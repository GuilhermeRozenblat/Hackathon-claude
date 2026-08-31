"""Onde os segredos entram e por onde eles não podem sair.

Um arquivo só, e fora de `__main__.py`, para que dê para testar sem subir o bot inteiro.

O token do Telegram viaja no CAMINHO da URL da Bot API, e basta um traceback de urllib com
a URL dentro para ele parar no console, no CI, ou num print colado no chat da equipe.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path

# Nomes cujo valor nunca pode aparecer em log, traceback ou mensagem de erro.
SEGREDOS = ("TELEGRAM_TOKEN", "ANTHROPIC_API_KEY", "DATABASE_URL", "FERNET_KEY",
            "POSTGRES_PASSWORD", "TELEGRAM_WEBHOOK_SECRET")

# Segredo que o processo NÃO conhece de antemão: a chave da Anthropic chega pelo chat, em
# `/ia sk-ant-...`, e com `DEBUG_CONTEUDO=1` a mensagem inteira é espelhada no console.
# Sem valor para comparar, só o formato pega.
CHAVE_API = re.compile(r"sk-ant-[\w-]{8,}")


class FormatadorSeguro(logging.Formatter):
    """Segredo nunca chega ao log: nem em mensagem, nem em traceback, nem dentro de URL.

    O token do Telegram viaja no caminho da URL da Bot API, então basta um traceback de
    urllib com a URL dentro para ele parar no console, no CI ou num print colado no chat.
    """

    def __init__(self, *args, segredos: Sequence[str], **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Valor curto demais dá falso positivo e apagaria log legítimo.
        self._segredos = [s for s in segredos if len(s) >= 12]

    def format(self, record: logging.LogRecord) -> str:
        texto = super().format(record)
        for segredo in self._segredos:
            texto = texto.replace(segredo, "«redigido»")
        return CHAVE_API.sub("«redigido»", texto)


def configurar_log(nivel: int = logging.INFO) -> None:
    """Log só com ID, e o formatador como segunda linha de defesa. Chame depois do .env."""
    saida = logging.StreamHandler()
    saida.setFormatter(FormatadorSeguro(
        "%(asctime)s %(levelname)-7s %(name)s · %(message)s", datefmt="%H:%M:%S",
        segredos=[v for chave in SEGREDOS if (v := os.environ.get(chave, ""))],
    ))
    logging.basicConfig(level=nivel, handlers=[saida])
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def carregar_env(env: Path) -> None:
    """Lê o .env sem depender de python-dotenv, e cobra que ele seja só seu."""
    if not env.exists():
        sys.exit("Falta o .env. Rode: cp .env.example .env  (e cole o token do @BotFather)")

    # Quem tem o token controla o bot, que fala com famílias e recebe documento de
    # criança. Legível por grupo ou por outro usuário da máquina não serve.
    if env.stat().st_mode & 0o077:
        env.chmod(0o600)
        print("aviso: .env estava legível por outros; ajustei para 0600.", file=sys.stderr)

    for linha in env.read_text().splitlines():
        linha = linha.strip().removeprefix("export ")
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip().strip("\"'"))
