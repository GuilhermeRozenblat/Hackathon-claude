"""Servidor estático do painel `creche-conectada-v2.html`.

Só stdlib — o painel é um arquivo só, não precisa de framework. Serve na porta que
o Railway injeta em `$PORT`.

A regra que importa aqui é o que **não** é público. O servidor não anda pelo disco:
ele tem um dicionário de caminhos permitidos, montado no import, e tudo fora dele
responde 404. Um `http.server` comum serviria o diretório inteiro — e o diretório
inteiro tem `.env` com token do Telegram, chave da Anthropic e senha do Postgres.
"""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PAGINA = RAIZ / "creche-conectada-v2.html"
PASTA_CSV = RAIZ / "creche_bot" / "MapaFilaCreche"

HTML = "text/html; charset=utf-8"
CSV = "text/csv; charset=utf-8"


def _publicos() -> dict[str, tuple[Path, str]]:
    """O conjunto fechado do que sai daqui. Nada é resolvido a partir da URL."""
    mapa: dict[str, tuple[Path, str]] = {
        "/": (PAGINA, HTML),
        "/index.html": (PAGINA, HTML),
    }
    # Os CSVs para o `fetch()` da página. Sem eles o painel ainda funciona pelos
    # blocos embutidos, mas servi-los deixa o jurado abrir o dado bruto.
    for csv in sorted(PASTA_CSV.glob("*.csv")):
        mapa[f"/creche_bot/MapaFilaCreche/{csv.name}"] = (csv, CSV)
    return mapa


PUBLICOS = _publicos()


class Handler(BaseHTTPRequestHandler):
    server_version = "creche-conectada"
    sys_version = ""

    def do_GET(self) -> None:
        self._responder(corpo=True)

    def do_HEAD(self) -> None:
        self._responder(corpo=False)

    def _responder(self, *, corpo: bool) -> None:
        caminho = self.path.split("?", 1)[0].split("#", 1)[0]
        alvo = PUBLICOS.get(caminho)
        if alvo is None:
            self._erro_404()
            return

        arquivo, tipo = alvo
        try:
            dados = arquivo.read_bytes()
        except OSError:
            self.send_error(500, "arquivo indisponível")
            return

        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "public, max-age=300")
        # O painel não embute nada de fora e não tem formulário: pode ser estrito.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if corpo:
            self.wfile.write(dados)

    def _erro_404(self) -> None:
        corpo = (
            "<!doctype html><meta charset=utf-8>"
            "<title>404</title>"
            "<p style='font:16px system-ui;padding:40px'>Nada aqui. "
            "O painel está em <a href='/'>/</a>.</p>"
        ).encode()
        self.send_response(404)
        self.send_header("Content-Type", HTML)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, formato: str, *args: object) -> None:
        # Caminho e status bastam. Sem User-Agent, sem query, sem IP do visitante.
        print(f"{self.command} {self.path.split('?', 1)[0]} {args[1] if len(args) > 1 else ''}", flush=True)


def main() -> None:
    if not PAGINA.exists():
        raise SystemExit(f"não achei {PAGINA} — a imagem foi montada errado")
    porta = int(os.environ.get("PORT", "8080"))
    print(f"servindo {len(PUBLICOS)} caminhos em 0.0.0.0:{porta}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", porta), Handler).serve_forever()


if __name__ == "__main__":
    main()
