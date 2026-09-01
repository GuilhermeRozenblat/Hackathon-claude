# Canal Telegram

Traduzir o transporte do Telegram para o modelo canônico e de volta. **Você não conhece regra
de negócio**: não decide o que responder, só como entregar.

**Seus arquivos:** `telegram.py` · `render.py` · `figurinhas.py` · `tests/canal/`.
**Só lê:** `tipos.py` (congelado). **Não toque** em `conversa/`, `ia/`, `dados/`, `backend/`,
`notificacao/`.

```python
def rodar(nucleo: Nucleo) -> None      # long polling, loop principal
def enviar(id_externo: str, msg: MensagemSaida) -> None
def digitando(id_externo: str | None)  # contexto: "digitando…" enquanto o núcleo trabalha
```

O `sendChatAction` do Telegram dura ~5s, e turno com áudio ou modelo passa disso: `digitando`
renova o aviso numa thread daemon até a resposta sair. É melhor esforço — falhar ali nunca
atrasa nem derruba a resposta. **O webhook usa o mesmo contexto** (`scripts/servidor.py`).

1. Update do Telegram → `MensagemEntrada`: texto, foto (bytes), áudio de voz, documento e
   clique de botão (`callback_query` → `escolha`). `id_mensagem` sempre preenchido.
2. `MensagemSaida` → payload, em `render.py`.
3. `figurinhas.py`: chave (`"comemorando"`, `"festa"`, `"atencao"`…) → emoji hoje, `file_id`
   quando houver pack. Quem escolhe a chave é `ia/persona.py`, não você.

## Os dois modos de entrega

**Polling (`getUpdates`) é o daqui**, e é o que faz rodar em localhost sem HTTPS nem ngrok.

⚠️ **`rodar()` chama `deleteWebhook` antes de entrar no loop**: os dois modos são exclusivos, e
sem isso `getUpdates` devolve 409. A consequência é que **subir o bot local com o token de
produção derruba o bot hospedado**, em silêncio, até alguém rodar
`python scripts/configurar_webhook.py https://…` de novo. Para depurar depois do deploy, use um
token de teste, ou `--remover` e reaponte no fim.

**O webhook já existe, e não é seu:** `scripts/servidor.py` recebe o POST na hospedagem e chama
o mesmo núcleo. Se mexer em como um update vira `MensagemEntrada`, os dois caminhos mudam, e
`tests/test_servidor.py` cobre o lado de lá.

## Regras específicas

- **`getFile` baixa no máximo 20 MB.** Foto maior: peça outra, com mensagem gentil.
- **Áudio acima de `MAX_SEGUNDOS_AUDIO` (120s) não é baixado.** A transcrição é síncrona: um
  áudio de cinco minutos travaria o polling para todo mundo. O `mime` vem do cliente e não
  autoriza nada, serve só para o núcleo saber que é voz.
- **Rate limit ~1 msg/s por chat.** Fila de envio com backoff; `429` vem com `retry_after`.
- **Texto puro.** Não gere `MarkdownV2`: o escape do Telegram é fonte clássica de bug e o
  WhatsApp usa outro dialeto. Envie sem `parse_mode`.
- **`local` vira uma segunda mensagem** (`sendVenue`), depois do texto. Nunca um anexo.
- **A abreviação de rótulo NÃO mora aqui.** Está em `canal/tipos.py` (`abreviar`,
  `botoes_nomeados`), junto do limite que ela existe para respeitar, e o construtor cobra antes
  do render. Se dois nomes colidirem depois de abreviados, `botoes_nomeados` numera: abreviar
  duas escolas para o mesmo texto é pior que truncar, porque a pessoa escolhe errado sem saber.
- **Nunca logue conteúdo de mensagem nem bytes de foto.** Só `id_externo` e `id_mensagem`. A
  exceção é `DEBUG_CONTEUDO=1` (`make debug`), e mesmo aí os bytes ficam fora, veja
  `tests/canal/test_traco.py`.

## Verificar

`make contratos && make canal`, sem rede: um update de exemplo vira a `MensagemEntrada`
esperada; uma `MensagemSaida` com 3 botões vira o payload esperado; nomes longos abreviam sem
colidir. Com token: `make eco`, mandar "oi" no Telegram e receber de volta com botão e emoji.
