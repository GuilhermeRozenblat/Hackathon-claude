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
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
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

# Quantas vezes reesperar um 429 antes de desistir. O retry era recursivo e sem teto: um
# rate limit sustentado virava recursão infinita segurando a thread que atende todo mundo.
MAX_TENTATIVAS_429 = 3

# O "digitando…" do Telegram dura ~5s; renovar antes disso não deixa buraco na tela.
RENOVA_DIGITANDO = 4.0
# Teto do aviso. O SDK da Anthropic espera minutos por padrão: sem isto, uma chamada
# pendurada vira "digitando…" eterno, e o eterno é pior que o silêncio.
MAX_DIGITANDO = 120.0


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
    def _chamar(self, metodo: str, timeout_local: int = 70, *,
                permitir_retry: bool = True, tentativa: int = 0, **params: Any) -> Any:
        """`timeout_local` é o timeout do socket; o `timeout` de getUpdates (long polling)
        é um parâmetro da API do Telegram e viaja em `params`, não aqui — os dois têm nomes
        parecidos mas são coisas diferentes, por isso o nome distinto.

        `permitir_retry=False` pula o `sleep` do 429: usado por quem chama fora do fluxo
        principal (`avisar_processando`) e não pode travar a thread esperando o Telegram.
        """
        corpo = urllib.parse.urlencode({
            k: (json.dumps(v) if isinstance(v, dict | list) else v)
            for k, v in params.items() if v is not None
        }).encode()
        req = urllib.request.Request(API.format(token=self._token, metodo=metodo), data=corpo)
        try:
            with urllib.request.urlopen(req, timeout=timeout_local) as r:
                return json.load(r)["result"]
        except urllib.error.HTTPError as e:
            try:
                detalhe = json.load(e)
            except ValueError:   # corpo de erro que não é JSON (proxy, edge fora do ar)
                detalhe = {}
            if e.code == 429 and permitir_retry and tentativa < MAX_TENTATIVAS_429:
                espera = detalhe.get("parameters", {}).get("retry_after", 1)
                log.warning("rate limit; aguardando %ss (tentativa %d)", espera, tentativa + 1)
                time.sleep(espera + 0.5)
                return self._chamar(metodo, timeout_local, permitir_retry=permitir_retry,
                                    tentativa=tentativa + 1, **params)
            if e.code == 429:
                # Sem o teto isto era recursão sem fundo: um 429 sustentado segurava a
                # thread do polling para sempre, e o bot parava de atender todo mundo.
                raise ErroTelegram(
                    f"{metodo} -> 429 depois de {MAX_TENTATIVAS_429} tentativas") from e
            if e.code == 409:
                raise ErroTelegram(
                    "409: outro processo faz polling com este token. "
                    "Use um bot por desenvolvedor. Veja TELEGRAM.md."
                ) from e
            raise ErroTelegram(f"{metodo} -> {e.code}: {detalhe.get('description')}") from e
        except (urllib.error.URLError, OSError) as e:
            raise ErroTelegram(f"{metodo} -> erro de rede: {e}") from e

    # --------------------------------------------------------------- entrada
    def _baixar(self, file_id: str, mime: str = "image/jpeg") -> Anexo | None:
        """`None` em qualquer falha, que é o valor que os passos já sabem tratar com
        mensagem gentil ("manda uma menor").

        Sem o try, o `getFile` de arquivo acima de 20 MB (o Telegram responde 400 "file is
        too big", e nem manda `file_size`) virava `ErroTelegram`, o `except Exception` de
        cima engolia, e a família que mandou a foto do documento não recebia resposta
        nenhuma. Queda de rede no meio do download tinha o mesmo desfecho.
        """
        try:
            info = self._chamar("getFile", file_id=file_id)
            if info.get("file_size", 0) > LIMITE_DOWNLOAD:
                return None                   # o passo pede uma foto menor
            url = ARQUIVO.format(token=self._token, caminho=info["file_path"])
            with urllib.request.urlopen(url, timeout=60) as r:
                # `file_size` vem de fora e pode faltar: o corte é aqui, na leitura, senão
                # um arquivo grande entra inteiro na memória do processo.
                conteudo = r.read(LIMITE_DOWNLOAD + 1)
        except (ErroTelegram, KeyError, OSError):
            log.warning("anexo não baixou; a família recebe o pedido de reenviar")
            return None
        if len(conteudo) > LIMITE_DOWNLOAD:
            return None
        return Anexo(conteudo=conteudo, mime=mime, nome=info["file_path"])

    def receber(self, upd: dict) -> MensagemEntrada | None:
        """Um update avulso -> modelo canônico. É a porta de entrada do WEBHOOK.

        `rodar()` é o caminho do long polling, e chama `_traduzir` direto. Quando a
        hospedagem recebe o update por HTTP (`scripts/servidor.py`), não há laço nenhum:
        chega um dicionário, sai uma `MensagemEntrada`. Este método existe para esse caso
        não precisar alcançar um `_privado` de fora do módulo.
        """
        return self._traduzir(upd)

    def chat_id_do(self, upd: dict) -> str | None:
        """Só olha o dicionário, sem chamar o Telegram: quem recebe o update chama isto
        ANTES de `receber()`/`_traduzir()`, porque a tradução já baixa anexo e responde
        callback — as duas coisas que o "digitando..." deveria cobrir.
        """
        if (cq := upd.get("callback_query")):
            return str(cq["message"]["chat"]["id"])
        if (m := upd.get("message")):
            return str(m["chat"]["id"])
        return None

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
            # `or 0` não: sem o campo, o default 0 deixava passar áudio de duração
            # desconhecida. Ausente é recusado, como o longo demais.
            if 0 < som.get("duration", 0) <= MAX_SEGUNDOS_AUDIO:
                anexo = self._baixar(som["file_id"], som.get("mime_type") or "audio/ogg")
        elif (doc := m.get("document")):
            # O mime vem do cliente, não é confiável para autorizar nada, e serve só para
            # o extrator saber se abre como imagem ou como PDF.
            mime = doc.get("mime_type", "application/octet-stream")
            # "Enviar como arquivo" não traz `duration`, e `maquina.processar` roteia por
            # `mime.startswith("audio/")`: um .ogg de 20 MB furava o teto de 120s e ia
            # inteiro para a transcrição síncrona, deixando o bot mudo para todo mundo.
            # Mesmo tratamento da voz longa demais: sem anexo.
            if not mime.startswith("audio/"):
                anexo = self._baixar(doc["file_id"], mime)

        return MensagemEntrada(
            canal="telegram", id_externo=str(m["chat"]["id"]),
            id_mensagem=str(m["message_id"]),
            texto=m.get("text") or m.get("caption"), anexo=anexo,
        )

    # ----------------------------------------------------------------- saída
    def avisar_processando(self, id_externo: str) -> None:
        """"Zé Matrícula está digitando…" enquanto o núcleo processa. Cold start do
        serviço hospedado e transcrição de áudio levam alguns segundos calados; isto dá
        um sinal de vida. Melhor esforço, e literalmente qualquer coisa: falhar aqui não
        pode atrasar (por isso `permitir_retry=False`, sem o sleep do 429) nem derrubar
        (por isso `Exception`, não só `ErroTelegram` — o corpo pode vir truncado ou fora
        do formato esperado) a resposta de verdade.

        Registra o horário como se tivesse enviado: senão o `enviar()` da resposta real,
        logo em seguida, não vê essa chamada e arrisca estourar o limite de 1 msg/s.
        """
        try:
            self._chamar("sendChatAction", 5, permitir_retry=False,
                         chat_id=id_externo, action="typing")
        except Exception:
            log.debug("aviso de \"digitando\" falhou, seguindo sem ele", exc_info=True)
        finally:
            self._ultimo_envio[id_externo] = time.monotonic()

    @contextmanager
    def digitando(self, id_externo: str | None) -> Iterator[None]:
        """Mantém o "Zé Matrícula está digitando…" no ar enquanto o núcleo trabalha.

        Um `sendChatAction` vale ~5s no cliente, e só isso deixava a família no vácuo
        justo nos turnos lentos: transcrição de áudio e chamada ao modelo passam disso
        com folga. Uma thread renova o aviso até a resposta sair.

        Melhor esforço como o aviso avulso: `avisar_processando` já engole qualquer
        falha, e a thread é daemon para não segurar o Ctrl-C do dev.

        # ponytail: uma thread de aviso por update, sem agendador. No polling é uma por
        # vez; no webhook o `ThreadingHTTPServer` já dá uma thread por update, e cada
        # uma cuida do seu chat. Um timer único só compensaria com muito mais volume.
        """
        if id_externo is None:              # update sem chat: my_chat_member, poll…
            yield
            return

        parar = threading.Event()

        def renovar() -> None:
            # Escreve `_ultimo_envio` de fora da thread principal. O pior caso é o
            # `enviar()` seguinte esperar até 1s a mais pelo throttle, nunca um envio
            # a menos: só o relógio do rate limit é compartilhado.
            fim = time.monotonic() + MAX_DIGITANDO
            while not parar.wait(RENOVA_DIGITANDO) and time.monotonic() < fim:
                self.avisar_processando(id_externo)

        self.avisar_processando(id_externo)
        thread = threading.Thread(target=renovar, daemon=True)
        thread.start()
        try:
            yield
        finally:
            parar.set()
            # Espera o aviso em voo pousar. Um `sendChatAction` que chega DEPOIS da
            # resposta acende "digitando…" por mais 5s sem nada vir: é o vácuo que isto
            # veio matar, ao contrário. Meio segundo cobre a chamada normal; socket
            # travado a gente desiste e segue, que a thread é daemon.
            thread.join(0.5)

    def enviar(self, id_externo: str, msg: MensagemSaida) -> None:
        if _debug():
            log.info("→ %s · %s", id_externo, _resumo_saida(msg))
        for metodo, params in render(msg):
            agora = time.monotonic()
            if (espera := self._intervalo - (agora - self._ultimo_envio.get(id_externo, 0))) > 0:
                time.sleep(espera)
            self._chamar(metodo, 20, chat_id=id_externo, **params)
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
                    # Desde antes de traduzir: `_traduzir` já baixa anexo e responde
                    # callback, justo o que demora e o que o aviso deveria cobrir.
                    with self.digitando(self.chat_id_do(upd)):
                        entrada = self._traduzir(upd)
                        if entrada is None:
                            continue
                        if _debug():
                            log.info("← %s · %s", entrada.id_externo,
                                     _resumo_entrada(entrada))
                        resposta = processar(entrada)
                    if resposta is not None:
                        self.enviar(entrada.id_externo, resposta)
                except Exception:
                    # Um update ruim não pode derrubar o bot para todo mundo.
                    log.exception("falha ao processar update %s", upd.get("update_id"))
