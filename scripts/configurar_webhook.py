"""Aponta o Telegram para o servidor hospedado, ou tira o webhook para voltar ao polling.

    python scripts/configurar_webhook.py https://seu-app.up.railway.app
    python scripts/configurar_webhook.py --ver
    python scripts/configurar_webhook.py --remover     # volta para `python -m creche_bot`

Webhook e long polling são exclusivos: com o webhook registrado, `getUpdates` passa a
responder erro. É por isso que o `--remover` existe: sem ele, quem quiser depurar na
própria máquina depois do deploy não consegue.

Lê `TELEGRAM_TOKEN` e `TELEGRAM_WEBHOOK_SECRET` do ambiente ou do `.env`.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from creche_bot.segredos import carregar_env  # noqa: E402

API = "https://api.telegram.org/bot{token}/{metodo}"

# Só o que o bot trata. Sem esta lista o Telegram manda edição de mensagem, entrada em
# canal e reação de emoji, tudo o que `_traduzir` descarta, pago em requisição.
ATUALIZACOES = ["message", "callback_query"]


def chamar(token: str, metodo: str, **params: object) -> dict:
    dados = urllib.parse.urlencode(
        {k: (json.dumps(v) if isinstance(v, list | dict) else v)
         for k, v in params.items() if v is not None}).encode()
    pedido = urllib.request.Request(API.format(token=token, metodo=metodo), data=dados)
    try:
        with urllib.request.urlopen(pedido, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as erro:
        return json.load(erro)


def main() -> None:
    carregar_env(RAIZ / ".env")
    token = os.environ.get("TELEGRAM_TOKEN", "")
    if not token or token.startswith("coloque"):
        sys.exit("TELEGRAM_TOKEN não configurado. Veja docs/TELEGRAM.md")

    if "--ver" in sys.argv:
        info = chamar(token, "getWebhookInfo").get("result", {})
        url = info.get("url") or "(nenhum, o bot está em long polling)"
        # A URL carrega o segredo no caminho: mostra só até o /telegram/.
        visivel = url.split("/telegram/")[0] + ("/telegram/…" if "/telegram/" in url else "")
        print("webhook:", visivel)
        for chave in ("pending_update_count", "last_error_message", "last_error_date",
                      "max_connections", "ip_address"):
            if info.get(chave) is not None:
                print(f"  {chave}: {info[chave]}")
        return

    if "--remover" in sys.argv:
        # `drop_pending_updates` fica FALSO: o que chegou enquanto o webhook valia é
        # conversa de família esperando resposta, não lixo.
        r = chamar(token, "deleteWebhook", drop_pending_updates=False)
        print("webhook removido, `python -m creche_bot` volta a funcionar"
              if r.get("ok") else f"falhou: {r}")
        return

    base = next((a for a in sys.argv[1:] if a.startswith("http")), "")
    if not base:
        sys.exit(__doc__)
    if not base.startswith("https://"):
        sys.exit("o Telegram só aceita webhook em https, e a URL do Railway já é https")

    segredo = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    if not segredo:
        sys.exit("TELEGRAM_WEBHOOK_SECRET não configurado. Gere um:\n"
                 "  python -c \"import secrets; print(secrets.token_urlsafe(32))\"")

    r = chamar(token, "setWebhook",
               url=f"{base.rstrip('/')}/telegram/{segredo}",
               secret_token=segredo,
               allowed_updates=ATUALIZACOES,
               drop_pending_updates=True)
    if not r.get("ok"):
        sys.exit(f"o Telegram recusou: {r.get('description', r)}")
    print(f"webhook apontado para {base.rstrip('/')}/telegram/…")
    print("confira com: python scripts/configurar_webhook.py --ver")


if __name__ == "__main__":
    main()
