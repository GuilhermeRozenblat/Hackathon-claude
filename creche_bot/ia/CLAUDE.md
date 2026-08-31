# IA: persona e classificação

Escrever a fala do Zé e classificar mensagem fora do roteiro. **Você não conhece o fluxo**:
recebe entrada, devolve string ou schema.

> ⚠️ **A extração de documentos não é sua.** É do backend, atrás de
> `backend/porta.py::enviar_documento()`.

**Seus arquivos:** `redacao.py` · `persona.py` · `transcricao.py` · `tests/ia/`.
**Não toque** em `conversa/`, `canal/`, `dados/`, `backend/`, `dominio/`: `Classificacao` e
`DadosExtraidos` moram em `dominio/tipos.py`, congelado.

## Entrega

```python
def texto(self, chave: str, **vars) -> str
def classificar(self, mensagem: str, estado: str) -> Classificacao
def responder_duvida(self, pergunta: str, etapa: str) -> str | None   # None = sem IA
def diagnosticar(api_key: str) -> str | None                          # None = a chave funciona
RedatorClaude.ultima_falha: str | None                                # por que a última chamada não valeu
```

As duas primeiras recebem **a etapa e a pergunta estática que está no ar**, nada de CPF, nome
ou endereço. Para responder "como funciona a fila" o modelo não precisa saber quem pergunta.

| Classe | Chave? | Quando |
|---|---|---|
| `RedatorEstatico` | não | **padrão**, quem não ligou a IA |
| `RedatorClaude` | sim | a chave que a pessoa cadastrou com `/ia` ([D20](../../docs/DECISOES.md)) |

`RedatorClaude` cai para o estático em qualquer falha, porque erro de rede não pode emudecer o
bot. Mas cair **calado** faria a pessoa achar que a IA dela está de pé: por isso `ultima_falha` e
`diagnosticar()`, com os motivos de `MOTIVOS` (401, 403, 404, 429, 5xx, rede, crédito).
**Nunca ecoe o corpo da resposta da API**: vem em inglês, muda sem aviso e carrega detalhe da
conta de quem cadastrou.

`classificar` é uma chamada por mensagem digitada; saída fora do vocabulário de `Intencao`, ou
API fora, cai na heurística do `RedatorEstatico` ([D18](../../docs/DECISOES.md)).

## Guardrails: o prompt pede, o filtro cobra

Nada que o modelo devolve entra na conversa sem passar por `_limpo` (tira markdown) e
`_promete` (barra "garantido", "com certeza", "sua pontuação", "está na frente").

| Onde | Trava | Por quê |
|---|---|---|
| `texto()` | `_numeros(novo) == _numeros(base)` | número mexido é CPF, protocolo ou nota errada na tela |
| `responder_duvida()` | descarta `\d{5,}` e link | CPF, CEP e protocolo inventados; link leva a golpe |
| `responder_duvida()` | pergunta truncada em 500 chars, sem `<` nem `>` | sem eles ninguém fecha a tag e escapa do bloco de dado |
| `classificar()` | saída obrigatoriamente em `Intencao` | rótulo inventado viraria estado que a máquina não conhece |
| `conversa/maquina.py` | `LIMITE_DUVIDAS` por contato/hora | chat aberto é um botão de gastar dinheiro dos outros |

Reprovou, cai para o texto estático: um filtro que barra não pode emudecer o bot.

`persona.py` é o arquivo mais editado do projeto, porque produto mexe toda semana. Por isso é só
texto, sem lógica.

## Áudio

Claude **não recebe áudio**, e mandar a voz de uma família para terceiros quebraria a regra de
privacidade. `faster-whisper` roda local (`pip install -e ".[audio]"`, tamanho em
`WHISPER_MODELO`), e o `canal/` recusa áudio acima de 120s porque a transcrição é síncrona. Sem
a dependência, o bot pede para escrever, e não quebra. O `__main__` aquece o modelo numa thread
no boot: em disco frio ele baixa ~460 MB, e carregar na primeira voz emudeceria o bot esse
tempo todo.

## Privacidade (elegibilidade a ZDR)

```python
MODELO = "claude-haiku-4-5"   # nunca Fable 5 / Mythos 5: Covered Models, sem ZDR
```

**Proibido nesta pasta:** `client.files.*`, Batch API, `code_execution`, MCP connector, Managed
Agents. Há teste que faz `grep` aqui e falha.

Técnica: sem `effort` e sem `thinking` (Haiku 4.5 não aceita, devolve 400); sem `cache_control`
(o system tem ~180 tokens e nunca alcança o mínimo cacheável); e **trate
`stop_reason == "refusal"`**, que vem HTTP 200, não exceção.

## Tom

Uma pergunta por mensagem, máximo 4 linhas, sem markdown, nunca invente número, nome de escola,
endereço ou prazo. A regra de honestidade, o que o bot pode e não pode dizer sobre uma creche,
está inteira no `CLAUDE.md` da raiz, e vale para todo texto que sair daqui.

Verificar: `make contratos && make ia`.
