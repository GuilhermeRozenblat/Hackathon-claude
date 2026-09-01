# Hospedagem: o projeto inteiro fora da sua máquina

O projeto está no ar no Railway, painel e bot no mesmo serviço, e nada depende mais do laptop
de quem desenvolve. Este documento é como ele foi montado, o que está configurado hoje, e como
refazer isso do zero.

## As três decisões que orientam o desenho

| Decisão | Escolha | Consequência |
|---|---|---|
| Banco | Continua no Supabase | O Railway só recebe a `DATABASE_URL`. Zero migração |
| Painel | Público | `api/banco.json` fica aberto. A §5 explica por que isso é seguro aqui |
| Telegram | Webhook, no mesmo serviço do painel | Um serviço só. O bot acorda quando chega mensagem |

## 1. Como está montado

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

## 2. As peças, e onde cada uma mora

| Arquivo | O que faz |
|---|---|
| `scripts/servidor.py` | O servidor de produção: painel, `api/banco.json`, `/saude` e o webhook. `ThreadingHTTPServer` em `0.0.0.0:$PORT` |
| `scripts/configurar_webhook.py` | Registra, mostra e remove o webhook no Telegram |
| `deploy/app.Dockerfile` | A imagem: Python 3.12, `-e ".[ia,audio]"`, COPY como allowlist, usuário não-root |
| `.dockerignore` | Impede que `.env`, banco, `.git` e testes cheguem ao contexto de build |
| `railway.json` | `builder: DOCKERFILE` apontando para o arquivo acima, healthcheck em `/saude`, `sleepApplication`, restart em falha |
| `tests/test_servidor.py` | 22 testes: guardas do webhook, idempotência, gzip, allowlist, healthcheck |

Testado localmente ponta a ponta: painel 200, CSVs 200, `api/banco.json` 200 com dados do
Postgres, allowlist devolvendo 404 para `.env`, `.git/config`, `creche.db` e `.py`, e o
webhook recusando caminho errado (404), cabeçalho ausente ou errado (403) e JSON inválido
(400). Um update válido percorreu `Telegram.receber` → `Maquina.processar` → `enviar`.

E verificado em Python 3.12 num container limpo, que é a versão que a hospedagem monta. A
bateria passa inteira lá. Desenvolvemos em 3.14, e sem essa checagem o build seria a primeira
vez que o código veria a versão de produção.

## 3. Como refazer isto do zero

### 3.1. Gerar o segredo do webhook

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3.2. Configurar as variáveis no Railway

Em Variables, no serviço:

| Variável | Valor | Obrigatória |
|---|---|---|
| `TELEGRAM_TOKEN` | o token do @BotFather | sim |
| `TELEGRAM_WEBHOOK_SECRET` | o valor gerado em 3.1 | sim |
| `DATABASE_URL` | a connection string do pooler do Supabase, ver [BANCO.md](BANCO.md) | sim |
| `BACKEND` | vazio (oferta real) ou `mock` (demo determinística) | não |
| `WHISPER` | `1` liga a transcrição de áudio. Baixa ~460 MB no primeiro boot | não |
| `WHISPER_MODELO` | `small` (padrão) ou `base`: `base` é ~3x mais rápido e mais leve de RAM, erra mais nome próprio | não |
| `REPOSITORIO` | `memoria` roda sem Postgres, a válvula de escape se o Supabase cair | não |
| `OUTBOX_INTERVALO_S` | segundos entre ciclos do worker. Padrão `60` | não |
| `PORT` | o Railway injeta sozinho. Não defina | não |

> A `DATABASE_URL` vai sem os sinais `<` e `>` em volta da senha. É o erro que já custou uma
> sessão de depuração aqui: o Postgres responde `password authentication failed`, que manda
> procurar a senha errada. Hoje o `servidor.py` falha no boot com uma mensagem clara se sobrar
> `<` na string.

### 3.3. Subir o código

O `railway.json` na raiz já declara tudo o que o build precisa: `builder: DOCKERFILE`,
`deploy/app.Dockerfile`, healthcheck em `/saude` e `sleepApplication`. Um serviço novo só
precisa apontar para a branch `main`; nenhuma variável de build fica no painel.

Se o serviço vier de um desenho anterior, apague qualquer `RAILWAY_DOCKERFILE_PATH` que tenha
sobrado. Ela vence o `railway.json`, e apontando para um arquivo que não existe na branch de
deploy ela quebra o build e derruba o que estava no ar.

Confirme no deploy log:

```
servidor em 0.0.0.0:8080, painel /creche-conectada.html, webhook POST /telegram/…
worker de outbox no ar
```

### 3.4. Apontar o Telegram para lá

```bash
TELEGRAM_WEBHOOK_SECRET=<o mesmo de 3.1> \
  python scripts/configurar_webhook.py https://creche-conectada-production.up.railway.app
python scripts/configurar_webhook.py --ver
```

### 3.5. Conferir

```bash
curl https://creche-conectada-production.up.railway.app/saude          # {"ok": true}
curl https://creche-conectada-production.up.railway.app/api/banco.json # origem: postgres
```

E mandar `/start` para o bot no Telegram.

### 3.6. O que está no ar hoje

Conferido em 2026-08-31 pelos próprios endpoints, não pelo painel da Railway:

| Verificação | Resultado |
|---|---|
| `GET /saude` | `{"ok": true}` |
| `GET /api/banco.json` | 200, `origem: postgres`, schema `creche` |
| `getWebhookInfo` | apontando para `…up.railway.app/telegram/…`, `pending_update_count: 0` |
| Imagem | `deploy/app.Dockerfile`, com `[ia,audio]` e `WHISPER=1` |

Ou seja: é o app completo servindo painel e webhook no mesmo processo, com o Postgres do
Supabase por trás. O painel estático de `site.Dockerfile` saiu.

O que o `railway.json` declara (`sleepApplication`, healthcheck em `/saude`, `ON_FAILURE`,
uma réplica) vale a partir do deploy que o leu. Se você mexer nessas chaves pelo dashboard,
a configuração do painel vence o arquivo, e o repositório passa a mentir sobre o que está
rodando.

### 3.7. Fora da Railway, e ainda aberto

| Item | Estado | Ação |
|---|---|---|
| Bot pode entrar em grupo | `can_join_groups: true` | Desligar no @BotFather: `/setjoingroups` → Disable. O bot recebe documento de criança, e a Bot API não permite mudar isso por código |
| Menu de comandos do Telegram | `/start`, `/status`, `/ajuda`, `/apagar` | `/ia` e `/demo` funcionam e o `/ajuda` os anuncia, mas ficaram fora do menu. Pode ser deliberado: o menu está em linguagem de família |
| Descrições do bot | preenchidas | nada |

## 4. Pendências de código

| # | Pendência | Por quê | Quem |
|---|---|---|---|
| C3 | `ConnectionPool` não fecha limpo no Python 3.14 | Todo processo termina cuspindo `PythonFinalizationError` no log. Cosmético, mas polui | trilha dados |
| C5 | Suíte completa contra o pooler do Supabase | Deadlock no `TRUNCATE` entre arquivos e `prepared statement não existe` na conexão admin do `conftest`, ver [BANCO.md §4](BANCO.md#4-testes) | trilha dados |

Nenhuma das duas bloqueia o deploy.

Quatro pendências saíram desde a primeira versão desta lista, e vale registrar o que era cada
uma. A C1: `servidor.py` chamava `canal._traduzir`, que é privado, e hoje o canal expõe
`Telegram.receber(update)`. A C4: `RedatorClaude.texto()` interpolava o nome da criança sem
delimitador, e agora manda a base dentro de `<mensagem>`, com `<` e `>` removidos antes.
A C6: CEP sem coordenada caía no pino de Curicica, o que dava a uma família de Bangu as
creches de Curicica com distância em metros; hoje devolve "não achei esse CEP", que é pior de
usar e honesto. E a idempotência do webhook: o Telegram reenvia o update quando a resposta
demora ou a conexão cai, sempre com o mesmo `update_id`, e sem guarda a rede tossindo virava
pergunta repetida na tela da família. O `servidor.py` lembra os 2048 mais recentes e descarta
repetição, com trava porque dois reenvios podem chegar em threads diferentes.

## 5. Por que o painel pode ficar público

`api/banco.json` foi auditado: das 30 strings que ele emite, nenhuma é valor de coluna de
pessoa. O que sai é nome de coluna (`nome_crianca`, e não o nome), estado de conversa
(`PROTOCOLO`), código de critério, e nome de creche, que é público e já está nos CSVs abertos.
Nenhum CPF, telefone ou e-mail. As queries em `scripts/painel.py` só fazem `count` e
`count(*) FILTER`.

Se um dia alguém acrescentar uma query que selecione valor, isso deixa de valer. A regra
está escrita no topo de `painel.py`.

A allowlist do servidor entrega só o HTML do painel e os seis CSVs. `.env`, `creche.db`,
`.git/` e qualquer `.py` respondem 404, testado.

## 6. O que já está configurado para não gastar

A Railway cobra por RAM × tempo, CPU × tempo e egresso. As três escolhas abaixo já estão no
repositório, então não há nada a fazer. É só saber que existem.

| Alavanca | O que fizemos | Medido |
|---|---|---|
| Dormir sem tráfego | `sleepApplication: true` no `railway.json` | O serviço hiberna sozinho e acorda no primeiro request. É a maior economia das três |
| Egresso | gzip em memória e `Cache-Control: max-age=3600` | Uma visita ao painel caiu de 951 KB para 278 KB. Com o cache, o F5 não baixa nada |
| CPU ociosa | `OUTBOX_INTERVALO_S=60`, era 5s | 12x menos ciclos de worker, e cada ciclo é uma consulta ao backend mais uma ao banco |

`[audio]` está no build e `WHISPER=1` ligado. O RSS subiu de 36 MB para ~170 MB de biblioteca,
mais o modelo de ~460 MB que baixa uma vez no primeiro boot. Confira o número real em Usage,
no painel da Railway: o preço por GB e por vCPU muda, e não vale decorar aqui um valor que
envelhece.

### O preço de deixar dormir

Enquanto hiberna, o worker de outbox não roda. Na conversa isso não aparece, porque o webhook
acorda o serviço e a plataforma sobe em segundos, dentro dos ~60s que o Telegram espera. Quem
paga a conta são as notificações R1 a R4: elas só saem quando algo acorda o serviço, e se
ninguém conversar nem abrir o painel a noite toda, o aviso de convocação espera até de manhã.

Para demonstração e para o volume de hoje, é o certo. No dia em que houver família de verdade
esperando convocação, troque `"sleepApplication": true` por `false` no `railway.json`. O custo
sobe para o de um serviço ligado 24h, ainda pequeno nesse tamanho, e o aviso passa a sair no
minuto seguinte.

O meio-termo é um cron externo batendo em `/saude` de hora em hora: acorda o worker sem manter
o serviço de pé.

## 7. O que continua fora

- Domínio próprio: hoje é `*.up.railway.app`, e trocar é Settings → Networking no Railway.
- Backup do banco: o Supabase no plano free não faz backup automático diário.
- Observabilidade: o log vai para o stdout do Railway e acabou. Sem métrica, sem alerta.
- Escala: `ThreadingHTTPServer` é uma thread por requisição, o que serve para dezenas
  simultâneas e não para milhares. Com volume real isto vira ASGI atrás de um Uvicorn, e não
  antes disso.

## 8. Voltar para a máquina

Webhook e long polling são exclusivos. Para depurar localmente:

```bash
python scripts/configurar_webhook.py --remover
python -m creche_bot                 # long polling volta a funcionar
```

E para religar, o passo 3.4 de novo.
