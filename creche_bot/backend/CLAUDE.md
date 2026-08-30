# Backend do município — a fronteira com os dados da Matrícula Rio

O histórico da Matrícula Rio, a régua do processo vigente, a oferta de creches, a extração
de documentos e o andamento da inscrição são feitos por **outro time, em outra máquina**.
Nada disso é recalculado aqui — seria trabalho duplicado com duas fontes da verdade.

O sistema de registro continua sendo o **matricula.rio**. O bot é canal complementar: a
inscrição gerada aqui é gravada lá, com a hierarquia `prm_id / plm_id / ipl_id`.

## A divisão

```
creche_bot/backend/   → dados do MUNICÍPIO (histórico, régua, oferta, situação)
creche_bot/dados/     → estado NOSSO (sessão, consentimento, outbox)
```

Portas diferentes, donos diferentes, e nenhuma sabe da outra.

## As 17 operações

| Grupo | Operação | Devolve |
|---|---|---|
| Processo | `periodo_de_inscricao()` | `(início, fim)`. Fora dele o bot só oferece aviso |
| | `data_do_resultado()` | a única data que o bot promete |
| | `data_de_corte()` | onde a idade da criança é medida para o grupamento |
| | `criterios_do_processo()` | **a régua vigente**, ordenada, sem as autopreenchíveis |
| Histórico | `buscar_por_responsavel(cpf)` | `CadastroAnterior \| None` |
| Endereço | `resolver_cep(cep, numero)` | `Endereco \| None`, com coordenadas |
| Oferta | `escolas_proximas(endereco, grupamento, horario, n)` | top N **já ordenado**, com `chance` |
| | `panorama_da_regiao(endereco)` | o que aconteceu na microárea no ano-base |
| Inscrição | `validar_nis(nis)` | `(válido, códigos de critério que ele comprova)` |
| | `inscrever(dados, preferencias)` | o número da inscrição |
| | `enviar_documento(numero, codigo_criterio, arquivo, mime)` | `DadosExtraidos` |
| | `pontos_de_entrega(forma, id_escola, cep)` | a creche, ou os CRAS próximos |
| Consulta | `consultar_por_numero(numero, nascimento)` | `list[Desfecho]` |
| | `consultar_por_nome(nome, nascimento, filiacao)` | `list[Desfecho]` |
| | `consultar_por_responsavel(cpf)` | `list[Desfecho]` — 2,8% têm mais de uma criança |
| Notificação | `situacao(numero)` | onde a inscrição está agora |
| | `mudancas_desde(marca)` | `(mudanças, nova marca)` — alimenta a outbox |

### Quatro coisas que essa lista decide, e que não são óbvias

**A âncora é o CPF do responsável, não o da criança.** É mais confiável, é o que a pessoa
tem na mão, e é o que reconhece reinscrição e irmãos. 27,9% das crianças de 2025 já
constavam em 2024. Exigir CPF de criança de 0 a 3 anos no primeiro turno derruba família
na porta. Ver [D12](../../docs/DECISOES.md).

**`criterios_do_processo()` existe para a régua não virar código.** Entre 2023 e 2024 só 3
das 13 perguntas sobreviveram e o teto caiu de 465 para 100 pontos. Vem de
`ic.pergunta_processo` + `ic.pergunta_catalogo`, ordenado por `ordem`, sem as marcadas como
autopreenchível. Ver [D15](../../docs/DECISOES.md).

**Os dois caminhos de consulta são obrigatórios.** São as rotas `/ConsultaInscricao` e
`/ConsultaCreche` do portal: número + nascimento, OU nome + nascimento + filiação. O
segundo existe porque nem todo mundo guarda o número, e porque há criança sem filiação
registrada na certidão.

**`validar_nis()` devolve os critérios comprovados, não só um booleano.** Com o NIS o
servidor consulta CadÚnico e Bolsa Família de uma vez — é por isso que as duas perguntas
da régua cabem num turno só.

## Seus arquivos

`http.py` · `tests/backend/`

`porta.py`, `mock.py` e `creche_bot/dominio/tipos.py` são **congelados**.
**Não toque** em `conversa/`, `canal/`, `dados/`.

## Estado atual

`mock.py` implementa `BackendCreche` por completo, com os dados do roteiro v2, e é o que
roda hoje. Todo o resto do projeto valida contra ele. **Enquanto o backend real não
existir, esta trilha não tem trabalho** — ela abre quando o outro time publicar o contrato
HTTP.

## Quando abrir: escreva `BackendHTTP`

```python
class BackendHTTP:                     # implementa BackendCreche
    def __init__(self, base_url: str, token: str, timeout_s: float = 4.0): ...
```

### A regra que faz o link ser barato: camada anticorrupção

O JSON do backend é dele. Os nomes de campo, os códigos de etapa e o formato de data vão
mudar sem nos avisar. **Nada disso pode vazar para `conversa/`.**

Traduza na fronteira e devolva só os tipos de `dominio/tipos.py`. Depois de `http.py`,
ninguém no projeto vê `dict`, `json` ou `response`. Se o backend renomear um campo, muda
um arquivo.

### O que a tradução tem que resolver

**`codigo` de etapa → `TipoEtapa`.** O backend define **quais** etapas existem —
vocabulário aberto, muda por município. Nós definimos **o que fazer** com cada uma —
`TipoEtapa`, fechado, seis valores.

```python
_TIPO_POR_CODIGO: dict[str, TipoEtapa] = {
    "inscricao_recebida":   "aguardando",
    "envio_documentos":     "acao_no_chat",
    "entrega_na_unidade":   "acao_presencial",
    "aguardando_analise":   "aguardando",
    "convocado":            "convocacao",
    "deferido":             "concluida",
    "indeferido":           "encerrada",
}

def _tipo(codigo: str) -> TipoEtapa:
    tipo = _TIPO_POR_CODIGO.get(codigo)
    if tipo is None:
        log.warning("etapa desconhecida: %s", codigo)   # o código, nunca dado de pessoa
        return "aguardando"        # default seguro: o bot informa e NÃO cobra nada
    return tipo
```

**O default é `"aguardando"` de propósito.** Etapa nova e desconhecida faz o bot avisar que
andou, sem inventar uma cobrança. O erro caro seria mandar a pessoa à creche à toa.

Etapa nova que caia num tipo conhecido: adicione **uma linha** no dict. Nada mais muda —
nem a conversa, nem o catálogo de notificação, nem os templates da Meta.

**Situação bruta → `EstadoInscricao`.** O banco grava um status por opção de creche, com
oito valores. Traduza cada um e deixe o `dominio` calcular o desfecho — `desfecho_entre()`
já faz isso. Dois detalhes que quebram query:

- O valor gravado é `Cancelado na confirmacao`, **sem cedilha e sem til**. Filtrar pela
  grafia correta devolve zero linhas.
- 77,8% das linhas `Cancelado pelo sistema` pertencem a inscrições que **foram atendidas**
  — é o cancelamento automático das outras opções. Nunca deixe esse valor virar o desfecho
  de quem tem opção melhor. Ver [D14](../../docs/DECISOES.md).

### O que o bot NÃO mostra, e o backend não precisa mandar

Pontuação, classificação e posição na fila. A régua é norma (Resolução SME nº 542/2025),
roda em SQL determinístico **depois do fechamento das inscrições**, e não existe no momento
da conversa. Sobre uma creche vão três campos, e todos são fato verificável: distância,
`vaga_ociosa` e `Concorrencia` do ano passado — com `ano` obrigatório, para a UI ser
forçada a dizer de quando é o número. Ver [D5](../../docs/DECISOES.md).

### Resiliência — a conversa não pode morrer

- **Timeout curto** (~4s). Tem gente esperando no chat, não é um job noturno.
- **Levante `BackendIndisponivel`** em timeout, 5xx ou payload inválido. Nunca deixe
  vazar `httpx.TimeoutException` para `conversa/`.
- **Retry só no que é idempotente** (`buscar_por_responsavel`, `resolver_cep`,
  `escolas_proximas`, `criterios_do_processo`, `pontos_de_entrega`, as três consultas,
  `situacao`, `mudancas_desde`).
  **`inscrever()` NUNCA repete sozinho** — inscrição duplicada é problema real para a
  família: duas inscrições para a mesma criança se anulam. `dados` traz
  `chave_idempotencia`; honre-a e devolva o mesmo número. Ver [D16](../../docs/DECISOES.md).
- **Cache curto** em `escolas_proximas` e `criterios_do_processo` (~5 min). O usuário volta
  ao painel várias vezes na mesma conversa, e a régua não muda durante ela.
- **`mudancas_desde(marca)`** é polling com marca d'água, não webhook: o backend não
  precisa nos conhecer, e um restart nosso não perde nem duplica evento.

### Privacidade

O que passa por aqui é dado de criança, CPF e **dado sensível** — saúde, violência
doméstica, uso de substâncias, situação prisional (LGPD art. 5º II e art. 11). TLS
obrigatório, token em `config`, e **nunca logue payload** — só o código HTTP, a operação e
o número da inscrição.

## Como verificar

```bash
make contratos && make backend
```

O teste que importa: **a mesma bateria roda contra `BackendMock` e contra `BackendHTTP`**
(este último com respostas gravadas). Se passa nos dois, o contrato está honrado e trocar
um pelo outro é uma linha de configuração.

Mais: `_tipo()` devolve `"aguardando"` para código desconhecido, e nenhum campo do JSON
do backend aparece fora deste arquivo.

## Pronto quando

`BackendHTTP` passa a mesma bateria de `BackendMock`, e trocar os dois é uma env var.
