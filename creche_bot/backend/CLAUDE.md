# Backend do município: a fronteira com os dados da Matrícula Rio

Histórico, régua vigente, oferta de creches, extração de documento e andamento da inscrição são
de **outro time, em outra máquina**. Nada disso é recalculado aqui. O sistema de registro
continua sendo o **matricula.rio**: a inscrição gerada aqui é gravada lá, com a hierarquia
`prm_id / plm_id / ipl_id`.

```
creche_bot/backend/   → dados do MUNICÍPIO (histórico, régua, oferta, situação)
creche_bot/dados/     → estado NOSSO (sessão, consentimento, outbox)
```

**Seus arquivos:** `mapa.py` · `MapaFilaCreche/` · `tests/backend/`, e o `http.py` que ainda
não existe. **Congelados:** `porta.py`, `mock.py`, `dominio/tipos.py`. **Não toque** em
`conversa/`, `canal/`, `dados/`.

## As 17 operações

Estão em `porta.py`, congeladas e com type hints, então não vou repetir a assinatura aqui, porque
duplicata de contrato deriva. O que a assinatura **não** diz:

- **A âncora é o CPF do responsável**, nunca da criança ([D12](../../docs/DECISOES.md)).
- **`criterios_do_processo()` existe para a régua não virar código** ([D15](../../docs/DECISOES.md)).
  Devolve a régua vigente, já ordenada, sem as autopreenchíveis.
- **Os dois caminhos de consulta são obrigatórios**, não redundantes: são as rotas
  `/ConsultaInscricao` e `/ConsultaCreche` do portal. Nem todo mundo guarda o número, e há
  criança sem filiação na certidão.
- **`validar_nis()` devolve os critérios comprovados**, não só um booleano: com o NIS o servidor
  consulta CadÚnico e Bolsa Família de uma vez, e é por isso que as duas perguntas cabem num
  turno.
- **`escolas_proximas()` devolve o top N já ordenado**, com `chance` e `ano`. Quem chama não
  reordena.
- **`data_do_resultado()` é a única data que o bot promete**; fora de `periodo_de_inscricao()`
  ele só oferece aviso.
- **`mudancas_desde(marca)` alimenta a outbox**: polling com marca d'água, e é o único ponto de
  entrada de notificação.

## Estado atual

| | Quando | O que entrega |
|---|---|---|
| **`BackendMapa`** | padrão | Oferta **real**: 820 unidades com demanda em 2025, de `MapaFilaCreche/`: distância a partir do CEP, vaga ociosa por grupamento, concorrência e chance estimada. Herda do mock o que os CSVs não têm: régua, histórico, extração e situação |
| **`BackendMock`** | `BACKEND=mock` (`make roteiro`) | As 3 escolas do roteiro. Implementa a porta inteira, é determinístico, e é o que **a bateria usa** |

Herdar do mock é deliberado: deixa explícito, num lugar só, o que ainda é inventado. **Enquanto
o backend real não existir, esta trilha não tem trabalho novo.**

## Quando abrir: o que o `BackendHTTP` vai precisar respeitar

```python
class BackendHTTP:                     # implementa BackendCreche
    def __init__(self, base_url: str, token: str, timeout_s: float = 4.0): ...
```

**Camada anticorrupção.** O JSON é do outro time e os nomes de campo vão mudar sem aviso:
traduza na fronteira e devolva só os tipos de `dominio/tipos.py`. Depois de `http.py`, ninguém
no projeto vê `dict`, `json` ou `response`.

**`codigo` de etapa → `TipoEtapa`, numa tabela, com default `"aguardando"`.** O default é
deliberado: etapa desconhecida faz o bot avisar que andou, sem inventar cobrança. Mandar a
pessoa à creche à toa é o erro caro. Etapa nova que caia num tipo conhecido é **uma linha** no
dict, e nada mais muda ([D4](../../docs/DECISOES.md)).

```python
_TIPO_POR_CODIGO: dict[str, TipoEtapa] = {
    "inscricao_recebida": "aguardando",   "envio_documentos": "acao_no_chat",
    "entrega_na_unidade": "acao_presencial", "aguardando_analise": "aguardando",
    "convocado": "convocacao", "deferido": "concluida", "indeferido": "encerrada",
}
```

**Situação bruta → `EstadoInscricao`**, os oito valores, e deixe `desfecho_entre()` calcular o
desfecho. Duas armadilhas que quebram query: o valor gravado é `Cancelado na confirmacao`
(**sem cedilha e sem til**), e a maior parte das linhas `Cancelado pelo sistema` pertence a
inscrições **atendidas**. Nunca deixe esse valor virar o desfecho de quem tem opção melhor
([D14](../../docs/DECISOES.md)).

**Resiliência.** Timeout curto (~4s), porque tem gente esperando no chat. Levante
`BackendIndisponivel` em timeout, 5xx ou payload inválido; nunca deixe vazar exceção da
biblioteca HTTP. Retry só no que é idempotente: **`inscrever()` NUNCA repete sozinho**, honre a
`chave_idempotencia` e devolva o mesmo número ([D16](../../docs/DECISOES.md)). Cache curto
(~5 min) em `escolas_proximas` e `criterios_do_processo`. `mudancas_desde(marca)` é polling com
marca d'água, não webhook: o backend não precisa nos conhecer.

**Privacidade.** Passa por aqui dado de criança, CPF e dado sensível. TLS obrigatório, token em
config, e **nunca logue payload**: só o código HTTP, a operação e o número da inscrição.

**O que o backend não precisa mandar:** pontuação, classificação e posição na fila. Sobre uma
creche vão quatro campos observados: distância, `vaga_ociosa`, `Concorrencia` (com `ano`
obrigatório) e a `chance` estimada, que é razão entre duas contagens do mesmo ano e **não**
contém a classificação. A regra inteira está no `CLAUDE.md` da raiz.

## Pronto quando

`BackendHTTP` passa a mesma bateria de `BackendMock` (com respostas gravadas), `_tipo()` devolve
`"aguardando"` para código desconhecido, nenhum campo do JSON aparece fora deste arquivo, e
trocar os dois é uma variável de ambiente. Verifique com `make contratos && make backend`.
