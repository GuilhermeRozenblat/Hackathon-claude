"""`configurar_webhook.py`: a URL que ele monta e o que ele recusa.

Sem rede. `chamar` é substituído por um dublê que grava o que teria ido para o Telegram —
é o parâmetro que importa aqui, não a resposta da API.
"""

from __future__ import annotations

import pytest

from scripts import configurar_webhook as cw

TOKEN = "8123456789:AAHumtokendementiraquetem35chars"
SEGREDO = "segredo-de-teste-com-tamanho-real"


@pytest.fixture
def telegram(monkeypatch):
    """Intercepta as chamadas e devolve sucesso, gravando o que foi pedido."""
    chamadas: list[tuple[str, dict]] = []

    def falso(token: str, metodo: str, **params):
        chamadas.append((metodo, params))
        return {"ok": True, "result": {"url": params.get("url", "")}}

    monkeypatch.setattr(cw, "chamar", falso)
    monkeypatch.setenv("TELEGRAM_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SEGREDO)
    monkeypatch.setattr(cw, "carregar_env", lambda _: None)
    return chamadas


def rodar(monkeypatch, *argv):
    monkeypatch.setattr(cw.sys, "argv", ["configurar_webhook.py", *argv])
    cw.main()


def test_a_url_leva_o_segredo_no_caminho_e_no_cabecalho(telegram, monkeypatch):
    """As duas trancas do `servidor.py` precisam das duas metades registradas aqui."""
    rodar(monkeypatch, "https://app.up.railway.app")
    metodo, params = telegram[0]
    assert metodo == "setWebhook"
    assert params["url"] == f"https://app.up.railway.app/telegram/{SEGREDO}"
    assert params["secret_token"] == SEGREDO


def test_barra_no_fim_nao_vira_barra_dupla(telegram, monkeypatch):
    rodar(monkeypatch, "https://app.up.railway.app/")
    assert "//telegram/" not in telegram[0][1]["url"]


def test_so_pede_os_updates_que_o_bot_trata(telegram, monkeypatch):
    """Sem a lista, o Telegram manda edição, entrada em canal e reação — tudo descartado
    por `_traduzir`, e tudo pago em requisição."""
    rodar(monkeypatch, "https://app.up.railway.app")
    assert telegram[0][1]["allowed_updates"] == ["message", "callback_query"]


def test_http_sem_s_e_recusado(telegram, monkeypatch):
    """O Telegram só aceita webhook em https. Falhar aqui é mais claro que falhar lá."""
    with pytest.raises(SystemExit) as saida:
        rodar(monkeypatch, "http://app.up.railway.app")
    assert "https" in str(saida.value)
    assert telegram == []


def test_sem_segredo_nao_registra_nada(telegram, monkeypatch):
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET")
    with pytest.raises(SystemExit) as saida:
        rodar(monkeypatch, "https://app.up.railway.app")
    assert "TELEGRAM_WEBHOOK_SECRET" in str(saida.value)
    assert telegram == []


def test_remover_nao_descarta_o_que_esta_na_fila(telegram, monkeypatch):
    """O que chegou enquanto o webhook valia é família esperando resposta, não lixo."""
    rodar(monkeypatch, "--remover")
    metodo, params = telegram[0]
    assert metodo == "deleteWebhook"
    assert params["drop_pending_updates"] is False


def test_ver_nao_imprime_o_segredo(telegram, monkeypatch, capsys):
    """A URL registrada carrega o segredo no caminho; `--ver` mostra só até o /telegram/."""
    def com_url(token, metodo, **params):
        return {"ok": True, "result": {"url": f"https://app.up.railway.app/telegram/{SEGREDO}"}}

    monkeypatch.setattr(cw, "chamar", com_url)
    rodar(monkeypatch, "--ver")
    saida = capsys.readouterr().out
    assert SEGREDO not in saida, "o segredo não pode aparecer no terminal"
    assert "/telegram/…" in saida
