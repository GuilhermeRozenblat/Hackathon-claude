"""Serve o painel e conta o que o bot gravou no banco.

    python scripts/painel.py                # http://localhost:8000
    python scripts/painel.py --porta 9000
    python scripts/painel.py --snapshot     # regrava o bloco embutido no HTML

Diagnóstico e demonstração, não produção: sem autenticação, sem TLS, uma requisição por
vez. É para rodar na máquina de quem desenvolve.

**Por que o SQL mora aqui e não em `creche_bot/`.** A fronteira do projeto diz que só
`creche_bot/dados/` conhece banco, e há teste varrendo o pacote (`make fronteira`). O
painel precisa de agregado que a `Repositorio` não expõe, e não vale alargar um contrato
congelado, usado por quatro trilhas, por causa de uma tela de demonstração. `scripts/` é
onde `verificar_banco.py` já fala com o Postgres pelo mesmo motivo.

**O que sai daqui é contagem, nunca conteúdo.** Nenhuma query seleciona o VALOR de coluna
de pessoa: de `cadastro` sai quantas linhas têm cada campo preenchido, nunca o campo. Os
únicos textos que atravessam são vocabulário do sistema (estado da conversa, código de
critério, chave de template) e nome de creche, que é público e está nos CSVs. Ver a
regra de log em `CLAUDE.md` e a LGPD art. 11 em `docs/DECISOES.md`.

**A raiz do repositório NÃO é servida.** Só a lista de `PUBLICOS` sai pela rede, e um
`http.server` solto aqui entregaria `.env`, `creche.db` e `.git/` para quem pedisse.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import UTC, datetime
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from creche_bot.segredos import carregar_env  # noqa: E402

PAINEL = "creche-conectada.html"
CSVS = "creche_bot/MapaFilaCreche"

# Allowlist: o painel e os seis CSVs que ele lê. Nada mais é alcançável.
PUBLICOS = frozenset(
    [PAINEL] + [f"{CSVS}/{f.name}" for f in (RAIZ / CSVS).glob("*.csv")]
)

# As colunas de `cadastro` cujo PREENCHIMENTO interessa medir: quantas linhas têm valor,
# nunca qual. `id`, `contato_id` e os timestamps ficam de fora: são sempre preenchidos.
# Na ordem em que a conversa as preenche: assim a barra vira o funil de abandono, e o
# degrau entre duas linhas vizinhas é onde a família parou.
COLUNAS_CADASTRO = (
    "documento_crianca", "nascimento_crianca", "grupamento", "origem", "nome_crianca",
    "nome_responsavel", "cpf_responsavel", "telefone", "email",
    "cep", "numero", "logradouro", "bairro", "lat", "lng", "horario",
)

TABELAS = (
    "contato", "identidade_canal", "consentimento", "sessao", "inscricao", "cadastro",
    "resposta_criterio", "preferencia_escola", "evento_inscricao", "outbox", "marca",
)


def consultas(schema: str = "creche") -> dict[str, str]:
    """As queries, em texto. Viajam no JSON para o painel mostrar o SQL que rodou.
    sem isto a tela teria uma cópia do SQL, e as duas versões divergiriam na primeira
    coluna nova."""
    s = schema
    return {
        "tabelas": "SELECT " + ",\n       ".join(
            f'(SELECT count(*) FROM {s}.{t}) AS "{t}"' for t in TABELAS),
        "cadastro": f"""SELECT count(*) FILTER (WHERE protocolo IS NULL)     AS abertos,
       count(*) FILTER (WHERE protocolo IS NOT NULL) AS enviados
  FROM {s}.cadastro""",
        # Só count() da coluna: quantas linhas têm valor, nunca qual valor.
        "preenchimento": "SELECT count(*) AS total,\n       " + ",\n       ".join(
            f'count({c}) AS "{c}"' for c in COLUNAS_CADASTRO) + f"\n  FROM {s}.cadastro",
        "sessoes": f"""SELECT estado, count(*) AS n
  FROM {s}.sessao GROUP BY estado ORDER BY n DESC, estado""",
        "origens": f"""SELECT coalesce(origem, 'ainda não respondeu') AS origem,
       count(*) AS n
  FROM {s}.cadastro GROUP BY origem ORDER BY n DESC, origem""",
        "criterios": f"""SELECT codigo,
       count(*)                          AS respostas,
       count(*) FILTER (WHERE declarado)  AS declarados,
       count(*) FILTER (WHERE comprovado) AS comprovados,
       bool_or(sensivel)                 AS sensivel
  FROM {s}.resposta_criterio
 GROUP BY codigo ORDER BY declarados DESC, codigo""",
        # `chance_media` é a estimativa que estava na TELA quando a família escolheu,
        # não uma conta refeita agora: é o que permite auditar a decisão depois, mesmo
        # quando os CSVs virarem os do ano seguinte.
        "preferencias": f"""SELECT id_escola,
       max(nome_escola)                     AS nome_escola,
       count(*)                             AS escolhas,
       count(*) FILTER (WHERE posicao = 1)  AS primeiras,
       count(*) FILTER (WHERE vaga_ociosa)  AS com_vaga_ociosa,
       -- `::float8` no fim porque `numeric` chega ao JSON como string ("1.20"), e a
       -- tela então compara texto com número. Número sai daqui como número.
       round(avg(distancia_km)::numeric, 2)::float8 AS km_medio,
       round(avg(chance)::numeric, 3)::float8       AS chance_media,
       max(ano_referencia)                  AS ano_referencia
  FROM {s}.preferencia_escola
 GROUP BY id_escola ORDER BY escolhas DESC, id_escola LIMIT 25""",
        "eventos": f"""SELECT tipo, etapa_codigo, count(*) AS n
  FROM {s}.evento_inscricao
 GROUP BY tipo, etapa_codigo ORDER BY n DESC, etapa_codigo""",
        "outbox": f"""SELECT
       count(*) FILTER (WHERE enviado_em IS NULL AND tentativas < 5)   AS pendentes,
       count(*) FILTER (WHERE enviado_em IS NOT NULL)                  AS enviados,
       count(*) FILTER (WHERE enviado_em IS NULL AND tentativas >= 5)  AS desistidos
  FROM {s}.outbox""",
    }


def contagens(dsn: str, schema: str = "creche") -> dict:
    """Um retrato agregado do schema. Só COUNT, SUM e GROUP BY."""
    import psycopg
    from psycopg.rows import dict_row

    sql = consultas(schema)
    with psycopg.connect(dsn, connect_timeout=8) as con:
        con.read_only = True
        with con.cursor(row_factory=dict_row) as cur:
            def uma(chave: str) -> dict:
                cur.execute(sql[chave])
                return cur.fetchone() or {}

            def varias(chave: str) -> list[dict]:
                cur.execute(sql[chave])
                return cur.fetchall()

            campos = uma("preenchimento")
            total = campos.pop("total", 0)
            return {
                "gerado_em": datetime.now(UTC).isoformat(timespec="seconds"),
                "origem": "postgres",
                "schema": schema,
                "sql": sql,
                "tabelas": uma("tabelas"),
                "cadastro": {
                    **uma("cadastro"),
                    "total": total,
                    "preenchimento": [{"coluna": c, "preenchidos": campos.get(c, 0)}
                                      for c in COLUNAS_CADASTRO],
                },
                "sessoes": varias("sessoes"),
                "origens": varias("origens"),
                "criterios": varias("criterios"),
                "preferencias": varias("preferencias"),
                "eventos": varias("eventos"),
                "outbox": uma("outbox"),
            }


def _dsn() -> str:
    # `carregar_env` encerra o processo quando o .env falta. Aqui isso roda DENTRO de uma
    # thread de requisição: mata a thread em silêncio e o cliente recebe "empty reply".
    # Na hospedagem não há .env nenhum, e as variáveis vêm do ambiente.
    if (env := RAIZ / ".env").exists():
        carregar_env(env)
    dsn = os.environ.get("DATABASE_URL", "")
    return "" if dsn.startswith("coloque") else dsn


class Painel(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        caminho = self.path.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        if caminho in ("", "index.html"):
            self.send_response(302)
            self.send_header("Location", "/" + PAINEL)
            self.end_headers()
            return
        if caminho == "api/banco.json":
            self._banco()
            return
        if caminho not in PUBLICOS:
            self.send_error(404, "fora da allowlist do painel")
            return
        super().do_GET()

    def _banco(self) -> None:
        dsn = _dsn()
        if not dsn:
            self._json({"erro": "sem DATABASE_URL", "origem": "ausente"}, 503)
            return
        try:
            corpo = contagens(dsn)
        except Exception as erro:
            # A classe do erro, nunca a mensagem: a DSN carrega a senha e psycopg a
            # repete no texto de "connection failed".
            self._json({"erro": type(erro).__name__, "origem": "erro"}, 502)
            return
        self._json(corpo, 200)

    def _json(self, corpo: dict, codigo: int) -> None:
        bruto = json.dumps(corpo, ensure_ascii=False, default=str).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(bruto)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(bruto)


BLOCO = re.compile(
    r'(<script type="application/json" id="snapshot-banco">\n).*?(\n</script>)', re.S)


def gravar_snapshot() -> None:
    """Regrava o bloco embutido no HTML, o que a página mostra quando não há servidor.

    Fica DENTRO do arquivo, e não num .json ao lado, pelo mesmo motivo dos CSVs: o painel
    tem que abrir com duplo clique e numa hospedagem estática sem perder o sentido.
    """
    dsn = _dsn()
    if not dsn:
        sys.exit("DATABASE_URL não configurado. Veja docs/BANCO.md")
    corpo = contagens(dsn)
    corpo["origem"] = "snapshot"
    alvo = RAIZ / PAINEL
    texto = alvo.read_text(encoding="utf-8")
    novo, n = BLOCO.subn(
        lambda m: m.group(1) + json.dumps(corpo, ensure_ascii=False, indent=1,
                                          default=str) + m.group(2),
        texto, count=1)
    if not n:
        sys.exit(f'bloco <script id="snapshot-banco"> não encontrado em {PAINEL}')
    alvo.write_text(novo, encoding="utf-8")
    print(f"snapshot de {corpo['gerado_em']} gravado em {PAINEL}")


def main() -> None:
    if "--snapshot" in sys.argv:
        gravar_snapshot()
        return
    porta = 8000
    if "--porta" in sys.argv:
        porta = int(sys.argv[sys.argv.index("--porta") + 1])
    banco = "ligado" if _dsn() else "sem DATABASE_URL (a aba Banco cai no snapshot)"
    print(f"painel em http://localhost:{porta}/{PAINEL}\nbanco: {banco}\nCtrl+C para parar")
    servidor = HTTPServer(("127.0.0.1", porta),
                          partial(Painel, directory=str(RAIZ)))
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrado.")


if __name__ == "__main__":
    main()
