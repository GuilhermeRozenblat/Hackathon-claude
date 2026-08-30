# IA — persona e classificação

Escrever a fala do Zé Matrícula e classificar mensagem fora do roteiro. **Você não conhece
o fluxo**: recebe entrada, devolve string ou schema.

> ⚠️ **A extração de documentos não é sua.** Ela é do backend do município, atrás de
> `backend/porta.py::enviar_documento()`. Se um dia decidirmos extrair localmente com
> Claude, vira uma implementação daquela porta — configuração, não arquitetura.

## Seus arquivos

`redacao.py` · `persona.py` · `transcricao.py` · `tests/ia/`

**Não toque** em `conversa/`, `canal/`, `dados/`, `backend/`, `dominio/`.

`Classificacao` e `DadosExtraidos` moram em `dominio/tipos.py`, que é congelado.

## Entrega

```python
def texto(self, chave: str, **vars) -> str
def classificar(self, mensagem: str, estado: str) -> Classificacao
def responder_duvida(self, pergunta: str, etapa: str) -> str | None   # None = sem IA
```

`responder_duvida` recebe **só o nome da etapa** — nada de CPF, nome ou endereço. Para
responder "como funciona a fila" o modelo não precisa saber quem está perguntando.

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

## Guardrails: o prompt pede, o filtro cobra

Do outro lado tem um campo de texto aberto. Nada que o modelo devolve entra na conversa
sem passar por `_limpo` (tira markdown) e `_promete` (barra "garantido", "com certeza",
"sua pontuação"). Além disso:

| Onde | Trava | Por quê |
|---|---|---|
| `texto()` | `_numeros(novo) == _numeros(base)` | número mexido é CPF, protocolo ou nota errada na tela |
| `responder_duvida()` | descarta `\d{5,}` e link | CPF, CEP, telefone e protocolo inventados; link leva a golpe |
| `responder_duvida()` | pergunta truncada em 500 chars, sem `<` nem `>` | sem eles ninguém fecha a tag e escapa do bloco de dado |
| `conversa/maquina.py` | `LIMITE_DUVIDAS` por contato/hora | chat aberto é um botão de gastar dinheiro dos outros |

Reprovou, cai para o texto estático. Um filtro que barra não pode emudecer o bot.

## Áudio: `transcricao.py`

Claude **não recebe áudio** — a API aceita texto, imagem e PDF. E mandar a voz de uma
família para um serviço de terceiros quebraria a regra de privacidade. Então o
`faster-whisper` roda local (`pip install -e ".[audio]"`) e o `canal/` recusa áudio acima
de 120s porque a transcrição é síncrona. Sem a dependência instalada o bot pede para a
pessoa escrever — não quebra.

O `__main__` chama `Transcritor.carregar()` numa thread no boot. Em disco frio o modelo
baixa ~460 MB (medimos 159s) e o polling do Telegram é síncrono: carregar na primeira voz
emudeceria o bot para todo mundo esse tempo todo.

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
- **Nunca prometa vaga, pontuação nem posição na fila.** A classificação roda depois do
  fechamento das inscrições e não existe durante a conversa. Proibido "garantido", "com
  certeza", "vai conseguir". Sobre creche, só distância, vaga aberta agora e concorrência
  do ano passado, rotulada como passado.
- Nunca invente número, nome de escola, endereço ou prazo.
- Sem markdown.

## Verificar

```bash
make contratos && make ia
```

Sem rede: `grep` proíbe as APIs fora de ZDR; nenhum texto de `TEXTOS` contém promessa de
vaga nem markdown. Com chave: `RedatorClaude` preserva os números exatos do texto base.
