"""Fixture única de repositório: todo teste roda contra as DUAS implementações.

`RepositorioMemoria` é a referência de comportamento. Se o Postgres divergir dela em
qualquer detalhe — cópia de dict, ordem da fila, órfão depois do expurgo — o teste acusa
aqui, e não em produção no meio de uma conversa.

Sem `DATABASE_URL_TESTE` (ou `DATABASE_URL`), a metade Postgres é pulada: quem trabalha em
canal e conversa não fica bloqueado por banco. Veja docs/BANCO.md.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from creche_bot.dados.memoria import RepositorioMemoria
from creche_bot.segredos import carregar_env

# O pytest não lê o .env sozinho, e sem isto a metade Postgres seria pulada em silêncio
# mesmo com o banco configurado. `carregar_env` usa setdefault: variável de ambiente de
# verdade continua ganhando, o que mantém o CI no comando.
_ENV = Path(__file__).resolve().parent.parent / ".env"
if _ENV.exists():
    carregar_env(_ENV)

# Schema próprio: o teste TRUNCATE tudo que enxerga, e apontar isso para os dados reais
# de uma inscrição seria destruição silenciosa.
SCHEMA_TESTE = "creche_teste"

TABELAS = ("contato", "identidade_canal", "consentimento", "sessao",
           "inscricao", "outbox", "marca")


@pytest.fixture(scope="session")
def _postgres():
    dsn = os.environ.get("DATABASE_URL_TESTE") or os.environ.get("DATABASE_URL", "")
    if not dsn or dsn.startswith("coloque"):    # o placeholder do .env.example é truthy
        pytest.skip("sem DATABASE_URL_TESTE — rodando só a implementação em memória")

    psycopg = pytest.importorskip("psycopg", reason="psycopg não instalado")
    from creche_bot.dados.postgres import RepositorioPostgres, _com_tls

    repositorio = RepositorioPostgres(dsn, schema=SCHEMA_TESTE)
    admin = psycopg.connect(_com_tls(dsn), autocommit=True)
    yield repositorio, admin

    admin.execute(f"DROP SCHEMA IF EXISTS {SCHEMA_TESTE} CASCADE")
    admin.close()
    repositorio.fechar()


@pytest.fixture(params=["memoria", "postgres"])
def repo(request):
    if request.param == "memoria":
        return RepositorioMemoria()

    repositorio, admin = request.getfixturevalue("_postgres")
    # RESTART IDENTITY: o id da outbox recomeça em 1, como no `itertools.count` da
    # implementação em memória. Sem isso as duas divergem já no primeiro evento.
    alvos = ", ".join(f"{SCHEMA_TESTE}.{t}" for t in TABELAS)
    admin.execute(f"TRUNCATE {alvos} RESTART IDENTITY CASCADE")
    return repositorio
