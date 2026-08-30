"""Repositório em sqlite3. É o padrão hoje e o ponto de partida do Postgres.

# ponytail: sqlite3 da stdlib. Roda sem docker, sem pip install, sem migração.
# Trocar por Postgres+SQLAlchemy quando houver mais de um processo escrevendo, ou quando
# `sessao.contexto` precisar de query por campo. A troca não vaza: quem consome só
# conhece `porta.Repositorio` — veja creche_bot/dados/CLAUDE.md (Trilha D1).

ESTE É O ÚNICO ARQUIVO DO PROJETO QUE ESCREVE SQL.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from creche_bot.dados.porta import EventoPendente, Inscricao

MAX_TENTATIVAS = 5

ESQUEMA = """
CREATE TABLE IF NOT EXISTS contato (
    id            TEXT PRIMARY KEY,
    criado_em     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS identidade_canal (
    contato_id    TEXT NOT NULL REFERENCES contato(id) ON DELETE CASCADE,
    canal         TEXT NOT NULL,
    id_externo    TEXT NOT NULL,
    PRIMARY KEY (canal, id_externo)
);
CREATE TABLE IF NOT EXISTS consentimento (
    contato_id    TEXT PRIMARY KEY REFERENCES contato(id) ON DELETE CASCADE,
    versao_texto  TEXT NOT NULL,
    aceito_em     TEXT NOT NULL DEFAULT (datetime('now')),
    canal         TEXT NOT NULL,
    id_externo    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessao (
    contato_id    TEXT PRIMARY KEY REFERENCES contato(id) ON DELETE CASCADE,
    estado        TEXT NOT NULL,
    contexto      TEXT NOT NULL DEFAULT '{}',
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS inscricao (
    protocolo     TEXT PRIMARY KEY,
    contato_id    TEXT NOT NULL REFERENCES contato(id) ON DELETE CASCADE,
    id_escola     TEXT NOT NULL,
    nome_escola   TEXT NOT NULL,
    nome_crianca  TEXT NOT NULL,
    etapa_codigo  TEXT,
    criado_em     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS outbox (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    protocolo     TEXT NOT NULL,
    chave         TEXT NOT NULL,
    variaveis     TEXT NOT NULL,
    criado_em     TEXT NOT NULL DEFAULT (datetime('now')),
    enviado_em    TEXT,
    tentativas    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_outbox_pendente ON outbox(enviado_em) WHERE enviado_em IS NULL;
CREATE TABLE IF NOT EXISTS marca (chave TEXT PRIMARY KEY, valor TEXT);
"""


class RepositorioSQLite:
    def __init__(self, caminho: str | Path = "creche.db") -> None:
        # check_same_thread=False: o worker de outbox roda em thread separada do polling.
        self._con = sqlite3.connect(str(caminho), check_same_thread=False,
                                    isolation_level=None)
        self._con.row_factory = sqlite3.Row
        self._con.execute("PRAGMA foreign_keys = ON")
        self._con.execute("PRAGMA journal_mode = WAL")   # leitor não bloqueia escritor
        self._con.executescript(ESQUEMA)

    def fechar(self) -> None:
        self._con.close()

    # ------------------------------------------------------------- identidade
    def contato_de(self, canal: str, id_externo: str) -> str:
        linha = self._con.execute(
            "SELECT contato_id FROM identidade_canal WHERE canal=? AND id_externo=?",
            (canal, id_externo),
        ).fetchone()
        if linha:
            return linha["contato_id"]

        contato_id = str(uuid.uuid4())
        self._con.execute("INSERT INTO contato (id) VALUES (?)", (contato_id,))
        self._con.execute(
            "INSERT INTO identidade_canal (contato_id, canal, id_externo) VALUES (?,?,?)",
            (contato_id, canal, id_externo),
        )
        return contato_id

    def id_externo_de(self, contato_id: str, canal: str = "telegram") -> str | None:
        linha = self._con.execute(
            "SELECT id_externo FROM identidade_canal WHERE contato_id=? AND canal=?",
            (contato_id, canal),
        ).fetchone()
        return linha["id_externo"] if linha else None

    # ----------------------------------------------------------- consentimento
    def registrar_consentimento(self, contato_id: str, versao: str,
                                canal: str, id_externo: str) -> None:
        self._con.execute(
            "INSERT OR REPLACE INTO consentimento"
            " (contato_id, versao_texto, canal, id_externo) VALUES (?,?,?,?)",
            (contato_id, versao, canal, id_externo),
        )

    def tem_consentimento(self, contato_id: str) -> bool:
        return self._con.execute(
            "SELECT 1 FROM consentimento WHERE contato_id=?", (contato_id,)
        ).fetchone() is not None

    # ------------------------------------------------------------------ sessão
    def carregar_sessao(self, contato_id: str) -> tuple[str, dict[str, Any]]:
        linha = self._con.execute(
            "SELECT estado, contexto FROM sessao WHERE contato_id=?", (contato_id,)
        ).fetchone()
        return ("INICIO", {}) if not linha else (linha["estado"], json.loads(linha["contexto"]))

    def salvar_sessao(self, contato_id: str, estado: str, contexto: dict[str, Any]) -> None:
        self._con.execute(
            "INSERT INTO sessao (contato_id, estado, contexto) VALUES (?,?,?)"
            " ON CONFLICT(contato_id) DO UPDATE SET estado=excluded.estado,"
            " contexto=excluded.contexto, atualizado_em=datetime('now')",
            (contato_id, estado, json.dumps(contexto, ensure_ascii=False, default=str)),
        )

    # --------------------------------------------------------------- inscrição
    def salvar_inscricao(self, inscricao: Inscricao) -> None:
        self._con.execute(
            "INSERT OR REPLACE INTO inscricao (protocolo, contato_id, id_escola,"
            " nome_escola, nome_crianca, etapa_codigo) VALUES (?,?,?,?,?,?)",
            (inscricao.protocolo, inscricao.contato_id, inscricao.id_escola,
             inscricao.nome_escola, inscricao.nome_crianca, inscricao.etapa_codigo),
        )

    def inscricao(self, protocolo: str) -> Inscricao | None:
        linha = self._con.execute(
            "SELECT * FROM inscricao WHERE protocolo=?", (protocolo,)
        ).fetchone()
        if not linha:
            return None
        return Inscricao(linha["protocolo"], linha["contato_id"], linha["id_escola"],
                         linha["nome_escola"], linha["nome_crianca"], linha["etapa_codigo"])

    def atualizar_etapa(self, protocolo: str, etapa_codigo: str) -> None:
        self._con.execute("UPDATE inscricao SET etapa_codigo=? WHERE protocolo=?",
                          (etapa_codigo, protocolo))

    # ------------------------------------------------------------------ outbox
    def enfileirar(self, protocolo: str, chave: str, variaveis: dict[str, Any]) -> None:
        self._con.execute(
            "INSERT INTO outbox (protocolo, chave, variaveis) VALUES (?,?,?)",
            (protocolo, chave, json.dumps(variaveis, ensure_ascii=False, default=str)),
        )

    def pendentes(self, limite: int = 50) -> list[EventoPendente]:
        linhas = self._con.execute(
            "SELECT o.id, o.protocolo, o.chave, o.variaveis, i.contato_id"
            " FROM outbox o JOIN inscricao i USING (protocolo)"
            " WHERE o.enviado_em IS NULL AND o.tentativas < ?"
            " ORDER BY o.id LIMIT ?", (MAX_TENTATIVAS, limite),
        ).fetchall()
        return [EventoPendente(x["id"], x["protocolo"], x["contato_id"], x["chave"],
                               json.loads(x["variaveis"])) for x in linhas]

    def marcar_enviado(self, evento_id: int) -> None:
        self._con.execute("UPDATE outbox SET enviado_em=datetime('now') WHERE id=?",
                          (evento_id,))

    def marcar_falha(self, evento_id: int) -> None:
        self._con.execute("UPDATE outbox SET tentativas=tentativas+1 WHERE id=?",
                          (evento_id,))

    # ------------------------------------------------------------ marca d'água
    def ler_marca(self, chave: str) -> str | None:
        linha = self._con.execute("SELECT valor FROM marca WHERE chave=?",
                                  (chave,)).fetchone()
        return linha["valor"] if linha else None

    def gravar_marca(self, chave: str, valor: str) -> None:
        self._con.execute(
            "INSERT INTO marca (chave, valor) VALUES (?,?)"
            " ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, valor))

    # -------------------------------------------------------------------- LGPD
    def apagar_tudo(self, contato_id: str) -> int:
        protocolos = [r["protocolo"] for r in self._con.execute(
            "SELECT protocolo FROM inscricao WHERE contato_id=?", (contato_id,))]
        for p in protocolos:                    # outbox não tem FK para contato
            self._con.execute("DELETE FROM outbox WHERE protocolo=?", (p,))
        return self._con.execute("DELETE FROM contato WHERE id=?", (contato_id,)).rowcount
