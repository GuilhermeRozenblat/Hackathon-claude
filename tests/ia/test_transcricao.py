"""Áudio nunca pode derrubar o bot — no pior caso ele pede para a pessoa escrever."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from creche_bot.ia.transcricao import MAX_CARACTERES, Transcritor


def test_sem_a_dependencia_o_boot_passa_e_o_audio_vira_none(monkeypatch):
    """`None` em sys.modules faz o `from faster_whisper import ...` levantar ImportError."""
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    t = Transcritor()
    t.carregar()                        # é o que a thread do boot chama
    assert t(b"nao importa") is None    # e o áudio que chega depois não explode


class _FakeWhisper:
    def __init__(self, texto: str) -> None:
        self.texto, self.chamadas = texto, 0

    def transcribe(self, *_: object, **__: object):
        self.chamadas += 1
        return [SimpleNamespace(text=f"  {self.texto}  ")], None


def test_audio_longo_e_cortado():
    """O corte é guarda, não estética: áudio comprido vira prompt comprido."""
    t = Transcritor()
    t._whisper = _FakeWhisper("a" * (MAX_CARACTERES + 100))   # como se o boot já tivesse aquecido
    assert len(t(b"ogg")) == MAX_CARACTERES


def test_carregar_nao_recarrega_o_que_ja_esta_na_memoria():
    t = Transcritor()
    t._whisper = fake = _FakeWhisper("oi, quero creche")
    t.carregar()
    assert t(b"ogg") == "oi, quero creche"
    assert t._whisper is fake and fake.chamadas == 1
