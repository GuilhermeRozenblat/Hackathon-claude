.PHONY: bot memoria fronteira test contratos seguranca conversa canal ia dados backend notificacao lint limpar

bot:          ; python -m creche_bot
memoria:      ; REPOSITORIO=memoria python -m creche_bot   # roda sem tocar em disco
verificar:    ; python scripts/verificar_telegram.py
eco:          ; python scripts/verificar_telegram.py --eco

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
limpar:       ; rm -f creche.db creche.db-wal creche.db-shm
