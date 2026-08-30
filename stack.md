# Stack — Zé Matrícula

Regra que explica quase tudo abaixo: **rodar o bot não exige dependência nenhuma**.
Canal, conversa, persistência e notificação usam só a stdlib do Python. Tudo que é
biblioteca externa é opcional (`extras`) e o sistema funciona sem ela.

## Runtime

| O quê | Versão | Onde |
|---|---|---|
| Python | >= 3.12 | `pyproject.toml` |
| Empacotamento | setuptools + `pip install -e .` | `pyproject.toml` |

## Núcleo — só stdlib

| Módulo | Para quê | Onde |
|---|---|---|
| `urllib.request` | Cliente HTTP da Telegram Bot API (6 métodos, long polling) | `canal/telegram.py` |
| `psycopg` 3 | Postgres do Supabase. Único arquivo do projeto que escreve SQL | `dados/postgres.py` |
| `json` | Payload do Telegram e campos livres no banco | `canal/`, `dados/` |
| `threading` | Worker do outbox ao lado do polling | `__main__.py`, `notificacao/outbox.py` |
| `logging` | Log com formatador que redige segredo em mensagem e traceback | `segredos.py` |
| `dataclasses` + `typing` (`Protocol`) | Contratos congelados e portas (backend, dados) | `dominio/`, `*/porta.py` |
| `re` | Guardrails de saída do modelo, validação de entrada | `ia/redacao.py` |
| `pathlib`, `os`, `stat` | `.env` com permissão 0600, banco 0600 | `segredos.py` |

## Dependências opcionais (`extras`)

| Extra | Pacote | Para quê | Sem ele |
|---|---|---|---|
| `ia` | `anthropic>=0.40` | `RedatorClaude`: variação de linguagem e resposta a dúvida solta. Modelo **`claude-haiku-4-5`** (elegível a ZDR — nunca Fable/Mythos) | cai para `RedatorEstatico`, textos escritos à mão em `ia/persona.py` |
| `audio` | `faster-whisper>=1.0` | Transcrição de áudio **local**, CPU, `int8`, modelo `small` (`WHISPER_MODELO`). A voz da família não sai da máquina | bot pede para a pessoa escrever |
| `postgres` | `sqlalchemy>=2.0`, `psycopg[binary]>=3.2`, `alembic>=1.13` | Trilha D1, ainda **não usado em código** — o repositório Postgres entra pela mesma `dados/porta.py` | roda em SQLite |
| `dev` | `pytest>=8`, `ruff>=0.7`, `pydantic>=2.9` | Testes e lint | — |

## Serviços externos

| Serviço | Como | Observação |
|---|---|---|
| Telegram Bot API | HTTPS, long polling (sem webhook, sem HTTPS local, sem ngrok) | token do @BotFather em `TELEGRAM_TOKEN`; viaja no caminho da URL — por isso o formatador de log |
| Anthropic Messages API | `/v1/messages`, imagem base64 inline | Proibidos: `client.files.*`, Batch API, code execution, MCP connector, Managed Agents — nenhum é elegível a ZDR |
| Backend da Matrícula Rio | `backend/porta.py`, 16 operações | hoje `BackendMock`; amanhã `BackendHTTP`. Régua, endereço por CEP e escolas vêm dele |
| WhatsApp Business | ainda não | os limites dele (3 botões, 10 itens, rótulo de 20 chars, texto puro) já valem no código Telegram |

## Infra

| O quê | Detalhe |
|---|---|
| Docker Compose | `postgres:16-alpine`, publicado só em `127.0.0.1:5432`, volume `pgdata` |
| Banco padrão | arquivo `creche.db` (SQLite, chmod 0600) |
| Sem disco | `REPOSITORIO=memoria` → `RepositorioMemoria` |
| Config | `.env` (chmod 0600) lido por `segredos.py`; sem biblioteca de config |

## Ferramentas de desenvolvimento

| O quê | Detalhe |
|---|---|
| pytest | sem fixture elaborada, sem plugin; suítes por trilha |
| ruff | `line-length = 100`, regras `E, F, I, UP, B, SIM, RUF` |
| make | `bot`, `memoria`, `debug`, `test`, `contratos`, `fronteira`, `lint` e uma alvo por trilha |
| Fakes | `fakes/canal_fake.py`, `fakes/ia_fake.py` — sem mock framework |
| Agentes | Claude Code (`CLAUDE.md` por pasta, `.claude/skills`), `skills-lock.json`, hooks em `.codex/` |

## O que foi deliberadamente deixado de fora

| Não usamos | Por quê |
|---|---|
| `python-telegram-bot` / aiogram | async contaminaria `conversa/`, `ia/` e `dados/` inteiras; a Bot API que usamos são 6 métodos |
| requests / httpx | `urllib` já faz |
| Framework web (FastAPI, Flask) | long polling não precisa de servidor HTTP |
| ORM no caminho padrão | SQLite direto; a troca não vaza porque todo mundo só conhece `dados/porta.py` |
| Redis / Celery | o outbox é uma tabela + uma thread |
| Serviço de transcrição na nuvem | quebraria a regra de privacidade (dado de criança, ZDR) |
| Sticker pack do Telegram | emoji resolve durante a validação (`canal/figurinhas.py`) |
