# Canal Telegram

Traduzir o transporte do Telegram para o modelo canônico e de volta. **Você não conhece
regra de negócio**: nada de decidir o que responder, só como entregar.

## Seus arquivos

`telegram.py` · `render.py` · `figurinhas.py` · `tests/canal/`

Só lê: `tipos.py` (congelado). **Não toque** em `conversa/`, `ia/`, `dados/`,
`backend/`, `notificacao/`.

## Entrega

```python
# telegram.py
def rodar(nucleo: Nucleo) -> None:      # long polling, loop principal
def enviar(id_externo: str, msg: MensagemSaida) -> None
```

1. Update do Telegram → `MensagemEntrada`. Texto, foto (baixada em bytes) e clique de
   botão (`callback_query` → `escolha`). `id_mensagem` preenchido sempre.
2. `MensagemSaida` → payload do Telegram, em `render.py`.
3. `figurinhas.py`: chave (`"comemorando"`, `"pensando"`, `"vamos_la"`, `"festa"`,
   `"atencao"`) → `file_id`. Mapa em dict; `file_id` é estável, então cacheia.

## Regras específicas

- **Long polling (`getUpdates`), não webhook.** É o que faz a V1 rodar em localhost sem
  HTTPS nem ngrok. O WhatsApp exigirá webhook na Fase 3 — problema de outro arquivo.
- **`getFile` baixa no máximo 20 MB.** Foto maior: peça outra, com mensagem gentil.
- **Rate limit ~1 msg/s por chat.** Fila de envio com backoff. `429` vem com
  `retry_after` — respeite.
- **Texto puro.** Não gere `MarkdownV2`: o escape do Telegram é fonte clássica de bug e o
  WhatsApp usa outro dialeto. Envie sem `parse_mode`.
- **`local` vira uma segunda mensagem** (`sendVenue`), depois do texto. Nunca um anexo.
- **Rótulo de botão tem 20 caracteres, e a abreviação NÃO mora aqui.** Ela está em
  `canal/tipos.py` (`abreviar`, `botoes_nomeados`), junto do limite que existe para
  respeitar — o construtor de `MensagemSaida` cobra antes do render chegar. Quem *produz*
  o botão abrevia. Se dois nomes colidirem depois de abreviados, `botoes_nomeados` numera:
  abreviar duas escolas para o mesmo texto é pior que truncar, porque a pessoa escolhe
  errado sem saber.
- **Nunca logue conteúdo de mensagem nem bytes de foto.** Só `id_externo` e `id_mensagem`.
  A exceção é `DEBUG_CONTEUDO=1` (`make debug`): espelha texto, rótulos e o tamanho do
  anexo no console do dev. Os bytes ficam fora mesmo assim — `tests/canal/test_traco.py`.

## Como verificar

```bash
make contratos && make canal
```

Testes sem rede: um update de exemplo (JSON fixo) vira a `MensagemEntrada` esperada; uma
`MensagemSaida` com 3 botões vira o payload esperado; nomes longos abreviam sem colidir.

Com rede, quando houver token: `rodar()` com um núcleo que ecoa — mandar "oi" no Telegram
e receber de volta com botão e figurinha.

## Pronto quando

O eco funciona no Telegram real, e `make canal` passa sem rede.
