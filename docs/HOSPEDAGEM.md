# Hospedagem: o projeto inteiro fora da sua máquina

Hoje o Railway serve só o painel estático, e o bot roda no laptop de quem desenvolve. Este
documento é o caminho para o bot subir junto e nada mais depender da sua máquina.

## As três decisões que orientam o desenho

| Decisão | Escolha | Consequência |
|---|---|---|
| Banco | **Continua no Supabase** | O Railway só recebe a `DATABASE_URL`. Zero migração |
| Painel | **Público** | `api/banco.json` fica aberto, ver §5, por que isso é seguro aqui |
| Telegram | **Webhook, no mesmo serviço do painel** | Um serviço só. O bot acorda quando chega mensagem |

## 1. Como fica

```
                    Railway (1 serviço web)
                    ┌───────────────────────────────────┐
  Telegram ────────►│ POST /telegram/<segredo>          │
                    │        │                          │
  navegador ───────►│ GET  / → creche-conectada.html    │
                    │ GET  /api/banco.json              │──► Supabase (sa-east-1)
                    │ GET  /saude   (healthcheck)       │
                    │                                   │
                    │ thread: worker de outbox ─────────┼──► Telegram (R1 a R4)
                    └───────────────────────────────────┘
```

Um processo, `scripts/servidor.py`. O worker de outbox continua numa thread porque ele não
tem gatilho HTTP: é ele quem entrega as notificações R1 a R4.

## 2. O que já está pronto no código

| Arquivo | O que faz |
|---|---|
| `scripts/servidor.py` | O servidor de produção: painel, `api/banco.json`, `/saude` e o webhook. `ThreadingHTTPServer` em `0.0.0.0:$PORT` |
| `scripts/configurar_webhook.py` | Registra, mostra e remove o webhook no Telegram |
| `deploy/app.Dockerfile` | A imagem: Python 3.12, `-e ".[ia]"`, COPY como allowlist, usuário não-root |
| `.dockerignore` | Impede que `.env`, banco, `.git` e testes cheguem ao contexto de build |
| `railway.json` | `builder: DOCKERFILE` apontando para o arquivo acima, healthcheck em `/saude`, `sleepApplication`, restart em falha |
| `tests/test_servidor.py` | 18 testes: guardas do webhook, idempotência, gzip, allowlist, healthcheck |

Testado localmente ponta a ponta: painel 200, CSVs 200, `api/banco.json` 200 com dados do
Postgres, allowlist devolvendo 404 para `.env`, `.git/config`, `creche.db` e `.py`, e o
webhook recusando caminho errado (404), cabeçalho ausente ou errado (403) e JSON inválido
(400). Um update válido percorreu `_traduzir` → `Maquina.processar` → `enviar`.

E verificado **em Python 3.12 num container limpo**, com só `[ia,dev]` instalado, que é o
que a hospedagem monta. A bateria passa inteira lá. Desenvolvemos em 3.14; sem essa checagem o
build seria a primeira vez que o código veria a versão de produção.

## 3. O que falta você fazer, passo a passo

**3.1. Gerar o segredo do webhook**

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**3.2. Configurar as variáveis no Railway** (Variables, no serviço):

| Variável | Valor | Obrigatória |
|---|---|---|
| `TELEGRAM_TOKEN` | o token do @BotFather | sim |
| `TELEGRAM_WEBHOOK_SECRET` | o valor gerado em 3.1 | sim |
| `DATABASE_URL` | a connection string do pooler do Supabase, ver [BANCO.md](BANCO.md) | sim |
| `BACKEND` | vazio (oferta real) ou `mock` (demo determinística) | não |
| `WHISPER` | `1` liga a transcrição de áudio. Baixa ~460 MB no primeiro boot | não |
| `RAILWAY_DOCKERFILE_PATH` | `deploy/app.Dockerfile`. Existe desde o desenho antigo; se ficar apontando para `site.Dockerfile`, sobe o painel estático de novo | sim, até ser apagada |
| `OUTBOX_INTERVALO_S` | segundos entre ciclos do worker. Padrão `60` | não |
| `PORT` | o Railway injeta sozinho, **não defina** | não |

> A `DATABASE_URL` vai **sem** os sinais `<` e `>` em volta da senha. É o erro que já
> custou uma sessão de depuração aqui: o Postgres responde `password authentication
> failed`, que parece senha errada e não é. O `servidor.py` agora falha no boot com uma
> mensagem clara se sobrar `<` na string.

**3.3. Subir o código**

Hoje o serviço constrói de `deploy/site.Dockerfile`, a partir da branch
`fila/mapa-sisu-supabase` — é por isso que o `api/banco.json` responde 404 em produção: o
servidor de lá é estático e não conhece banco. Para virar o app completo, duas coisas
mudam no serviço:

- a branch de deploy passa a ser **`main`**;
- `RAILWAY_DOCKERFILE_PATH` passa a ser **`deploy/app.Dockerfile`** (o `railway.json` no
  repo já declara isso; a variável no painel é o cinto que sobra do desenho antigo, e deve
  ser apagada ou apontada para o mesmo arquivo).

Confirme no deploy log:

```
servidor em 0.0.0.0:8080, painel /creche-conectada.html, webhook POST /telegram/…
worker de outbox no ar
```

**3.4. Apontar o Telegram para lá**

```bash
TELEGRAM_WEBHOOK_SECRET=<o mesmo de 3.1> \
  python scripts/configurar_webhook.py https://creche-conectada-production.up.railway.app
python scripts/configurar_webhook.py --ver
```

**3.5. Conferir**

```bash
curl https://creche-conectada-production.up.railway.app/saude          # {"ok": true}
curl https://creche-conectada-production.up.railway.app/api/banco.json # origem: postgres
```

E mandar `/start` para o bot no Telegram.

## 3.6. O que está configurado agora, e o que não está

Levantado direto da Railway em 2026-08-31:

| Item | Estado hoje | Precisa |
|---|---|---|
| `TELEGRAM_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `DATABASE_URL`, `OUTBOX_INTERVALO_S` | **definidas** | nada |
| Origem do serviço | **`source = null`** — não está ligado ao GitHub. O deploy de hoje veio de `railway up` a partir da branch `fila/mapa-sisu-supabase` | ligar ao repo e apontar para `main`, no painel: Settings → Source |
| `RAILWAY_DOCKERFILE_PATH` | `deploy/site.Dockerfile` (o painel estático) | virar `deploy/app.Dockerfile` **no mesmo momento** em que o código chega a `main` |
| `sleepApplication` | **`False`** — o serviço não hiberna, e é a maior economia | o `railway.json` liga no deploy |
| `healthcheckPath` | não configurado | o `railway.json` aponta `/saude` no deploy |
| `numReplicas`, `restartPolicyType` | `1`, `ON_FAILURE` | nada |

> **A ordem importa.** `RAILWAY_DOCKERFILE_PATH` apontando para um arquivo que não existe
> na branch de deploy quebra o build e derruba o painel que está no ar. Por isso ele
> continua em `site.Dockerfile`: ele vira junto com o push, não antes.

## 3.7. Fora da Railway

| Item | Estado | Ação |
|---|---|---|
| Bot pode entrar em grupo | **`can_join_groups: true`** | Desligar no @BotFather: `/setjoingroups` → Disable. O bot recebe documento de criança, e a Bot API não permite mudar isso por código |
| Menu de comandos do Telegram | `/start`, `/status`, `/ajuda`, `/apagar` | Decidir se `/ia` e `/demo` entram. Os dois funcionam e o `/ajuda` os anuncia; ficaram fora do menu, o que pode ser deliberado — o menu está em linguagem de família |
| Descrições do bot | preenchidas | nada |

## 4. Pendências de código

| # | Pendência | Por quê | Quem |
|---|---|---|---|
| **C1** | `Telegram.receber(update)` público | `servidor.py` chama `canal._traduzir`, que é privado. Funciona, mas é a trilha do canal contornada por fora | PR da trilha do canal |
| **C3** | `ConnectionPool` não fecha limpo no Python 3.14 | Todo processo termina cuspindo `PythonFinalizationError` no log. Cosmético, mas polui | trilha dados |
| **C4** | Delimitar a entrada do cidadão em `RedatorClaude.texto()` | `REESCRITA.format(base=base)` interpola o nome da criança **sem delimitador**. As guardas de saída seguram hoje, mas a regra do projeto pede delimitação na entrada | trilha ia |
| **C5** | Suíte completa contra o pooler do Supabase | Deadlock no `TRUNCATE` entre arquivos e `prepared statement não existe` na conexão admin do `conftest`, ver [BANCO.md §7](BANCO.md) | trilha dados |
| **C6** | `lat/lng` cai para Curicica quando o CEP não tem coordenada | A família vê distância calculada do bairro errado, apresentada como fato | trilha backend |

Nenhuma bloqueia o deploy.

**Resolvida nesta rodada: idempotência do webhook.** O Telegram reenvia o update quando a
resposta demora ou a conexão cai, e reenvio traz o mesmo `update_id`. Sem guarda, a rede
tossindo virava pergunta repetida na tela da família e resposta contada duas vezes no
cadastro. `scripts/servidor.py` agora lembra os 2048 `update_id` mais recentes e descarta
repetição, com trava porque dois reenvios podem chegar em threads diferentes. Coberto em
`tests/test_servidor.py`.

## 5. Por que o painel pode ficar público

`api/banco.json` foi auditado: das 30 strings que ele emite, nenhuma é valor de coluna de
pessoa. O que sai é **nome de coluna** (`nome_crianca`, não o nome), estado de conversa
(`PROTOCOLO`), código de critério, e nome de creche, que é público e está nos CSVs
abertos. Zero CPF, telefone ou e-mail. As queries em `scripts/painel.py` só fazem `count`
e `count(*) FILTER`.

Se um dia alguém acrescentar uma query que selecione valor, isso deixa de valer. A regra
está escrita no topo de `painel.py`.

A allowlist do servidor entrega **só** o HTML do painel e os seis CSVs. `.env`,
`creche.db`, `.git/` e qualquer `.py` respondem 404, testado.

## 6. O que já está configurado para não gastar

A Railway cobra por **RAM × tempo**, **CPU × tempo** e **egresso**. As quatro escolhas
abaixo já estão no repositório. Você não precisa fazer nada, é só saber que existem.

| Alavanca | O que fizemos | Medido |
|---|---|---|
| **Dormir sem tráfego** | `sleepApplication: true` no `railway.json` | O serviço hiberna sozinho e acorda no primeiro request. É a maior economia das quatro |
| **Egresso** | gzip em memória + `Cache-Control: max-age=3600` | Uma visita ao painel caiu de **951 KB para 278 KB**. Com o cache, o F5 não baixa nada |
| **RAM** | sem `[audio]` no build | **36 MB de RSS**. Com o Whisper seriam ~170 MB de biblioteca mais 460 MB de modelo em disco |
| **CPU ociosa** | `OUTBOX_INTERVALO_S=60` (era 5s) | 12x menos ciclos de worker. Cada ciclo é uma consulta ao backend e uma ao banco |

Nesse tamanho o serviço cabe folgado no crédito mensal do plano Hobby. Confira o número
real em **Usage**, no painel da Railway, porque o preço por GB e por vCPU muda, e não vale
decorar aqui um valor que envelhece.

### O preço de deixar dormir, e é real

Enquanto hiberna, **o worker de outbox não roda**. Consequência prática:

- **A conversa não sofre.** O webhook acorda o serviço, e a família nem percebe: o
  Telegram espera ~60s e a plataforma sobe em segundos.
- **As notificações R1 a R4 atrasam.** Elas só saem quando algo acorda o serviço. Se
  ninguém conversar e ninguém abrir o painel a noite toda, o aviso de convocação espera.

Para uma demonstração e para o volume de hoje, isso é o certo. **No dia em que houver
família de verdade esperando convocação, desligue:** troque `"sleepApplication": true` por
`false` no `railway.json`. O custo sobe para o de um serviço ligado 24h, ainda pequeno
nesse tamanho, e o aviso passa a sair no minuto seguinte.

Se quiser o meio-termo, um cron externo (o próprio `/loop` do Claude Code, ou o cron da
Railway) batendo em `/saude` de hora em hora acorda o worker sem manter o serviço de pé.

## 7. O que continua fora

- **Domínio próprio.** Hoje é `*.up.railway.app`. Trocar é Settings → Networking no Railway.
- **Backup do banco.** O Supabase no plano free não faz backup automático diário.
- **Observabilidade.** O log vai para o stdout do Railway e acabou. Sem métrica, sem alerta.
- **Escala.** `ThreadingHTTPServer` é uma thread por requisição, bom para dezenas
  simultâneas, não para milhares. Com volume real, isto vira ASGI atrás de um Uvicorn.
  Não invente isso antes de precisar.

## 8. Voltar para a máquina

Webhook e long polling são exclusivos. Para depurar localmente:

```bash
python scripts/configurar_webhook.py --remover
python -m creche_bot                 # long polling volta a funcionar
```

E para religar, o passo 3.4 de novo.
