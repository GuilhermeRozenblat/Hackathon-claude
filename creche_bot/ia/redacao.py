"""Como o bot fala. Duas implementações; a escolha é config, não arquitetura.

`RedatorEstatico` roda sem chave da Anthropic e sem rede — é o que permite validar o
fluxo inteiro no Telegram antes de gastar um token.
`RedatorClaude` usa os mesmos textos como base e dá a variação humana em cima.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from creche_bot.dominio.tipos import Classificacao
from creche_bot.ia.persona import SISTEMA, TEXTOS

log = logging.getLogger(__name__)

MODELO = "claude-opus-5"   # nunca Fable/Mythos: são Covered Models, sem ZDR


@runtime_checkable
class Redator(Protocol):
    def texto(self, chave: str, **vars: Any) -> str: ...
    def classificar(self, mensagem: str, estado: str) -> Classificacao: ...


class RedatorEstatico:
    """Textos escritos à mão. Determinístico, grátis, testável."""

    def texto(self, chave: str, **vars: Any) -> str:
        return TEXTOS[chave].format(**vars) if vars else TEXTOS[chave]

    def classificar(self, mensagem: str, estado: str) -> Classificacao:
        m = mensagem.lower().strip()
        if m in {"/apagar", "apagar", "quero apagar meus dados"}:
            return Classificacao(intencao="desistir")
        if m.endswith("?") or m.startswith(("como", "quando", "por que", "porque", "o que")):
            return Classificacao(intencao="duvida")
        return Classificacao(intencao="responder")


class RedatorClaude:
    """Mesma interface, com variação de linguagem. Cai para o estático se a API falhar —
    um erro de rede não pode emudecer o bot."""

    def __init__(self, api_key: str) -> None:
        from anthropic import Anthropic  # import tardio: dependência opcional

        self._cliente = Anthropic(api_key=api_key)
        self._reserva = RedatorEstatico()

    def texto(self, chave: str, **vars: Any) -> str:
        base = self._reserva.texto(chave, **vars)
        try:
            r = self._cliente.messages.create(
                model=MODELO,
                max_tokens=300,
                system=[{"type": "text", "text": SISTEMA,
                         "cache_control": {"type": "ephemeral"}}],   # prompt estável: cacheia
                output_config={"effort": "low"},                     # conversa é volume
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content":
                           f"Reescreva com suas palavras, mantendo o sentido e os números "
                           f"exatos:\n\n{base}"}],
            )
            if r.stop_reason == "refusal":       # HTTP 200, não exceção
                log.warning("recusa do modelo em %r", chave)
                return base
            return "".join(b.text for b in r.content if b.type == "text").strip() or base
        except Exception:
            log.exception("redação falhou em %r; usando o texto estático", chave)
            return base

    def classificar(self, mensagem: str, estado: str) -> Classificacao:
        return self._reserva.classificar(mensagem, estado)


def criar(api_key: str | None) -> Redator:
    return RedatorClaude(api_key) if api_key else RedatorEstatico()
