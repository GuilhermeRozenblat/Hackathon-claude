"""O servidor da hospedagem: as guardas do webhook, a allowlist e o gzip.

Sobe um `ThreadingHTTPServer` de verdade numa porta efêmera, com canal e máquina de
mentira. É HTTP real, onde os erros deste arquivo aparecem, e nenhum deles apareceria
chamando os métodos direto.
"""

from __future__ import annotations

import gzip
import json
import threading
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer

import pytest

from creche_bot.canal.tipos import MensagemEntrada, MensagemSaida
from scripts.servidor import RAIZ, Servidor, _Vistos

SEGREDO = "segredo-de-teste"


class CanalFalso:
    def __init__(self) -> None:
        self.enviadas: list[tuple[str, MensagemSaida]] = []

    def receber(self, upd: dict) -> MensagemEntrada | None:
        msg = upd.get("message")
        if not msg:
            return None
        return MensagemEntrada(canal="telegram", id_externo=str(msg["chat"]["id"]),
                               id_mensagem=str(msg["message_id"]), texto=msg.get("text"))

    def enviar(self, id_externo: str, msg: MensagemSaida) -> None:
        self.enviadas.append((id_externo, msg))

    def avisar_processando(self, id_externo: str) -> None:
        pass


class NucleoFalso:
    def __init__(self) -> None:
        self.turnos: list[MensagemEntrada] = []

    def processar(self, entrada: MensagemEntrada) -> MensagemSaida:
        self.turnos.append(entrada)
        return MensagemSaida("oi")


@pytest.fixture
def servidor():
    canal, nucleo = CanalFalso(), NucleoFalso()
    Servidor.canal, Servidor.nucleo = canal, nucleo
    Servidor.segredo = SEGREDO
    Servidor.vistos = _Vistos()          # memória limpa a cada teste
    http = ThreadingHTTPServer(("127.0.0.1", 0), partial(Servidor, directory=str(RAIZ)))
    threading.Thread(target=http.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{http.server_address[1]}", canal, nucleo
    http.shutdown()


def pedir(url: str, dados: bytes | None = None,
          cabecalhos: dict | None = None) -> tuple[int, bytes, dict]:
    pedido = urllib.request.Request(url, data=dados, headers=cabecalhos or {})
    try:
        with urllib.request.urlopen(pedido, timeout=10) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def update(update_id: int = 1, texto: str = "/start") -> bytes:
    return json.dumps({"update_id": update_id,
                       "message": {"message_id": 7, "chat": {"id": 4242},
                                   "text": texto}}).encode()


# ------------------------------------------------------------------ guardas do webhook
def test_caminho_errado_nao_revela_que_existe_webhook(servidor):
    base, _, nucleo = servidor
    codigo, _, _ = pedir(f"{base}/telegram/chute", update())
    assert codigo == 404, "caminho errado tem que ser 404, não 403, porque 403 confirmaria a rota"
    assert nucleo.turnos == []


def test_sem_o_cabecalho_de_segredo_nao_passa(servidor):
    """O caminho pode vazar em log de proxy. O cabeçalho é a segunda tranca."""
    base, _, nucleo = servidor
    codigo, _, _ = pedir(f"{base}/telegram/{SEGREDO}", update())
    assert codigo == 403
    assert nucleo.turnos == []


def test_cabecalho_errado_nao_passa(servidor):
    base, _, nucleo = servidor
    codigo, _, _ = pedir(f"{base}/telegram/{SEGREDO}", update(),
                         {"X-Telegram-Bot-Api-Secret-Token": "outro"})
    assert codigo == 403
    assert nucleo.turnos == []


def test_json_invalido_nao_derruba_o_servidor(servidor):
    base, _, _ = servidor
    codigo, _, _ = pedir(f"{base}/telegram/{SEGREDO}", b"isto nao e json",
                         {"X-Telegram-Bot-Api-Secret-Token": SEGREDO})
    assert codigo == 400
    assert pedir(f"{base}/saude")[0] == 200, "o servidor continua de pé"


def test_update_valido_chega_na_maquina_e_a_resposta_volta(servidor):
    base, canal, nucleo = servidor
    codigo, _, _ = pedir(f"{base}/telegram/{SEGREDO}", update(texto="oi"),
                         {"X-Telegram-Bot-Api-Secret-Token": SEGREDO})
    assert codigo == 200
    assert [e.texto for e in nucleo.turnos] == ["oi"]
    assert canal.enviadas and canal.enviadas[0][0] == "4242"


# ------------------------------------------------------------------------ idempotência
def test_reenvio_do_telegram_nao_vira_mensagem_repetida(servidor):
    """O Telegram reenvia o update quando a resposta demora ou a conexão cai.

    Sem esta guarda, a rede tossindo faz o bot repetir a pergunta e contar a resposta
    duas vezes no cadastro.
    """
    base, canal, nucleo = servidor
    cab = {"X-Telegram-Bot-Api-Secret-Token": SEGREDO}
    for _ in range(3):
        assert pedir(f"{base}/telegram/{SEGREDO}", update(update_id=99), cab)[0] == 200
    assert len(nucleo.turnos) == 1, "três entregas do mesmo update_id, um turno só"
    assert len(canal.enviadas) == 1


def test_updates_diferentes_passam(servidor):
    base, _, nucleo = servidor
    cab = {"X-Telegram-Bot-Api-Secret-Token": SEGREDO}
    for i in (1, 2, 3):
        pedir(f"{base}/telegram/{SEGREDO}", update(update_id=i), cab)
    assert len(nucleo.turnos) == 3


def test_memoria_de_updates_nao_cresce_sem_fim():
    vistos = _Vistos(teto=3)
    for i in range(10):
        assert vistos.novo(i) is True
    assert vistos.novo(9) is False, "o recente continua lembrado"
    assert vistos.novo(0) is True, "o antigo saiu, e repetir vira turno novo, e é o preço"


def test_update_sem_id_sempre_passa():
    """Não é reenvio: é update que o Telegram mandou sem `update_id`. Melhor atender."""
    vistos = _Vistos()
    assert vistos.novo(None) is True
    assert vistos.novo(None) is True


# ------------------------------------------------------------- estático, gzip, allowlist
def test_painel_sai_comprimido_e_com_cache(servidor):
    base, _, _ = servidor
    codigo, corpo, cab = pedir(f"{base}/creche-conectada.html",
                               cabecalhos={"Accept-Encoding": "gzip"})
    assert codigo == 200
    assert cab.get("Content-Encoding") == "gzip"
    assert "max-age" in cab.get("Cache-Control", "")
    cru = gzip.decompress(corpo)
    assert len(corpo) * 2 < len(cru), "comprimir tem que valer a pena"
    assert cru.startswith(b"<!"), "e o que sai descomprimido é o painel"


def test_quem_nao_aceita_gzip_recebe_o_arquivo_cru(servidor):
    base, _, _ = servidor
    codigo, corpo, cab = pedir(f"{base}/creche-conectada.html",
                               cabecalhos={"Accept-Encoding": "identity"})
    assert codigo == 200
    assert "gzip" not in cab.get("Content-Encoding", "")
    assert corpo.startswith(b"<!")


@pytest.mark.parametrize("caminho", [".env", ".git/config", "creche.db",
                                     "scripts/servidor.py", "pyproject.toml"])
def test_a_allowlist_nao_deixa_sair_nada_alem_do_painel(servidor, caminho):
    """Um http.server solto na raiz entregaria o .env para quem pedisse."""
    base, _, _ = servidor
    assert pedir(f"{base}/{caminho}")[0] == 404


def test_saude_responde_para_o_healthcheck(servidor):
    base, _, _ = servidor
    codigo, corpo, _ = pedir(f"{base}/saude")
    assert codigo == 200
    assert json.loads(corpo) == {"ok": True}


def test_raiz_redireciona_com_content_length(servidor):
    """Em HTTP/1.1, resposta sem corpo precisa de Content-Length: 0, senão o cliente
    espera um corpo que nunca vem e só desiste no timeout."""
    base, _, _ = servidor
    pedido = urllib.request.Request(f"{base}/")

    class SemRedirecionar(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_a, **_k):
            return None

    abridor = urllib.request.build_opener(SemRedirecionar)
    try:
        with abridor.open(pedido, timeout=10) as r:
            codigo, cab = r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        codigo, cab = e.code, dict(e.headers)
    assert codigo == 302
    assert cab.get("Content-Length") == "0"
    assert "creche-conectada.html" in cab.get("Location", "")


# ------------------------------------------------------------ composição e a imagem
def test_montar_recusa_subir_sem_o_segredo_do_webhook(monkeypatch):
    """Sem segredo o webhook aceitaria qualquer POST. Melhor não subir do que subir aberto."""
    from scripts.servidor import montar

    monkeypatch.setenv("TELEGRAM_TOKEN", "8123456789:AAHumtokendementiraquetem35chars")
    monkeypatch.setattr(Servidor, "segredo", "")
    with pytest.raises(SystemExit) as saida:
        montar()
    assert "TELEGRAM_WEBHOOK_SECRET" in str(saida.value)


def test_montar_recusa_subir_sem_token(monkeypatch):
    from scripts.servidor import montar

    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.setattr(Servidor, "segredo", "seg")
    with pytest.raises(SystemExit) as saida:
        montar()
    assert "TELEGRAM_TOKEN" in str(saida.value)


def test_a_imagem_copia_tudo_que_o_servidor_serve():
    """O COPY do Dockerfile é uma allowlist: o que ele esquece vira 404 só em produção.

    Sem `docker build` de propósito — o teste tem que rodar em qualquer máquina.
    """
    from scripts.painel import PUBLICOS
    from scripts.servidor import RAIZ

    dockerfile = (RAIZ / "deploy" / "app.Dockerfile").read_text()
    copiados = [linha for linha in dockerfile.splitlines() if linha.startswith("COPY ")]
    junto = "\n".join(copiados)

    assert "creche_bot/" in junto, "o pacote do bot tem que entrar"
    assert "scripts/servidor.py" in junto, "o próprio servidor tem que entrar"
    for alvo in PUBLICOS:
        raiz = alvo.split("/")[0]
        assert raiz in junto, f"{alvo} é servido mas {raiz} não é copiado para a imagem"


def test_a_imagem_nao_copia_segredo_nem_teste():
    """`.env` e `tests/` dentro da imagem seriam superfície sem nenhum ganho."""
    from scripts.servidor import RAIZ

    dockerfile = (RAIZ / "deploy" / "app.Dockerfile").read_text()
    for proibido in (".env", "tests", "creche.db"):
        assert f"COPY {proibido}" not in dockerfile
    ignorados = (RAIZ / ".dockerignore").read_text()
    for exigido in (".env", "tests", ".git"):
        assert exigido in ignorados, f"{exigido} tem que estar no .dockerignore"
