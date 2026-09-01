"""O aviso de "digitando..." é melhor esforço: nunca pode atrasar nem derrubar a resposta
de verdade."""

from __future__ import annotations

import io
import json
import time
import urllib.error

import pytest

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


def test_digitando_renova_o_aviso_ate_a_resposta_sair(monkeypatch):
    """Um sendChatAction vale ~5s no cliente, e transcrição de áudio ou chamada ao modelo
    passam disso: sem renovar, a família fica no vácuo justo no turno lento."""
    import creche_bot.canal.telegram as mod

    monkeypatch.setattr(mod, "RENOVA_DIGITANDO", 0.01)
    t = Telegram("token-de-mentira")
    avisos: list[str] = []
    monkeypatch.setattr(t, "avisar_processando", avisos.append)

    with t.digitando("42"):
        time.sleep(0.1)

    assert len(avisos) > 1 and set(avisos) == {"42"}

    parou_em = len(avisos)    # o `join` do contexto já esperou o aviso em voo pousar
    time.sleep(0.05)
    assert len(avisos) == parou_em, "a thread morre quando a resposta sai"


def test_digitando_nao_acende_depois_que_a_resposta_saiu(monkeypatch):
    """O aviso que estava em voo no `set()` chegaria ao Telegram DEPOIS da resposta, e
    acenderia "digitando…" por mais 5s sem nada vir — o vácuo ao contrário."""
    import creche_bot.canal.telegram as mod

    monkeypatch.setattr(mod, "RENOVA_DIGITANDO", 0.01)
    t = Telegram("token-de-mentira")
    avisos: list[str] = []

    def lento(id_externo: str) -> None:
        time.sleep(0.05)          # a chamada de rede, apanhada no meio do `set()`
        avisos.append(id_externo)

    monkeypatch.setattr(t, "avisar_processando", lento)

    with t.digitando("42"):
        time.sleep(0.02)
    pousou = len(avisos)

    time.sleep(0.1)
    assert len(avisos) == pousou, "o contexto espera o aviso em voo antes de devolver"


def test_digitando_sem_chat_nao_avisa(monkeypatch):
    """Update sem chat (my_chat_member, poll) não tem para quem avisar."""
    t = Telegram("token-de-mentira")
    monkeypatch.setattr(t, "_chamar", lambda *a, **kw: pytest.fail("não devia chamar"))

    with t.digitando(None):
        pass


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
