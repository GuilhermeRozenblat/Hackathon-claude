"""O contexto que atravessa um passo. Objeto pequeno de propósito: handler recebe isto,
devolve uma MensagemSaida, e no máximo pede uma mudança de estado."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from creche_bot.backend.porta import BackendCreche
from creche_bot.canal.tipos import MensagemEntrada
from creche_bot.dados.porta import Repositorio
from creche_bot.ia.redacao import Redator


@dataclass
class Passo:
    msg: MensagemEntrada
    contato_id: str
    dados: dict[str, Any]
    backend: BackendCreche
    redator: Redator
    repo: Repositorio
    proximo: str | None = field(default=None)

    def ir(self, estado: str) -> None:
        self.proximo = estado

    def txt(self, chave: str, **vars: Any) -> str:
        return self.redator.texto(chave, **vars)

    @property
    def texto(self) -> str:
        return (self.msg.texto or "").strip()
