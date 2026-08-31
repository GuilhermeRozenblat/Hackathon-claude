"""O aviso de "digitando..." é melhor esforço: nunca pode atrasar nem derrubar a resposta
de verdade."""

from __future__ import annotations

import io
import json
import urllib.error

from creche_bot.canal.telegram import Telegram


def test_avisar_processando_chama_sendchataction_sem_retry(monkeypatch):
    chamadas = []
    t = Telegram("token-de-mentira")
    monkeypatch.setattr(t, "_chamar",
                        lambda metodo, *a, **kw: chamadas.append((metodo, kw)))

    t.avisar_processando("42")

    assert chamadas == [
        ("sendChatAction", {"permitir_retry": False, "chat_id": "42", "action": "typing"}),
    ]


def test_avisar_processando_engole_qualquer_falha(monkeypatch):
    """Não só ErroTelegram: um JSON truncado no caminho de sucesso também não pode
    derrubar quem chama, senão o webhook aborta antes de processar a mensagem real."""
    t = Telegram("token-de-mentira")
    monkeypatch.setattr(t, "_chamar",
                        lambda *a, **kw: (_ for _ in ()).throw(ValueError("json quebrado")))

    t.avisar_processando("42")   # não levanta


def test_avisar_processando_registra_throttle(monkeypatch):
    """Sem isto, o `enviar()` da resposta real logo em seguida não vê esta chamada e
    arrisca estourar o 1 msg/s do Telegram."""
    t = Telegram("token-de-mentira")
    monkeypatch.setattr(t, "_chamar", lambda *a, **kw: None)

    t.avisar_processando("42")

    assert "42" in t._ultimo_envio


def test_avisar_processando_nao_espera_o_retry_do_429(monkeypatch):
    """`permitir_retry=False` tem que valer de verdade: sem isso, um 429 no próprio aviso
    prenderia a thread no `time.sleep` do retry antes de processar a mensagem real."""
    import creche_bot.canal.telegram as mod

    corpo = json.dumps({"parameters": {"retry_after": 30}}).encode()
    erro = urllib.error.HTTPError("url", 429, "rate limit", {}, io.BytesIO(corpo))
    monkeypatch.setattr(mod.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(erro))
    dormiu = []
    monkeypatch.setattr(mod.time, "sleep", lambda s: dormiu.append(s))

    t = Telegram("token-de-mentira")
    t.avisar_processando("42")   # não levanta, não dorme

    assert dormiu == []


def test_chamar_normal_ainda_espera_o_retry_do_429(monkeypatch):
    """O comportamento padrão (usado por `enviar()`, `getUpdates` etc.) continua esperando
    e tentando de novo: só `avisar_processando` pediu para pular isso."""
    import creche_bot.canal.telegram as mod

    corpo = json.dumps({"parameters": {"retry_after": 1}}).encode()
    erro = urllib.error.HTTPError("url", 429, "rate limit", {}, io.BytesIO(corpo))
    chamadas = {"n": 0}

    def urlopen_falso(*a, **k):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise erro
        return io.BytesIO(json.dumps({"result": "ok"}).encode())

    monkeypatch.setattr(mod.urllib.request, "urlopen", urlopen_falso)
    dormiu = []
    monkeypatch.setattr(mod.time, "sleep", lambda s: dormiu.append(s))

    t = Telegram("token-de-mentira")
    resultado = t._chamar("sendMessage", chat_id="42", text="oi")

    assert resultado == "ok"
    assert dormiu == [1.5]
