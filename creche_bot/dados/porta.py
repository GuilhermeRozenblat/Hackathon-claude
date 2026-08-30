"""CONTRATO CONGELADO — Fase 0.2. A fronteira com a persistência.

Quem trabalha no canal, na conversa ou na notificação **nunca** conhece banco. Não há
`sqlite3`, `SELECT`, `session` nem `connection` fora das implementações desta porta.

Duas implementações hoje:
  · `memoria.RepositorioMemoria` — zero dependência, zero setup. É o que garante que o
    trabalho de Telegram nunca fica bloqueado por uma refatoração no banco.
  · `sqlite.RepositorioSQLite`  — o que roda por padrão; ponto de partida do Postgres.

Adicionar campo aqui = PR próprio. Todo mundo depende deste arquivo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class Inscricao:
    protocolo: str
    contato_id: str
    id_escola: str
    nome_escola: str
    nome_crianca: str
    etapa_codigo: str | None = None


@dataclass(frozen=True)
class EventoPendente:
    """Uma linha da outbox pronta para entregar. `id` é o que marca enviado/falha."""
    id: int
    protocolo: str
    contato_id: str
    chave: str
    variaveis: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Repositorio(Protocol):
    # ------------------------------------------------------------- identidade
    def contato_de(self, canal: str, id_externo: str) -> str:
        """UUID interno do contato, criando na primeira mensagem. Idempotente.

        `id_externo` NUNCA é chave primária: é isso que faz a mesma pessoa migrar do
        Telegram para o WhatsApp sem perder o cadastro.
        """

    def id_externo_de(self, contato_id: str, canal: str = "telegram") -> str | None: ...

    # ----------------------------------------------------------- consentimento
    def registrar_consentimento(
        self, contato_id: str, versao: str, canal: str, id_externo: str
    ) -> None: ...

    def tem_consentimento(self, contato_id: str) -> bool: ...

    # ------------------------------------------------------------------ sessão
    def carregar_sessao(self, contato_id: str) -> tuple[str, dict[str, Any]]:
        """(estado, contexto). Contato sem sessão devolve ("INICIO", {})."""

    def salvar_sessao(self, contato_id: str, estado: str, contexto: dict[str, Any]) -> None: ...

    # --------------------------------------------------------------- inscrição
    def salvar_inscricao(self, inscricao: Inscricao) -> None: ...

    def inscricao(self, protocolo: str) -> Inscricao | None: ...

    def atualizar_etapa(self, protocolo: str, etapa_codigo: str) -> None: ...

    # ------------------------------------------------------------------ outbox
    def enfileirar(self, protocolo: str, chave: str, variaveis: dict[str, Any]) -> None: ...

    def pendentes(self, limite: int = 50) -> list[EventoPendente]:
        """Eventos não entregues que ainda não estouraram o teto de tentativas."""

    def marcar_enviado(self, evento_id: int) -> None: ...

    def marcar_falha(self, evento_id: int) -> None: ...

    # ------------------------------------------------------------ marca d'água
    def ler_marca(self, chave: str) -> str | None: ...

    def gravar_marca(self, chave: str, valor: str) -> None: ...

    # -------------------------------------------------------------------- LGPD
    def apagar_tudo(self, contato_id: str) -> int:
        """Direito de eliminação (LGPD art. 18). Não pode deixar órfão em lugar nenhum."""
