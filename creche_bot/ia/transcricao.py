"""Áudio -> texto, na própria máquina.

Claude não recebe áudio — a API aceita texto, imagem e PDF, e nada mais. E mandar a voz
de uma família para um serviço de transcrição de terceiros quebraria a regra de
privacidade do projeto (ZDR, dado de criança). Então o modelo roda aqui: os bytes entram,
o texto sai, nada atravessa a rede.

# ponytail: faster-whisper em CPU, síncrono, na thread do polling. É o que cabe num
# processo só. Se o volume crescer, isto vira uma fila — não um serviço.
"""

from __future__ import annotations

import io
import logging
import os

log = logging.getLogger(__name__)

# "small" acerta bem português falado e leva ~2s por 10s de áudio num laptop.
# "base" é ~3x mais rápido e erra mais nome próprio. Vale mudar por máquina.
MODELO = os.environ.get("WHISPER_MODELO", "small")

# Resposta de cadastro é curta. O corte também é guarda: áudio longo vira prompt longo.
MAX_CARACTERES = 500


class Transcritor:
    """Carrega o modelo na primeira voz que chega, não no boot — subir o bot não pode
    depender de um download de centenas de MB."""

    def __init__(self, modelo: str = MODELO) -> None:
        self._nome = modelo
        self._whisper = None

    def __call__(self, audio: bytes) -> str | None:
        """`None` = não deu para ouvir. Quem chama pede para a pessoa escrever."""
        try:
            if self._whisper is None:
                from faster_whisper import WhisperModel

                log.info("carregando o modelo de voz %r", self._nome)
                self._whisper = WhisperModel(self._nome, device="cpu", compute_type="int8")

            segmentos, _ = self._whisper.transcribe(
                io.BytesIO(audio), language="pt", vad_filter=True,
            )
            texto = " ".join(s.text.strip() for s in segmentos).strip()
        except ImportError:
            log.error("chegou áudio e o faster-whisper não está instalado — "
                      "rode: pip install -e '.[audio]'")
            return None
        except Exception:
            log.exception("transcrição falhou")
            return None

        return texto[:MAX_CARACTERES] or None
