"""O contexto que atravessa um passo. Objeto pequeno de propósito: handler recebe isto,
devolve uma MensagemSaida, e no máximo pede uma mudança de estado."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from creche_bot.backend.porta import BackendCreche
from creche_bot.canal.tipos import Botao, ItemLista, Local, MensagemEntrada, MensagemSaida
from creche_bot.dados.porta import Repositorio
from creche_bot.ia.persona import FIGURINHAS
from creche_bot.ia.redacao import Redator


def dizer(redator: Redator, chave: str, *, prefixo: str = "",
          botoes: tuple[Botao, ...] = (), lista: tuple[ItemLista, ...] = (),
          local: Local | None = None, **vars: Any) -> MensagemSaida:
    """Texto do roteiro + a figurinha que combina com a situação.

    A figurinha vem do mapa em `persona.py`, junto do texto — assim ninguém precisa
    lembrar de escolher emoji em 40 lugares, e mudar o tom é mexer num arquivo só.
    """
    return MensagemSaida(prefixo + redator.texto(chave, **vars), botoes=botoes,
                         lista=lista, local=local, figurinha=FIGURINHAS.get(chave))


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

    def diz(self, chave: str, **kw: Any) -> MensagemSaida:
        """`txt` quando a mensagem é só aquele texto — e aí ela ganha a figurinha."""
        return dizer(self.redator, chave, **kw)

    @property
    def texto(self) -> str:
        return (self.msg.texto or "").strip()
