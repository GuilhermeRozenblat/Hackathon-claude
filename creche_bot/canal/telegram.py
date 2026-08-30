"""Adapter do Telegram: long polling e envio.

# ponytail: cliente HTTP com urllib da stdlib. A Bot API que usamos são 6 métodos; o
# python-telegram-bot é async e contaminaria conversa/, ia/ e dados/ inteiras sem ganho
# nesta escala. Trocar quando houver webhook + concorrência real (Fase 3).

Long polling em vez de webhook é o que faz a V1 rodar em localhost sem HTTPS nem ngrok.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from creche_bot.canal.render import render
from creche_bot.canal.tipos import Anexo, MensagemEntrada, MensagemSaida

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{metodo}"
ARQUIVO = "https://api.telegram.org/file/bot{token}/{caminho}"
LIMITE_DOWNLOAD = 20 * 1024 * 1024   # getFile não baixa mais que isso

# A transcrição roda local, em CPU, na mesma thread do polling: um áudio de dez minutos
# congelaria o bot para todo mundo. Acima disso o áudio nem é baixado.
MAX_SEGUNDOS_AUDIO = 120


def _debug() -> bool:
    """Espelha a conversa no console. Depuração local só: por aqui passam CPF, nome de
    criança e endereço, e o log normal carrega só ID. Nunca ligue onde o log é coletado.

    Lido a cada mensagem, não no import: assim vale também quando `DEBUG_CONTEUDO=1` vem
    do `.env`, que o `__main__` carrega depois de importar este módulo.
    """
    return os.environ.get("DEBUG_CONTEUDO", "").strip().lower() in {"1", "true", "sim"}


def _resumo_entrada(m: MensagemEntrada) -> str:
    partes = [repr(m.texto)] if m.texto else []
    if m.escolha:
        partes.append(f"tocou {m.escolha!r}")
    if m.anexo:   # tamanho e mime; os bytes nunca entram no traço
        partes.append(f"[anexo {m.anexo.mime} {len(m.anexo.conteudo) // 1024} KB]")
    return " ".join(partes) or "(sem conteúdo)"


def _resumo_saida(m: MensagemSaida) -> str:
    partes = [repr(m.texto)]
    if m.botoes:
        partes.append("botões: " + " | ".join(b.rotulo for b in m.botoes))
    if m.lista:
        partes.append("lista: " + " | ".join(i.titulo for i in m.lista))
    if m.figurinha:
        partes.append(f"figurinha: {m.figurinha}")
    if m.local:
        partes.append(f"local: {m.local.nome}")
    return " ".join(partes)


class ErroTelegram(Exception):
    pass


class Telegram:
    def __init__(self, token: str, intervalo_min_s: float = 1.05) -> None:
        self._token = token
        self._intervalo = intervalo_min_s     # ~1 msg/s por chat é o limite do Telegram
        self._ultimo_envio: dict[str, float] = {}

    # ------------------------------------------------------------------ HTTP
    def _chamar(self, metodo: str, timeout: int = 70, **params: Any) -> Any:
        corpo = urllib.parse.urlencode({
            k: (json.dumps(v) if isinstance(v, dict | list) else v)
            for k, v in params.items() if v is not None
        }).encode()
        req = urllib.request.Request(API.format(token=self._token, metodo=metodo), data=corpo)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)["result"]
        except urllib.error.HTTPError as e:
            detalhe = json.load(e)
            if e.code == 429:
                espera = detalhe.get("parameters", {}).get("retry_after", 1)
                log.warning("rate limit; aguardando %ss", espera)
                time.sleep(espera + 0.5)
                return self._chamar(metodo, timeout, **params)
            if e.code == 409:
                raise ErroTelegram(
                    "409: outro processo faz polling com este token. "
                    "Use um bot por desenvolvedor — veja TELEGRAM.md."
                ) from e
            raise ErroTelegram(f"{metodo} -> {e.code}: {detalhe.get('description')}") from e

    # --------------------------------------------------------------- entrada
    def _baixar(self, file_id: str, mime: str = "image/jpeg") -> Anexo | None:
        info = self._chamar("getFile", file_id=file_id)
        if info.get("file_size", 0) > LIMITE_DOWNLOAD:
            return None                       # o passo pede uma foto menor
        url = ARQUIVO.format(token=self._token, caminho=info["file_path"])
        with urllib.request.urlopen(url, timeout=60) as r:
            # `file_size` vem de fora e pode faltar: o corte é aqui, na leitura, senão
            # um arquivo grande entra inteiro na memória do processo.
            conteudo = r.read(LIMITE_DOWNLOAD + 1)
        if len(conteudo) > LIMITE_DOWNLOAD:
            return None
        return Anexo(conteudo=conteudo, mime=mime, nome=info["file_path"])

    def _traduzir(self, upd: dict) -> MensagemEntrada | None:
        """Update do Telegram -> modelo canônico. Nada do dicionário dele sai daqui."""
        if (cq := upd.get("callback_query")):
            self._chamar("answerCallbackQuery", callback_query_id=cq["id"])
            return MensagemEntrada(
                canal="telegram", id_externo=str(cq["message"]["chat"]["id"]),
                id_mensagem=f"cb{upd['update_id']}", escolha=cq["data"],
            )

        m = upd.get("message")
        if not m:
            return None

        anexo = None
        if (fotos := m.get("photo")):
            anexo = self._baixar(fotos[-1]["file_id"])       # a última é a maior
        elif (som := m.get("voice") or m.get("audio")):
            if som.get("duration", 0) <= MAX_SEGUNDOS_AUDIO:
                anexo = self._baixar(som["file_id"], som.get("mime_type") or "audio/ogg")
        elif (doc := m.get("document")):
            # O mime vem do cliente, não é confiável para autorizar nada — serve só para
            # o extrator saber se abre como imagem ou como PDF.
            anexo = self._baixar(doc["file_id"], doc.get("mime_type", "application/octet-stream"))

        return MensagemEntrada(
            canal="telegram", id_externo=str(m["chat"]["id"]),
            id_mensagem=str(m["message_id"]),
            texto=m.get("text") or m.get("caption"), anexo=anexo,
        )

    # ----------------------------------------------------------------- saída
    def enviar(self, id_externo: str, msg: MensagemSaida) -> None:
        if _debug():
            log.info("→ %s · %s", id_externo, _resumo_saida(msg))
        agora = time.monotonic()
        if (espera := self._intervalo - (agora - self._ultimo_envio.get(id_externo, 0))) > 0:
            time.sleep(espera)
        for metodo, params in render(msg):
            self._chamar(metodo, timeout=20, chat_id=id_externo, **params)
        self._ultimo_envio[id_externo] = time.monotonic()

    # ------------------------------------------------------------- polling
    def rodar(self, processar: Callable[[MensagemEntrada], MensagemSaida | None]) -> None:
        eu = self._chamar("getMe")
        log.info("bot @%s no ar", eu["username"])
        self._chamar("deleteWebhook")     # webhook velho faz getUpdates devolver 409

        offset: int | None = None
        while True:
            try:
                updates = self._chamar("getUpdates", offset=offset, timeout=50)
            except ErroTelegram as e:
                log.error("polling: %s", e)
                time.sleep(3)
                continue

            for upd in updates:
                offset = upd["update_id"] + 1
                try:
                    entrada = self._traduzir(upd)
                    if entrada is None:
                        continue
                    if _debug():
                        log.info("← %s · %s", entrada.id_externo, _resumo_entrada(entrada))
                    if (resposta := processar(entrada)) is not None:
                        self.enviar(entrada.id_externo, resposta)
                except Exception:
                    # Um update ruim não pode derrubar o bot para todo mundo.
                    log.exception("falha ao processar update %s", upd.get("update_id"))
