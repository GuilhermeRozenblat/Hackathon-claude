# Notificação

Levar mudança de status até o chat, sem perder mensagem. Transactional outbox: uma tabela
e um loop. **Sem Kafka, sem Celery, sem Redis.**

## Seus arquivos

`outbox.py` · `catalogo.py` · `tests/notificacao/`

`chaves.py` é **congelado**. **Não toque** em `canal/telegram.py` (use `CanalFake`),
`conversa/`, `ia/`.

## Entrega

```python
# outbox.py — lógica pura, ZERO SQL
def sincronizar(backend: BackendCreche, repo: Repositorio) -> int
def entregar(canal: Canal, repo: Repositorio, limite: int = 50) -> int
def rodar_worker(backend, canal, repo, intervalo_s: float = 5.0) -> None

# catalogo.py
def renderizar(chave: ChaveTemplate, variaveis: dict, canal: str) -> MensagemSaida
```

O trabalho é em dois tempos, e separá-los é o que dá idempotência: se o envio falhar, o
evento fica na fila e **não** é buscado de novo no backend.

A persistência entra pela porta (`repo.enfileirar`, `repo.pendentes`,
`repo.marcar_enviado`, `repo.marcar_falha`). **Não escreva SQL aqui** — há teste que varre
o pacote e falha.

## Por que estes fluxos existem

Em 2025, 5.519 famílias (7,7%) foram convocadas e **perderam a vaga**, concentradas em
Pilares, Santa Teresa, Gávea e Bangu. A maior parte nunca soube que foi chamada — hoje
"não foi avisada" e "foi avisada e desistiu" viram o mesmo registro no banco, e as duas
são tratadas como desistência. `CONVOCACAO` (R2) e `LEMBRETE_CONVOCACAO` (R3) são a
correção direta desse vazamento; `DOCUMENTO_PENDENTE` (R1) ataca os 8,0% de validação
documental.

Nove chaves, e nenhum texto delas promete vaga, cita pontuação ou dá posição na fila.

## A regra que existe para o flip

**Nunca uma string livre na outbox.** Só `(ChaveTemplate, variáveis)`.

No Telegram a chave vira texto animado com figurinha. No WhatsApp vira template aprovado
pela Meta — que não aceita texto livre nem figurinha fora da janela de 24h, leva ~24h para
aprovar, e é pago. Se o emissor gravasse a string pronta, o flip seria impossível.

`catalogo.py` valida as variáveis contra `chaves.VARIAVEIS` **antes** de renderizar:
template do WhatsApp com variável faltando é erro em produção, não no deploy.

## Regras específicas

- **`enfileirar()` roda na mesma transação** que muda o status. É isso que faz "outbox":
  ou os dois acontecem, ou nenhum.
- **Idempotência**: `enviado_em` marcado só após sucesso. Reprocessar não duplica.
- **Retry com backoff** e campo `tentativas`. Depois de N falhas, para e loga — não fica
  girando.
- **Rate limit do Telegram é ~1 msg/s por chat.** O worker respeita; um lote grande não
  pode tomar `429`.
- **Nunca logue as variáveis** — carregam nome de criança.
- **`ACAO_PRESENCIAL` sempre vem com endereço, `CONVOCACAO` sempre com prazo.**
  `Etapa.__post_init__` já recusa o contrário, mas o catálogo depende disso: mandar a
  família à unidade sem dizer onde, ou deixar o prazo vencer em silêncio, é o erro caro.

## Despacho por tipo, não por código

`POR_TIPO_ETAPA` mapeia `TipoEtapa` → `ChaveTemplate`. Uma tabela, não uma cadeia de `if`.
É o que faz etapa nova do backend funcionar sem código novo — ver [D4](../../docs/DECISOES.md).

## Fase 3, e por que importa agora

Cada chave de `ChaveTemplate` vira **um template submetido à Meta**, ~24h de aprovação
cada. É o caminho crítico do flip. Se você precisar de uma chave nova, ela entra no
contrato congelado por PR próprio — quanto antes, melhor.

## Como verificar

```bash
make contratos && make notificacao
```

Testes com `fakes/canal_fake.py`: `enfileirar()` + `drenar()` entrega uma vez só; drenar
duas vezes não duplica; variável faltando falha no `renderizar()`, não no envio; toda
chave do enum tem render para Telegram.

Fim a fim (depois da integração):
`/avancar` no chat, depois de concluir uma inscrição → a mensagem chega em segundos.

## Pronto quando

O ciclo completo entrega no `CanalFake` e sobrevive a restart no meio do lote.
