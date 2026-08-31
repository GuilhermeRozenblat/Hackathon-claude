"""Fixture única de repositório: todo teste roda contra as DUAS implementações.

`RepositorioMemoria` é a referência de comportamento. Se o Postgres divergir dela em
qualquer detalhe (cópia de dict, ordem da fila, órfão depois do expurgo) o teste acusa
aqui, e não em produção no meio de uma conversa.

Sem `DATABASE_URL`, a metade Postgres é pulada: quem trabalha em canal e conversa não fica
bloqueado por banco. Veja docs/BANCO.md.
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

# Schema próprio: o teste apaga tudo que enxerga, e apontar isso para os dados reais de uma
# inscrição seria destruição silenciosa.
SCHEMA_TESTE = "creche_teste"

# As onze, explícitas: truncar a lista inteira num comando só dispensa o CASCADE, que era
# quem pegava lock em tabela fora da lista, em ordem imprevisível, e travava com o pool.
TABELAS = ("contato", "identidade_canal", "consentimento", "sessao", "cadastro",
           "resposta_criterio", "preferencia_escola", "inscricao", "evento_inscricao",
           "outbox", "marca")


@pytest.fixture(scope="session")
def _postgres():
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn or dsn.startswith("coloque"):    # o placeholder do .env.example é truthy
        pytest.skip("sem DATABASE_URL, rodando só a implementação em memória")

    psycopg = pytest.importorskip("psycopg", reason="psycopg não instalado")
    from creche_bot.dados.postgres import RepositorioPostgres, _com_tls

    repositorio = RepositorioPostgres(dsn, schema=SCHEMA_TESTE)
    # `prepare_threshold=None` pelo mesmo motivo do pool: o pooler em modo transação troca
    # a conexão de servidor embaixo do processo, e o prepared statement some com ela. Sem
    # isto a limpeza morre em `prepared statement "_pg3_0" does not exist` no meio da
    # bateria, e o erro aparece no teste seguinte, não onde nasceu.
    admin = psycopg.connect(_com_tls(dsn), autocommit=True, prepare_threshold=None)
    yield repositorio, admin

    admin.execute(f"DROP SCHEMA IF EXISTS {SCHEMA_TESTE} CASCADE")
    admin.close()
    repositorio.fechar()


@pytest.fixture(params=["memoria", "postgres"])
def repo(request):
    if request.param == "memoria":
        return RepositorioMemoria()

    repositorio, admin = request.getfixturevalue("_postgres")
    # Um comando, uma ida ao banco, sem CASCADE: o `CASCADE` alcançava tabela fora da
    # lista e pegava lock em ordem imprevisível, que era de onde vinha o `DeadlockDetected`
    # quando a bateria de conversa também escrevia. `DELETE` no lugar disto evita o lock
    # exclusivo, mas deixa tupla morta e a bateria vai ficando mais lenta a cada rodada.
    #
    # RESTART IDENTITY: o id da outbox recomeça em 1, como no `itertools.count` da
    # implementação em memória. Sem isso as duas divergem já no primeiro evento.
    alvos = ", ".join(f"{SCHEMA_TESTE}.{t}" for t in TABELAS)
    admin.execute(f"TRUNCATE {alvos} RESTART IDENTITY")
    return repositorio
