"""MensagemSaida -> payload do Telegram.

Só tradução de plataforma. A abreviação de rótulo mora em `tipos.py`, junto do limite
que ela existe para respeitar, e o construtor de MensagemSaida cobra antes do render.
"""

from __future__ import annotations

from typing import Any

from creche_bot.canal.figurinhas import emoji
from creche_bot.canal.tipos import MensagemSaida


def render(msg: MensagemSaida) -> list[tuple[str, dict[str, Any]]]:
    """Devolve [(metodo, params)]: uma MensagemSaida pode virar mais de uma mensagem.

    Sem `parse_mode`: texto puro, sempre. MarkdownV2 do Telegram e `*negrito*` do WhatsApp
    são dialetos incompatíveis, e o escape do Telegram é fonte clássica de bug.
    """
    texto = msg.texto
    if (e := emoji(msg.figurinha)):
        texto = f"{texto}\n\n{e}"

    principal: dict[str, Any] = {"text": texto}

    if msg.botoes:
        principal["reply_markup"] = {
            "inline_keyboard": [[{"text": b.rotulo, "callback_data": b.id}] for b in msg.botoes]
        }
    elif msg.lista:
        # O Telegram não tem "lista" nativa; vira teclado de uma coluna. No WhatsApp
        # o adapter usará interactive/list. Mesmo contrato, render diferente.
        principal["reply_markup"] = {
            "inline_keyboard": [
                [{"text": f"{i.titulo}"[:64], "callback_data": i.id}] for i in msg.lista
            ]
        }

    saida = [("sendMessage", principal)]

    if msg.local:
        saida.append(("sendVenue", {
            "latitude": msg.local.lat, "longitude": msg.local.lng,
            "title": msg.local.nome, "address": msg.local.endereco,
        }))
    return saida
