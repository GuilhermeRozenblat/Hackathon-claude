"""O processo único que a hospedagem sobe: painel, API do painel e webhook do Telegram.

    python scripts/servidor.py            # 0.0.0.0:$PORT (8000 se não houver)

Diferente de `painel.py`, que é a ferramenta de quem desenvolve: escuta só na loopback,
atende uma requisição por vez e não conhece o Telegram. Este aqui é o que roda hospedado:

    GET  /                       → redireciona para o painel
    GET  /creche-conectada.html  → o painel
    GET  /creche_bot/MapaFilaCreche/*.csv
    GET  /api/banco.json         → as contagens do Postgres
    GET  /saude                  → healthcheck da plataforma
    POST /telegram/<segredo>     → um update do Telegram

**Por que um serviço só.** O bot por webhook não precisa de processo próprio: ele só
acorda quando chega mensagem, e é o mesmo servidor HTTP que já está de pé para o painel.
Dois serviços custariam o dobro para deixar um deles ocioso 99% do tempo.

**Por que threading.** Um turno de conversa fala com o Postgres e com a API do Telegram,
centenas de milissegundos. Com `HTTPServer` puro, o painel de quem está olhando o mapa
congelaria a cada mensagem que chega, e o Telegram desistiria do webhook por timeout.

**O worker de outbox continua numa thread**, como no `__main__`: ele é quem entrega R1 a
R4, e não tem gatilho HTTP.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import sys
import threading
from collections import OrderedDict
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from creche_bot.canal.telegram import Telegram  # noqa: E402
from creche_bot.conversa.maquina import Maquina  # noqa: E402
from creche_bot.ia.redacao import RedatorEstatico  # noqa: E402
from creche_bot.ia.transcricao import Transcritor  # noqa: E402
from creche_bot.notificacao.outbox import rodar_worker  # noqa: E402
from creche_bot.segredos import carregar_env, configurar_log  # noqa: E402
from scripts.painel import PAINEL, PUBLICOS, Painel  # noqa: E402

log = logging.getLogger(__name__)

# Limite do corpo de um update. O Telegram manda JSON pequeno; foto e áudio vêm por
# `file_id`, não inline. Sem teto, um POST de 2 GB derruba o processo.
MAX_CORPO = 1 << 20

# Quanto o navegador pode guardar antes de perguntar de novo. O painel e os CSVs mudam
# por deploy, não por hora: sem isto, cada F5 baixa 1 MB de novo e a plataforma cobra o
# egresso. Uma hora é curto o bastante para um deploy aparecer sozinho.
CACHE_S = 3600

MIME = {".html": "text/html; charset=utf-8", ".csv": "text/csv; charset=utf-8"}

# Estático comprimido, em memória, uma vez por processo. São 7 arquivos e ~1 MB cru;
# guardá-los gzipados custa ~330 KB de RAM e economiza 3x de egresso em toda visita.
# ponytail: sem invalidação, porque o processo reinicia a cada deploy, que é quando eles mudam.
_COMPRIMIDO: dict[str, bytes] = {}


def _gzip(caminho: str) -> bytes:
    if caminho not in _COMPRIMIDO:
        _COMPRIMIDO[caminho] = gzip.compress((RAIZ / caminho).read_bytes(), 9)
    return _COMPRIMIDO[caminho]


# Quantos `update_id` recentes lembrar. O Telegram reenvia o update quando a resposta
# demora, falha ou a conexão cai, e reenvio é a MESMA mensagem, com o mesmo id. Sem esta
# memória, uma instabilidade de rede vira pergunta repetida na tela da família e, pior,
# resposta contada duas vezes no cadastro.
#
# 2048 é folgado: o Telegram só reenvia enquanto o update está pendente, e a fila dele
# anda em minutos. Guardar mais é lembrar de conversa que já acabou.
LEMBRAR = 2048


class _Vistos:
    """Os `update_id` já atendidos, com descarte do mais antigo.

    A janela que isto cobre é estreita de propósito. `do_POST` responde 200 ANTES de
    processar, então o Telegram raramente reenvia: só quando o 200 não chega até ele. Por
    isso memória de processo basta, e persistir no banco custaria uma ida a São Paulo por
    mensagem para um caso que quase não acontece.

    ponytail: some no restart, e com `sleepApplication` ligado o restart é rotina. O que
    escapa é um reenvio que atravesse a hibernação — o preço aceito, documentado em
    docs/HOSPEDAGEM.md §6. Uma réplica só; `numReplicas` é 1 de propósito.
    """

    def __init__(self, teto: int = LEMBRAR) -> None:
        self._ordem: OrderedDict[int, None] = OrderedDict()
        self._teto = teto
        self._trava = threading.Lock()

    def novo(self, update_id: int | None) -> bool:
        """`True` na primeira vez que este id aparece. Update sem id sempre passa."""
        if update_id is None:
            return True
        with self._trava:       # ThreadingHTTPServer: dois reenvios podem chegar juntos
            if update_id in self._ordem:
                return False
            self._ordem[update_id] = None
            if len(self._ordem) > self._teto:
                self._ordem.popitem(last=False)
            return True


class Servidor(Painel):
    """O painel mais o webhook. Herda a allowlist e o `api/banco.json` de `painel.py`."""

    protocol_version = "HTTP/1.1"
    # O socketserver aplica isto no socket. Sem timeout, um cliente que anuncia
    # `Content-Length: 999999` e não manda corpo prende a thread para sempre, e abrir
    # algumas dezenas dessas derruba o servidor sem precisar de nenhum bug.
    #
    # 10s é folgado para o que passa por aqui: o update do Telegram é JSON de alguns KB e
    # o painel é um arquivo local. Quem não completou a requisição em 10s não vai completar.
    timeout = 10
    nucleo: Maquina | None = None
    canal: Telegram | None = None
    # O caminho secreto do webhook. O Telegram repete o segredo no cabeçalho
    # `X-Telegram-Bot-Api-Secret-Token`; conferimos os dois. Sem ele, qualquer um que
    # descubra o domínio injeta mensagem como se fosse o Telegram. Preenchido no `main`,
    # depois do `carregar_env`, porque no import o .env ainda não foi lido.
    segredo: str = ""
    vistos = _Vistos()

    def do_GET(self) -> None:
        caminho = self.path.split("?", 1)[0].split("#", 1)[0]
        if caminho == "/saude":
            self._json({"ok": True}, 200)
            return
        # O 302 é tratado aqui, e não herdado, porque em HTTP/1.1 resposta sem corpo
        # precisa de `Content-Length: 0` explícito, senão o cliente fica esperando
        # um corpo que nunca vem, e a conexão só morre no timeout dele.
        if caminho in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", f"/{PAINEL}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        alvo = caminho.lstrip("/")
        if alvo in PUBLICOS and "gzip" in self.headers.get("Accept-Encoding", ""):
            self._estatico(alvo)
            return
        super().do_GET()

    def _estatico(self, caminho: str) -> None:
        """O painel e os CSVs, gzipados e cacheados. 1 MB de egresso vira ~330 KB."""
        corpo = _gzip(caminho)
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(Path(caminho).suffix, "application/octet-stream"))
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", f"public, max-age={CACHE_S}")
        self.end_headers()
        self.wfile.write(corpo)

    def do_POST(self) -> None:
        caminho = self.path.split("?", 1)[0].lstrip("/")
        if not self.segredo or caminho != f"telegram/{self.segredo}":
            self.send_error(404, "nada aqui")
            return
        # Cinto e suspensório: o caminho pode vazar em log de proxy, o cabeçalho não.
        cabecalho = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if cabecalho != self.segredo:
            log.warning("webhook chamado sem o cabeçalho de segredo")
            self.send_error(403, "segredo não confere")
            return

        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            # Sem isto o ValueError sobe, a thread morre e o cliente recebe uma conexão
            # fechada sem resposta nenhuma — nem erro, nem log.
            self.send_error(400, "Content-Length inválido")
            return
        if tamanho > MAX_CORPO:
            self.send_error(413, "corpo grande demais")
            return
        try:
            bruto = self.rfile.read(tamanho)
        except (TimeoutError, OSError):
            # `Content-Length` maior que o corpo enviado. Com o `timeout` da classe isto
            # desiste; sem ele, a leitura esperava para sempre e a thread ficava presa —
            # abrir conexões assim esgotaria o servidor.
            log.warning("corpo do webhook não chegou inteiro; conexão descartada")
            return
        try:
            update = json.loads(bruto or b"{}")
        except ValueError:
            self.send_error(400, "json inválido")
            return

        # 200 primeiro, trabalho depois: o Telegram reenvia o update se a resposta demorar,
        # e reenvio vira mensagem duplicada na conversa da família.
        self._json({"ok": True}, 200)
        try:
            self._atender(update)
        except Exception:
            log.exception("update do Telegram falhou")

    def _atender(self, update: dict) -> None:
        # Reenvio do Telegram não é mensagem nova. Sem esta guarda, a rede tossindo vira
        # pergunta repetida na tela da família e resposta contada duas vezes no cadastro.
        if not self.vistos.novo(update.get("update_id")):
            log.info("update repetido descartado")
            return
        # Antes de `receber()`: ele já baixa anexo e responde callback, justo o que
        # demora e o que o aviso deveria cobrir.
        if (chat_id := self.canal.chat_id_do(update)) is not None:
            self.canal.avisar_processando(chat_id)
        entrada = self.canal.receber(update)
        if entrada is None:
            return
        resposta = self.nucleo.processar(entrada)
        if resposta is not None:
            self.canal.enviar(entrada.id_externo, resposta)

    def log_message(self, formato: str, *args: object) -> None:
        """O log padrão do http.server imprime o caminho, e o caminho tem o segredo."""
        log.info("%s %s", self.command, self.path.split("/telegram/")[0] or "/telegram/…")


def montar() -> tuple[Maquina, Telegram]:
    """A raiz de composição da hospedagem. Reusa as escolhas do `__main__`."""
    from creche_bot.__main__ import escolher_backend, escolher_repositorio

    token = os.environ.get("TELEGRAM_TOKEN", "")
    if not token or token.startswith("coloque"):
        sys.exit("TELEGRAM_TOKEN não configurado. Veja docs/TELEGRAM.md")
    if not Servidor.segredo:
        sys.exit("TELEGRAM_WEBHOOK_SECRET não configurado. Veja docs/HOSPEDAGEM.md")

    repo = escolher_repositorio()      # já recusa DSN com `<...>` do exemplo
    backend = escolher_backend()
    canal = Telegram(token)
    # Sem IA de plataforma: cada contato liga a chave dele com `/ia`. Ver D20.
    transcritor = Transcritor()
    nucleo = Maquina(backend, RedatorEstatico(), repo, transcritor)

    # O worker acorda a cada `OUTBOX_INTERVALO_S`. Cada volta é uma consulta ao backend e
    # uma ao banco, barato, mas é CPU que a plataforma cobra 24h por dia. Com webhook o
    # bot só precisa entregar aviso, e minuto de atraso numa notificação de matrícula não
    # muda nada para a família. Ver docs/HOSPEDAGEM.md §6.
    intervalo = float(os.environ.get("OUTBOX_INTERVALO_S", "60"))
    threading.Thread(target=rodar_worker, args=(backend, canal, repo, intervalo),
                     daemon=True).start()
    if os.environ.get("WHISPER", "").lower() in {"1", "true", "sim"}:
        # ~460 MB em disco frio. Fora daqui, áudio vira pedido para escrever, que é o
        # que o Transcritor já responde sozinho quando o modelo não carregou.
        threading.Thread(target=transcritor.carregar, daemon=True).start()
    return nucleo, canal


def main() -> None:
    # Na hospedagem as variáveis vêm do ambiente e não há `.env` nenhum, porque a imagem não o
    # copia de propósito. `carregar_env` encerra o processo quando o arquivo falta, que é
    # o certo na máquina de quem desenvolve e é morte no boot em produção.
    if (env := RAIZ / ".env").exists():
        carregar_env(env)
    configurar_log()
    Servidor.segredo = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    Servidor.nucleo, Servidor.canal = montar()
    try:
        porta = int(os.environ.get("PORT") or 8000)
    except ValueError:
        sys.exit("PORT precisa ser um número. A plataforma injeta sozinha; não defina.")
    log.info("servidor em 0.0.0.0:%d, painel /%s, webhook POST /telegram/…", porta, PAINEL)
    # 0.0.0.0 é obrigatório atrás do proxy da plataforma, que faz o TLS na borda.
    ThreadingHTTPServer(("0.0.0.0", porta),
                        partial(Servidor, directory=str(RAIZ))).serve_forever()


if __name__ == "__main__":
    main()
