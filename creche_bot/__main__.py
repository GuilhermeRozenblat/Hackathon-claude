"""Sobe o bot: polling do Telegram na thread principal, worker de outbox ao lado.

    python -m creche_bot
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path

from creche_bot.backend.mapa import BackendMapa
from creche_bot.backend.mock import BackendMock
from creche_bot.backend.porta import BackendCreche
from creche_bot.canal.telegram import Telegram
from creche_bot.conversa.maquina import Maquina
from creche_bot.dados.memoria import RepositorioMemoria
from creche_bot.dados.porta import Repositorio
from creche_bot.dados.postgres import RepositorioPostgres
from creche_bot.ia.redacao import RedatorEstatico
from creche_bot.ia.transcricao import Transcritor
from creche_bot.notificacao.outbox import rodar_worker
from creche_bot.segredos import carregar_env, configurar_log

RAIZ = Path(__file__).resolve().parent.parent


def escolher_repositorio() -> Repositorio:
    """REPOSITORIO=memoria roda o bot sem banco nenhum.

    É a válvula de escape: quem trabalha em canal e conversa continua rodando mesmo com o
    Postgres fora do ar ou no meio de uma migração.
    """
    if os.environ.get("REPOSITORIO", "").lower() == "memoria":
        return RepositorioMemoria()

    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn or dsn.startswith("coloque"):
        sys.exit("DATABASE_URL não configurado no .env. Veja docs/BANCO.md "
                 "(ou rode com REPOSITORIO=memoria)")
    # `<` sobrando é o placeholder do BANCO.md que não foi substituído inteiro. O Postgres
    # responderia "password authentication failed", que manda procurar a senha errada.
    if "<" in dsn:
        sys.exit("DATABASE_URL ainda tem <...> do exemplo. Os sinais < e > marcam o "
                 "buraco e saem junto com ele. Veja docs/BANCO.md")
    return RepositorioPostgres(dsn)


def escolher_backend() -> BackendCreche:
    """`BackendMapa` é o padrão: oferta real, das 820 creches de `MapaFilaCreche/`.

    `BACKEND=mock` volta para as três escolas inventadas do roteiro, e serve para demo
    determinística e é o que a bateria de testes usa. Quando o `BackendHTTP` do município
    subir, ele entra aqui e as duas opções saem.
    """
    if os.environ.get("BACKEND", "").lower() == "mock":
        return BackendMock()
    return BackendMapa()


def main() -> None:
    carregar_env(RAIZ / ".env")
    configurar_log()
    token = os.environ.get("TELEGRAM_TOKEN", "")
    if not token or token.startswith("coloque"):
        sys.exit("TELEGRAM_TOKEN não configurado no .env. Veja TELEGRAM.md")

    repo = escolher_repositorio()
    backend = escolher_backend()
    # A IA é opcional e por conta de quem usa: cada contato liga a dele com `/ia`, e o
    # bot não gasta a chave de quem hospeda. Sem chave, valem os textos prontos.
    redator = RedatorEstatico()
    canal = Telegram(token)
    transcritor = Transcritor()
    maquina = Maquina(backend, redator, repo, transcritor)

    for nome, obj in (("repositório", repo), ("backend", backend), ("redator", redator)):
        logging.info("%s: %s", nome, type(obj).__name__)

    threading.Thread(target=rodar_worker, args=(backend, canal, repo), daemon=True).start()
    # O modelo de voz aquece em paralelo: no primeiro boot ele baixa ~460 MB, e o polling
    # é síncrono. Áudio que chegar antes de ficar pronto vira pedido para escrever.
    threading.Thread(target=transcritor.carregar, daemon=True).start()

    try:
        canal.rodar(maquina.processar)
    except KeyboardInterrupt:
        logging.info("encerrado.")


if __name__ == "__main__":
    main()
