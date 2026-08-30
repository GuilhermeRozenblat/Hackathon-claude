"""Repositório em Postgres (Supabase). Substitui o sqlite3 que rodou na validação.

ESTE É O ÚNICO ARQUIVO DO PROJETO QUE ESCREVE SQL.

Três escolhas que valem explicação:

**Schema `creche`, não `public`.** No Supabase o `public` é servido pela Data API
(PostgREST) para quem tem a chave anônima — que costuma acabar no front. Um schema fora
da lista de exposição não é alcançável pela API, ponto: não depende de ninguém lembrar de
manter RLS restritiva numa tabela que guarda nome de criança e CPF. RLS fica ligada mesmo
assim, como segunda linha.

**psycopg direto, sem SQLAlchemy nem Alembic.** São 16 métodos de uma tabela cada, num só
arquivo. Um ORM aqui seria a abstração especulativa que o CLAUDE.md proíbe, e migração
versionada só paga quando o schema para de mudar toda semana. DDL idempotente no boot
custa menos até lá.

**Nome de tabela qualificado em toda query.** Nada de `search_path`: no pooler em modo
transação a conexão troca de sessão embaixo do processo, e um `SET` não sobrevive.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from creche_bot.dados.porta import EventoPendente, Inscricao

log = logging.getLogger(__name__)

MAX_TENTATIVAS = 5

# default=str para data/hora que caia no contexto da sessão sem virar erro no meio do chat.
_json = partial(json.dumps, ensure_ascii=False, default=str)

ESQUEMA = """
CREATE SCHEMA IF NOT EXISTS {s};

CREATE TABLE IF NOT EXISTS {s}.contato (
    id             text PRIMARY KEY,
    criado_em      timestamptz NOT NULL DEFAULT now()
);

-- id_externo NUNCA é chave primária: é esta tabela que faz a mesma pessoa migrar do
-- Telegram para o WhatsApp sem recomeçar o cadastro.
CREATE TABLE IF NOT EXISTS {s}.identidade_canal (
    contato_id     text NOT NULL REFERENCES {s}.contato(id) ON DELETE CASCADE,
    canal          text NOT NULL,
    id_externo     text NOT NULL,
    PRIMARY KEY (canal, id_externo)
);
CREATE INDEX IF NOT EXISTS ix_identidade_contato
    ON {s}.identidade_canal (contato_id);

CREATE TABLE IF NOT EXISTS {s}.consentimento (
    contato_id     text PRIMARY KEY REFERENCES {s}.contato(id) ON DELETE CASCADE,
    versao_texto   text NOT NULL,
    aceito_em      timestamptz NOT NULL DEFAULT now(),
    canal          text NOT NULL,
    id_externo     text NOT NULL
);

CREATE TABLE IF NOT EXISTS {s}.sessao (
    contato_id     text PRIMARY KEY REFERENCES {s}.contato(id) ON DELETE CASCADE,
    estado         text NOT NULL,
    contexto       jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    atualizado_em  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS {s}.inscricao (
    protocolo      text PRIMARY KEY,
    contato_id     text NOT NULL REFERENCES {s}.contato(id) ON DELETE CASCADE,
    id_escola      text NOT NULL,
    nome_escola    text NOT NULL,
    nome_crianca   text NOT NULL,
    etapa_codigo   text,
    criado_em      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_inscricao_contato ON {s}.inscricao (contato_id);

-- Sem FK para contato, de propósito: o expurgo da LGPD apaga por protocolo,
-- explicitamente, e um CASCADE escondido tornaria fácil esquecer disso.
CREATE TABLE IF NOT EXISTS {s}.outbox (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    protocolo      text NOT NULL,
    chave          text NOT NULL,
    variaveis      jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    criado_em      timestamptz NOT NULL DEFAULT now(),
    enviado_em     timestamptz,
    tentativas     smallint NOT NULL DEFAULT 0
);
-- Parcial: o worker só olha o que ainda não saiu, e o que já saiu é a maioria das linhas.
CREATE INDEX IF NOT EXISTS ix_outbox_pendente
    ON {s}.outbox (id) WHERE enviado_em IS NULL;
CREATE INDEX IF NOT EXISTS ix_outbox_protocolo ON {s}.outbox (protocolo);

CREATE TABLE IF NOT EXISTS {s}.marca (
    chave          text PRIMARY KEY,
    valor          text NOT NULL
);

ALTER TABLE {s}.contato           ENABLE ROW LEVEL SECURITY;
ALTER TABLE {s}.identidade_canal  ENABLE ROW LEVEL SECURITY;
ALTER TABLE {s}.consentimento     ENABLE ROW LEVEL SECURITY;
ALTER TABLE {s}.sessao            ENABLE ROW LEVEL SECURITY;
ALTER TABLE {s}.inscricao         ENABLE ROW LEVEL SECURITY;
ALTER TABLE {s}.outbox            ENABLE ROW LEVEL SECURITY;
ALTER TABLE {s}.marca             ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON SCHEMA {s} FROM PUBLIC;

-- Os papéis da Data API só existem no Supabase; em Postgres puro o bloco não faz nada.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        EXECUTE 'REVOKE ALL ON SCHEMA {s} FROM anon, authenticated, service_role';
        EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA {s}'
                ' FROM anon, authenticated, service_role';
    END IF;
END
$$;
"""


def _com_tls(dsn: str) -> str:
    """Sem TLS, CPF e nome de criança atravessam a internet em texto claro."""
    if "sslmode=" in dsn:
        return dsn
    return f"{dsn}{'&' if '?' in dsn else '?'}sslmode=require"


class RepositorioPostgres:
    def __init__(self, dsn: str, *, schema: str = "creche",
                 criar_esquema: bool = True) -> None:
        # O schema vai concatenado na query (nome de objeto não aceita parâmetro).
        # Só nós escolhemos o valor, mas a checagem custa uma linha.
        assert schema.isidentifier(), f"schema inválido: {schema!r}"
        self._s = schema

        self._pool = ConnectionPool(
            _com_tls(dsn),
            min_size=1, max_size=5, timeout=10,
            # prepare_threshold=None: o pooler do Supabase em modo transação (6543) troca
            # a conexão de servidor a cada transação e o prepared statement some.
            kwargs={"row_factory": dict_row, "prepare_threshold": None},
            # O pooler derruba conexão ociosa; sem isso o worker de outbox pega uma morta.
            check=ConnectionPool.check_connection,
            name="creche", open=True,
        )
        if criar_esquema:
            with self._cursor() as cur:
                cur.execute(ESQUEMA.format(s=self._s))

    @contextmanager
    def _cursor(self) -> Iterator[psycopg.Cursor[dict[str, Any]]]:
        """Uma transação por método: o `with` do pool faz commit na saída limpa."""
        with self._pool.connection() as con, con.cursor() as cur:
            yield cur

    def fechar(self) -> None:
        self._pool.close()

    def apagar_esquema(self) -> None:
        """Reset do ambiente: derruba o schema inteiro. Chamado só por `make limpar`.

        Não é o expurgo da LGPD — esse é `apagar_tudo()`, por contato.
        """
        with self._cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {self._s} CASCADE")

    # ------------------------------------------------------------- identidade
    def contato_de(self, canal: str, id_externo: str) -> str:
        with self._pool.connection() as con, con.cursor() as cur:
            cur.execute(
                f"SELECT contato_id FROM {self._s}.identidade_canal"
                " WHERE canal=%s AND id_externo=%s", (canal, id_externo))
            if (linha := cur.fetchone()) is not None:
                return linha["contato_id"]

            # Duas threads escrevem. Perder a corrida aqui criaria um segundo contato e a
            # pessoa perderia a conversa no meio; o savepoint desfaz e relê o vencedor.
            contato_id = str(uuid.uuid4())
            try:
                with con.transaction():
                    cur.execute(f"INSERT INTO {self._s}.contato (id) VALUES (%s)",
                                (contato_id,))
                    cur.execute(
                        f"INSERT INTO {self._s}.identidade_canal"
                        " (contato_id, canal, id_externo) VALUES (%s,%s,%s)",
                        (contato_id, canal, id_externo))
            except psycopg.errors.UniqueViolation:
                cur.execute(
                    f"SELECT contato_id FROM {self._s}.identidade_canal"
                    " WHERE canal=%s AND id_externo=%s", (canal, id_externo))
                return cur.fetchone()["contato_id"]
            return contato_id

    def id_externo_de(self, contato_id: str, canal: str = "telegram") -> str | None:
        with self._cursor() as cur:
            cur.execute(
                f"SELECT id_externo FROM {self._s}.identidade_canal"
                " WHERE contato_id=%s AND canal=%s", (contato_id, canal))
            linha = cur.fetchone()
        return linha["id_externo"] if linha else None

    # ----------------------------------------------------------- consentimento
    def registrar_consentimento(self, contato_id: str, versao: str,
                                canal: str, id_externo: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                f"INSERT INTO {self._s}.consentimento"
                " (contato_id, versao_texto, canal, id_externo) VALUES (%s,%s,%s,%s)"
                " ON CONFLICT (contato_id) DO UPDATE SET"
                " versao_texto=excluded.versao_texto, aceito_em=now(),"
                " canal=excluded.canal, id_externo=excluded.id_externo",
                (contato_id, versao, canal, id_externo))

    def tem_consentimento(self, contato_id: str) -> bool:
        with self._cursor() as cur:
            cur.execute(f"SELECT 1 FROM {self._s}.consentimento WHERE contato_id=%s",
                        (contato_id,))
            return cur.fetchone() is not None

    # ------------------------------------------------------------------ sessão
    def carregar_sessao(self, contato_id: str) -> tuple[str, dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute(f"SELECT estado, contexto FROM {self._s}.sessao WHERE contato_id=%s",
                        (contato_id,))
            linha = cur.fetchone()
        # psycopg monta um dict novo por linha, então já é a cópia que o chamador muta.
        return ("INICIO", {}) if linha is None else (linha["estado"], linha["contexto"])

    def salvar_sessao(self, contato_id: str, estado: str, contexto: dict[str, Any]) -> None:
        with self._cursor() as cur:
            cur.execute(
                f"INSERT INTO {self._s}.sessao (contato_id, estado, contexto)"
                " VALUES (%s,%s,%s)"
                " ON CONFLICT (contato_id) DO UPDATE SET estado=excluded.estado,"
                " contexto=excluded.contexto, atualizado_em=now()",
                (contato_id, estado, Jsonb(contexto, dumps=_json)))

    # --------------------------------------------------------------- inscrição
    def salvar_inscricao(self, inscricao: Inscricao) -> None:
        with self._cursor() as cur:
            cur.execute(
                f"INSERT INTO {self._s}.inscricao (protocolo, contato_id, id_escola,"
                " nome_escola, nome_crianca, etapa_codigo) VALUES (%s,%s,%s,%s,%s,%s)"
                " ON CONFLICT (protocolo) DO UPDATE SET contato_id=excluded.contato_id,"
                " id_escola=excluded.id_escola, nome_escola=excluded.nome_escola,"
                " nome_crianca=excluded.nome_crianca, etapa_codigo=excluded.etapa_codigo",
                (inscricao.protocolo, inscricao.contato_id, inscricao.id_escola,
                 inscricao.nome_escola, inscricao.nome_crianca, inscricao.etapa_codigo))

    def inscricao(self, protocolo: str) -> Inscricao | None:
        with self._cursor() as cur:
            cur.execute(
                f"SELECT protocolo, contato_id, id_escola, nome_escola, nome_crianca,"
                f" etapa_codigo FROM {self._s}.inscricao WHERE protocolo=%s", (protocolo,))
            linha = cur.fetchone()
        return None if linha is None else Inscricao(**linha)

    def atualizar_etapa(self, protocolo: str, etapa_codigo: str) -> None:
        with self._cursor() as cur:
            cur.execute(f"UPDATE {self._s}.inscricao SET etapa_codigo=%s WHERE protocolo=%s",
                        (etapa_codigo, protocolo))

    # ------------------------------------------------------------------ outbox
    def enfileirar(self, protocolo: str, chave: str, variaveis: dict[str, Any]) -> None:
        with self._cursor() as cur:
            cur.execute(
                f"INSERT INTO {self._s}.outbox (protocolo, chave, variaveis)"
                " VALUES (%s,%s,%s)",
                (protocolo, chave, Jsonb(variaveis, dumps=_json)))

    def pendentes(self, limite: int = 50) -> list[EventoPendente]:
        with self._cursor() as cur:
            cur.execute(
                f"SELECT o.id, o.protocolo, i.contato_id, o.chave, o.variaveis"
                f" FROM {self._s}.outbox o JOIN {self._s}.inscricao i USING (protocolo)"
                " WHERE o.enviado_em IS NULL AND o.tentativas < %s"
                " ORDER BY o.id LIMIT %s", (MAX_TENTATIVAS, limite))
            return [EventoPendente(**linha) for linha in cur.fetchall()]

    def marcar_enviado(self, evento_id: int) -> None:
        with self._cursor() as cur:
            cur.execute(f"UPDATE {self._s}.outbox SET enviado_em=now() WHERE id=%s",
                        (evento_id,))

    def marcar_falha(self, evento_id: int) -> None:
        with self._cursor() as cur:
            cur.execute(
                f"UPDATE {self._s}.outbox SET tentativas=tentativas+1 WHERE id=%s",
                (evento_id,))

    # ------------------------------------------------------------ marca d'água
    def ler_marca(self, chave: str) -> str | None:
        with self._cursor() as cur:
            cur.execute(f"SELECT valor FROM {self._s}.marca WHERE chave=%s", (chave,))
            linha = cur.fetchone()
        return linha["valor"] if linha else None

    def gravar_marca(self, chave: str, valor: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                f"INSERT INTO {self._s}.marca (chave, valor) VALUES (%s,%s)"
                " ON CONFLICT (chave) DO UPDATE SET valor=excluded.valor", (chave, valor))

    # -------------------------------------------------------------------- LGPD
    def apagar_tudo(self, contato_id: str) -> int:
        """Direito de eliminação (LGPD art. 18), numa transação só.

        A outbox não tem FK para contato: se ela não for apagada aqui, sobra fila com
        nome de criança dentro depois que a pessoa pediu para sumir.
        """
        with self._cursor() as cur:
            cur.execute(
                f"DELETE FROM {self._s}.outbox WHERE protocolo IN"
                f" (SELECT protocolo FROM {self._s}.inscricao WHERE contato_id=%s)",
                (contato_id,))
            cur.execute(f"DELETE FROM {self._s}.contato WHERE id=%s", (contato_id,))
            return cur.rowcount
