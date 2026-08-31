"""Mensagem de voz vira anexo de áudio, e áudio longo nem é baixado."""

from __future__ import annotations

from creche_bot.canal.telegram import MAX_SEGUNDOS_AUDIO, Telegram
from creche_bot.canal.tipos import Anexo


def _bot(monkeypatch) -> Telegram:
    t = Telegram("token-de-mentira")
    monkeypatch.setattr(t, "_baixar",
                        lambda file_id, mime="image/jpeg": Anexo(b"opus", mime, file_id))
    return t


def _update(**som) -> dict:
    return {"update_id": 1,
            "message": {"message_id": 9, "chat": {"id": 42}, "voice": som}}


def test_voz_curta_vira_anexo_de_audio(monkeypatch):
    entrada = _bot(monkeypatch)._traduzir(_update(file_id="abc", duration=8,
                                                  mime_type="audio/ogg"))

    assert entrada.anexo.mime == "audio/ogg"
    assert entrada.texto is None, "o texto só existe depois da transcrição"


def test_audio_longo_nem_e_baixado(monkeypatch):
    """A transcrição roda local, na thread do polling: dez minutos travariam todo mundo."""
    entrada = _bot(monkeypatch)._traduzir(
        _update(file_id="abc", duration=MAX_SEGUNDOS_AUDIO + 1))

    assert entrada.anexo is None
