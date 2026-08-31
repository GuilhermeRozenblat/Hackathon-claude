"""A conversa roda contra a implementação em memória, e só ela.

O conftest da raiz parametriza `repo` nas DUAS implementações, e é assim que a paridade
entre `RepositorioMemoria` e `RepositorioPostgres` é cobrada — em `tests/dados`, que existe
para isso e exercita a porta inteira, cadastro e preferências incluídos.

Aqui o objeto de teste é o ROTEIRO. Repetir cada turno contra um Postgres remoto multiplica
a bateria por cem (8 minutos contra 8 segundos), e ainda por cima cada teste precisaria de um
`TRUNCATE` que disputa lock com o pool que o teste anterior deixou vivo — que é de onde vinham
os deadlocks. Nada disso cobre uma linha de conversa a mais.
"""

from __future__ import annotations

import pytest

from creche_bot.dados.memoria import RepositorioMemoria


@pytest.fixture
def repo():
    return RepositorioMemoria()
