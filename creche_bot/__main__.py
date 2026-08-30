"""Sobe o bot: polling do Telegram na thread principal, worker de outbox ao lado.

    python -m creche_bot
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path

from creche_bot.backend.mock import BackendMock
from creche_bot.canal.telegram import Telegram
from creche_bot.conversa.maquina import Maquina
from creche_bot.dados.memoria import RepositorioMemoria
from creche_bot.dados.porta import Repositorio
from creche_bot.dados.sqlite import RepositorioSQLite
from creche_bot.ia.redacao import criar
from creche_bot.ia.transcricao import Transcritor
from creche_bot.notificacao.outbox import rodar_worker
from creche_bot.segredos import carregar_env, configurar_log

RAIZ = Path(__file__).resolve().parent.parent


def escolher_repositorio() -> Repositorio:
    """REPOSITORIO=memoria roda o bot sem tocar em disco.

    É a válvula de escape: se `dados/sqlite.py` estiver no meio de uma refatoração para
    Postgres, o trabalho de canal e conversa continua rodando.
    """
    if os.environ.get("REPOSITORIO", "").lower() == "memoria":
        return RepositorioMemoria()

    caminho = RAIZ / "creche.db"
    repo = RepositorioSQLite(caminho)
    caminho.chmod(0o600)   # o arquivo guarda CPF, nome de criança e telefone
    return repo


def main() -> None:
    carregar_env(RAIZ / ".env")
    configurar_log()
    token = os.environ.get("TELEGRAM_TOKEN", "")
    if not token or token.startswith("coloque"):
        sys.exit("TELEGRAM_TOKEN não configurado no .env — veja TELEGRAM.md")

    repo = escolher_repositorio()
    backend = BackendMock()          # troque por BackendHTTP quando o backend real subir
    redator = criar(os.environ.get("ANTHROPIC_API_KEY") or None)
    canal = Telegram(token)
    maquina = Maquina(backend, redator, repo, Transcritor())

    for nome, obj in (("repositório", repo), ("backend", backend), ("redator", redator)):
        logging.info("%s: %s", nome, type(obj).__name__)

    threading.Thread(target=rodar_worker, args=(backend, canal, repo), daemon=True).start()

    try:
        canal.rodar(maquina.processar)
    except KeyboardInterrupt:
        logging.info("encerrado.")


if __name__ == "__main__":
    main()
