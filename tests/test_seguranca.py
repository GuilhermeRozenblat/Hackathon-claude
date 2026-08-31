"""As garantias que não podem regredir: segredo não vaza em log, .env não fica exposto."""

from __future__ import annotations

import logging
import os
import stat

from creche_bot.segredos import FormatadorSeguro, carregar_env

TOKEN = "8123456789:AAHumtokendementiraquetem35chars"


def _formatar(record: logging.LogRecord) -> str:
    f = FormatadorSeguro("%(message)s", segredos=[TOKEN, "curto"])
    return f.format(record)


def test_token_nao_sobrevive_ao_log():
    r = logging.LogRecord("t", logging.ERROR, __file__, 1,
                          "falhou em https://api.telegram.org/bot%s/getMe", (TOKEN,), None)
    saida = _formatar(r)
    assert TOKEN not in saida and "«redigido»" in saida


def test_token_nao_sobrevive_nem_dentro_do_traceback():
    try:
        raise RuntimeError(f"HTTP 401 em bot{TOKEN}/sendMessage")
    except RuntimeError:
        import sys
        r = logging.LogRecord("t", logging.ERROR, __file__, 1, "caiu", (), sys.exc_info())
    assert TOKEN not in _formatar(r)


def test_chave_da_anthropic_nao_sobrevive_ao_log():
    """Ela não vem do ambiente: chega no chat, em `/ia sk-ant-...`, e com DEBUG_CONTEUDO=1
    a mensagem inteira é espelhada. Só o formato pega um segredo que ninguém declarou."""
    chave = "sk-ant-api03-uAbC-123_deMentira"
    r = logging.LogRecord("t", logging.INFO, __file__, 1, "← 777 · %r", (f"/ia {chave}",),
                          None)
    saida = _formatar(r)
    assert chave not in saida and "«redigido»" in saida


def test_valor_curto_nao_e_redigido():
    """Redigir string curta apagaria log legítimo, e o filtro tem piso de 12 caracteres."""
    r = logging.LogRecord("t", logging.INFO, __file__, 1, "estado curto", (), None)
    assert _formatar(r) == "estado curto"


def test_env_legivel_por_outros_e_fechado(tmp_path):
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_TOKEN=  'do-arquivo'  \nexport OUTRO=2\n# comentario\n")
    env.chmod(0o644)

    os.environ.pop("TELEGRAM_TOKEN", None)
    os.environ.pop("OUTRO", None)
    try:
        carregar_env(env)
        assert not stat.S_IMODE(env.stat().st_mode) & 0o077, ".env continuou legível"
        assert os.environ["TELEGRAM_TOKEN"] == "do-arquivo", "aspas e espaços entram no token"
        assert os.environ["OUTRO"] == "2"
    finally:
        os.environ.pop("TELEGRAM_TOKEN", None)
        os.environ.pop("OUTRO", None)


def test_dsn_com_placeholder_do_exemplo_para_antes_de_conectar(monkeypatch):
    """`:<minhasenha>@` faz o Postgres responder "password authentication failed".

    O erro manda procurar a senha errada, e a senha está certa, e o que sobrou foram os
    sinais que marcavam o buraco no exemplo do BANCO.md. Falhar aqui, com o motivo, custa
    uma linha e economiza a caçada.
    """
    import pytest

    from creche_bot.__main__ import escolher_repositorio

    monkeypatch.delenv("REPOSITORIO", raising=False)
    monkeypatch.setenv("DATABASE_URL",
                       "postgresql://postgres.abc:<senha>@x.pooler.supabase.com:6543/postgres")
    with pytest.raises(SystemExit) as saida:
        escolher_repositorio()
    assert "<...>" in str(saida.value), "a mensagem tem que nomear o placeholder"
