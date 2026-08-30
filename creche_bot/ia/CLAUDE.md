# IA — persona e classificação

Escrever a fala do Zé Matrícula e classificar mensagem fora do roteiro. **Você não conhece
o fluxo**: recebe entrada, devolve string ou schema.

> ⚠️ **A extração de documentos não é sua.** Ela é do backend do município, atrás de
> `backend/porta.py::enviar_documento()`. Se um dia decidirmos extrair localmente com
> Claude, vira uma implementação daquela porta — configuração, não arquitetura.

## Seus arquivos

`redacao.py` · `persona.py` · `tests/ia/`

**Não toque** em `conversa/`, `canal/`, `dados/`, `backend/`, `dominio/`.

`Classificacao` e `DadosExtraidos` moram em `dominio/tipos.py`, que é congelado.

## Entrega

```python
def texto(self, chave: str, **vars) -> str
def classificar(self, mensagem: str, estado: str) -> Classificacao
```

Duas implementações, e a escolha é config:

| Classe | Precisa de chave? | Quando |
|---|---|---|
| `RedatorEstatico` | não | **padrão hoje** — valida o fluxo sem gastar token |
| `RedatorClaude` | sim | variação de linguagem em cima dos mesmos textos |

`RedatorClaude` cai para o estático em qualquer falha. Um erro de rede não pode emudecer
o bot.

## `persona.py` é o arquivo mais editado do projeto

Produto mexe nele toda semana. Por isso é só texto, sem lógica: `TEXTOS` é um dict,
`SISTEMA` é o system prompt, e os dois consentimentos são constantes.

## Regras de privacidade (elegibilidade a ZDR)

```python
MODELO = "claude-haiku-4-5"   # nunca Fable 5 / Mythos 5: Covered Models, sem ZDR
```

**Proibido** nesta pasta: `client.files.*`, Batch API, `code_execution`, MCP connector,
Managed Agents. Nenhum é elegível a ZDR. Há teste que faz `grep` aqui e falha.

Técnica: sem `effort` e sem `thinking` — Haiku 4.5 não aceita nenhum dos dois (400); sem
`cache_control`, porque o system tem ~180 tokens e nunca alcança o mínimo cacheável; e
**trate `stop_reason == "refusal"`** — vem HTTP 200, não exceção.

## Regras de tom

- Uma pergunta por mensagem.
- Máximo 4 linhas.
- **Nunca prometa vaga.** Nota de corte é referência do ano passado, e a família não
  conhece a própria pontuação. Proibido "garantido", "com certeza", "vai conseguir".
- Nunca invente número, nome de escola, endereço ou prazo.
- Sem markdown.

## Verificar

```bash
make contratos && make ia
```

Sem rede: `grep` proíbe as APIs fora de ZDR; nenhum texto de `TEXTOS` contém promessa de
vaga nem markdown. Com chave: `RedatorClaude` preserva os números exatos do texto base.
