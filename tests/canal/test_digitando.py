"""O aviso de "digitando..." é melhor esforço: nunca pode derrubar a resposta de verdade."""

from __future__ import annotations

from creche_bot.canal.telegram import ErroTelegram, Telegram


def test_avisar_processando_chama_sendchataction(monkeypatch):
    chamadas = []
    t = Telegram("token-de-mentira")
    monkeypatch.setattr(t, "_chamar",
                        lambda metodo, *a, **kw: chamadas.append((metodo, kw)))

    t.avisar_processando("42")

    assert chamadas == [("sendChatAction", {"chat_id": "42", "action": "typing"})]


def test_avisar_processando_engole_falha_do_telegram(monkeypatch):
    t = Telegram("token-de-mentira")
    monkeypatch.setattr(t, "_chamar",
                        lambda *a, **kw: (_ for _ in ()).throw(ErroTelegram("fora do ar")))

    t.avisar_processando("42")   # não levanta
