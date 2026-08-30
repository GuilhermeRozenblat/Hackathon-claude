# Backend do município — a fronteira com os dados da Matrícula Rio

O data lake, a oferta de escolas com nota de corte, a extração de documentos e o
andamento da inscrição são feitos por **outro time, em outra máquina**. Nada disso é
recalculado aqui — seria trabalho duplicado com duas fontes da verdade.

## A divisão

```
creche_bot/backend/   → dados do MUNICÍPIO (data lake, escolas, status)
creche_bot/dados/     → estado NOSSO (sessão, consentimento, outbox)
```

Portas diferentes, donos diferentes, e nenhuma sabe da outra.

## As 8 operações

| Operação | Devolve |
|---|---|
| `buscar_candidato(cpf, nascimento)` | `CadastroExistente \| None` — o Bloco 1 do roteiro |
| `escolas_proximas(cep_ou_bairro, nascimento, n)` | top N **já ordenado**, com nota de corte |
| `pontos_de_entrega(forma, id_escola, local)` | a creche, ou os CRAS próximos |
| `documentos_exigidos(id_escola)` | lista para a família conferir |
| `inscrever(dados, preferencias, forma)` | `Situacao` com protocolo e 1ª etapa |
| `enviar_documento(protocolo, arquivo, mime)` | `ResultadoExtracao` |
| `situacao(protocolo)` | onde a inscrição está |
| `mudancas_desde(marca)` | `(mudanças, nova marca)` — alimenta a outbox |

`buscar_candidato` exige CPF **e** data de nascimento: CPF sozinho não é prova de vínculo,
e a data evita mostrar o cadastro de outra criança para quem digitou errado.

## Seus arquivos

`http.py` · `tests/backend/`

`porta.py`, `mock.py` e `creche_bot/dominio/tipos.py` são **congelados**.
**Não toque** em `conversa/`, `canal/`, `dados/`.

## Estado atual

`mock.py` já implementa `BackendCreche` por completo e é o que roda hoje. Todo o resto do
projeto valida contra ele. **Enquanto o backend real não existir, esta trilha não tem
trabalho** — ela abre quando o outro time publicar o contrato HTTP.

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

### Nota de corte: o campo `ano` é obrigatório

`NotaCorte` exige `ano` porque a UI é obrigada a dizer de quando é o número. Nota de corte
sozinha não diz a chance da família, que não conhece a própria pontuação. Se o backend
mandar sem ano, use `indisponivel=True` — o bot escreve "ainda não divulgada" em vez de
inventar. Ver [D5](../../docs/DECISOES.md).

### O ponto mais importante: traduzir `codigo` de etapa em `TipoEtapa`

O backend define **quais** etapas existem — vocabulário aberto, muda por município.
Nós definimos **o que fazer** com cada uma — `TipoEtapa`, fechado, cinco valores.

```python
_TIPO_POR_CODIGO: dict[str, TipoEtapa] = {
    "inscricao_recebida":   "aguardando",
    "envio_documentos":     "acao_no_chat",
    "entrega_na_unidade":   "acao_presencial",
    "aguardando_analise":   "aguardando",
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

### Resiliência — a conversa não pode morrer

- **Timeout curto** (~4s). Tem gente esperando no chat, não é um job noturno.
- **Levante `BackendIndisponivel`** em timeout, 5xx ou payload inválido. Nunca deixe
  vazar `httpx.TimeoutException` para `conversa/`.
- **Retry só no que é idempotente** (`buscar_candidato`, `escolas_proximas`,
  `documentos_exigidos`, `pontos_de_entrega`, `situacao`, `mudancas_desde`).
  **`inscrever()` NUNCA repete sozinho** — inscrição duplicada é problema real para a
  família. Use chave de idempotência e deixe o usuário decidir.
- **Cache curto** em `escolas_proximas` (mesmo CEP + mesma turma, ~5 min). O usuário volta
  ao painel várias vezes na mesma conversa.
- **`mudancas_desde(marca)`** é polling com marca d'água, não webhook: o backend não
  precisa nos conhecer, e um restart nosso não perde nem duplica evento.

### Privacidade

O que passa por aqui é dado de criança, CPF e **dado de saúde** (deficiência/TGD/TEA), que
é dado sensível pela LGPD art. 5º II. TLS obrigatório, token em `config`, e **nunca logue
payload** — só o código HTTP, a operação e o protocolo.

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
