# Notificação

Levar mudança de status até o chat sem perder mensagem. Transactional outbox: uma tabela e um
loop. **Sem Kafka, sem Celery, sem Redis.**

**Seus arquivos:** `outbox.py` · `catalogo.py` · `tests/notificacao/`.
`chaves.py` é **congelado**. **Não toque** em `canal/telegram.py` (use `fakes/canal_fake.py`),
`conversa/`, `ia/`.

```python
# outbox.py: lógica pura, ZERO SQL
def sincronizar(backend: BackendCreche, repo: Repositorio) -> int
def entregar(canal: Canal, repo: Repositorio, limite: int = 50) -> int
def rodar_worker(backend, canal, repo, intervalo_s: float = 5.0) -> None

# catalogo.py
def renderizar(chave: ChaveTemplate, variaveis: dict, canal: str) -> MensagemSaida
```

O trabalho é em dois tempos, e separá-los é o que dá idempotência: se o envio falhar, o evento
fica na fila e **não** é buscado de novo no backend. A persistência entra pela porta
(`enfileirar`, `pendentes`, `marcar_enviado`, `marcar_falha`). **Não escreva SQL aqui**: há
teste que varre o pacote.

## A regra que existe para o flip

**Nunca uma string livre na outbox.** Só `(ChaveTemplate, variáveis)`. No Telegram a chave vira
texto com figurinha; no WhatsApp, template aprovado pela Meta, que não aceita texto livre, leva
~24h para aprovar e é pago. Se o emissor gravasse a string pronta, o flip seria impossível, e
cada uma das nove chaves vira um template submetido, no caminho crítico. Chave nova entra no
contrato congelado por PR próprio; quanto antes, melhor.

`catalogo.py` valida as variáveis contra `chaves.VARIAVEIS` **antes** de renderizar: template
com variável faltando é erro em produção, não no deploy. E `POR_TIPO_ETAPA` mapeia `TipoEtapa` →
`ChaveTemplate` numa tabela, não numa cadeia de `if`, e é o que faz etapa nova do backend
funcionar sem código novo ([D4](../../docs/DECISOES.md)).

## Regras específicas

- **`enfileirar()` roda na mesma transação** que muda o status. É isso que faz "outbox": ou os
  dois acontecem, ou nenhum.
- **`enviado_em` marcado só após sucesso.** Reprocessar não duplica.
- **Retry com backoff** e campo `tentativas`. Depois de N falhas, para e loga.
- **Rate limit do Telegram é ~1 msg/s por chat.** Um lote grande não pode tomar `429`.
- **Nunca logue as variáveis**: carregam nome de criança.
- **`ACAO_PRESENCIAL` sempre com endereço, `CONVOCACAO` sempre com prazo.**
  `Etapa.__post_init__` já recusa o contrário, e o catálogo depende disso: mandar a família à
  unidade sem dizer onde, ou deixar o prazo vencer em silêncio, é o erro caro que
  `CONVOCACAO` (R2) e `LEMBRETE_CONVOCACAO` (R3) existem para atacar.
- **Nenhum texto promete vaga, cita pontuação ou dá posição na fila.** Vale para chave nova
  também; ver a regra de honestidade no `CLAUDE.md` da raiz.

## Verificar

`make contratos && make notificacao`, com `fakes/canal_fake.py`: enfileirar + drenar entrega uma
vez só; drenar duas vezes não duplica; variável faltando falha no `renderizar()`, não no envio;
toda chave do enum tem render para Telegram. Fim a fim: `/avancar` no chat depois de concluir
uma inscrição, e a mensagem chega em segundos.
