.PHONY: servidor webhook bot memoria roteiro debug painel painel-snapshot fronteira test contratos seguranca conversa canal ia dados backend notificacao lint limpar banco esquema up demo demo-limpar

bot:          ; python -m creche_bot
memoria:      ; REPOSITORIO=memoria python -m creche_bot   # roda sem banco nenhum
roteiro:      ; BACKEND=mock python -m creche_bot          # as 3 escolas fixas do roteiro
debug:        ; DEBUG_CONTEUDO=1 python -m creche_bot      # espelha a conversa no console
servidor:     ; python scripts/servidor.py                # painel + webhook, como na hospedagem
webhook:      ; python scripts/configurar_webhook.py --ver # o que o Telegram tem registrado
verificar:    ; python scripts/verificar_telegram.py
eco:          ; python scripts/verificar_telegram.py --eco
demo:         ; python scripts/semear_demo.py              # enche o banco para a demonstração
demo-limpar:  ; python scripts/semear_demo.py --apagar
banco:        ; python scripts/verificar_banco.py          # aplica o schema e testa a porta
esquema:      ; python scripts/verificar_banco.py --esquema
up:           ; docker compose up -d                       # Postgres local, alternativa ao Supabase

painel:          ; python scripts/painel.py             # serve o painel + /api/banco.json
painel-snapshot: ; python scripts/painel.py --snapshot  # congela o retrato do banco no HTML

test:         ; python -m pytest -q
contratos:    ; python -m pytest tests/test_contratos.py -q
seguranca:    ; python -m pytest tests/test_seguranca.py -q
canal:        ; python -m pytest tests/canal -q
conversa:     ; python -m pytest tests/conversa -q
ia:           ; python -m pytest tests/ia -q
dados:        ; python -m pytest tests/dados -q
backend:      ; python -m pytest tests/backend -q
notificacao:  ; python -m pytest tests/notificacao -q

fronteira:    ; python -m pytest tests/test_contratos.py -q -k 'vaza or porta'
lint:         ; ruff check creche_bot fakes tests scripts
limpar:       ; python scripts/verificar_banco.py --apagar   # derruba o schema inteiro
