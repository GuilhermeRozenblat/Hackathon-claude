"""Prova que o bot do Telegram está configurado e que o contrato renderiza de verdade.

Diagnóstico, não produção: usa só a stdlib e não depende de nenhuma trilha estar pronta.
A Trilha A escreve o `canal/telegram.py` de verdade — este arquivo pode ser apagado depois.

    python scripts/verificar_telegram.py          # só confere o token
    python scripts/verificar_telegram.py --eco    # sobe um eco, para testar no celular
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from creche_bot.canal.tipos import Botao, MensagemSaida

API = "https://api.telegram.org/bot{token}/{metodo}"


def carregar_token() -> str:
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        env = Path(__file__).resolve().parent.parent / ".env"
        if env.exists():
            for linha in env.read_text().splitlines():
                if linha.startswith("TELEGRAM_TOKEN="):
                    token = linha.split("=", 1)[1].strip()
    if not token or token.startswith("coloque"):
        sys.exit("TELEGRAM_TOKEN não definido. Copie .env.example para .env e cole o token.")
    return token


def chamar(token: str, metodo: str, **params) -> dict:
    url = API.format(token=token, metodo=metodo)
    dados = urllib.parse.urlencode(
        {k: (json.dumps(v) if isinstance(v, dict | list) else v)
         for k, v in params.items() if v is not None}
    ).encode()
    try:
        with urllib.request.urlopen(url, data=dados, timeout=70) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        corpo = json.load(e)
        if e.code == 409:
            sys.exit(
                "409: outro processo já está fazendo polling com ESTE token.\n"
                "Feche a outra instância, ou crie um bot separado para cada dev."
            )
        sys.exit(f"{e.code}: {corpo.get('description', corpo)}")


def render(msg: MensagemSaida) -> dict:
    """Render mínimo, só para provar o contrato no Telegram real. Trilha A faz o de verdade."""
    payload: dict = {"text": msg.texto}          # sem parse_mode: texto puro, de propósito
    if msg.botoes:
        payload["reply_markup"] = {
            "inline_keyboard": [[{"text": b.rotulo, "callback_data": b.id} for b in msg.botoes]]
        }
    return payload


def main() -> None:
    token = carregar_token()

    eu = chamar(token, "getMe")["result"]
    print(f"✅ token válido — @{eu['username']} ({eu['first_name']})")
    print(f"   pode entrar em grupo: {eu.get('can_join_groups')}  "
          f"(recomendado: False, o bot trata documento de criança)")

    # Webhook velho faz getUpdates devolver 409. Limpar é idempotente.
    chamar(token, "deleteWebhook", drop_pending_updates=False)

    if "--eco" not in sys.argv:
        print("\nPara testar no celular: python scripts/verificar_telegram.py --eco")
        return

    print(f"\n🟢 eco no ar. Abra t.me/{eu['username']} e mande /start. Ctrl+C para parar.")
    offset = None
    while True:
        resp = chamar(token, "getUpdates", offset=offset, timeout=50)
        for upd in resp["result"]:
            offset = upd["update_id"] + 1

            if "callback_query" in upd:
                cq = upd["callback_query"]
                chamar(token, "answerCallbackQuery", callback_query_id=cq["id"])
                chat = cq["message"]["chat"]["id"]
                msg = MensagemSaida(f"Você tocou em: {cq['data']} ✅")
            elif "message" in upd:
                m = upd["message"]
                chat = m["chat"]["id"]
                if "photo" in m:
                    msg = MensagemSaida("Recebi sua foto 📸 (não guardei nada, isso é só um eco)")
                else:
                    msg = MensagemSaida(
                        f"Ouvi: {m.get('text', '(sem texto)')}\n\nO contrato aguenta 3 botões:",
                        botoes=(Botao("op1", "Jardim Flores"),
                                Botao("op2", "Pequeno Prínc"),
                                Botao("op3", "CEI Girassol")),
                    )
            else:
                continue

            chamar(token, "sendMessage", chat_id=chat, **render(msg))
            print(f"   ↔ chat {chat}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nencerrado.")
