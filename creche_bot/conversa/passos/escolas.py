"""Blocos 6 e 7 — busca das escolas e a lista ordenada de preferência.

## O problema que este arquivo resolve

O roteiro pede "seleção múltipla ordenável". O WhatsApp não tem esse widget: são no
máximo 3 botões ou 10 itens de lista, sem ordenação.

A solução é montar a ordem INCREMENTALMENTE. Cada toque acrescenta uma preferência, o bot
confirma a posição e mostra o que sobrou. Em toda tela cabem 3 botões: as escolas
restantes e o "Pronto". A ordem sai da sequência de toques.
"""

from __future__ import annotations

import re
from datetime import date

from creche_bot.backend.porta import BackendIndisponivel
from creche_bot.canal.tipos import Botao, MensagemSaida, botoes_nomeados
from creche_bot.conversa.sessao import Passo
from creche_bot.dominio.tipos import VagaSugerida

FAIXA = {"alta": "💚", "media": "💛", "baixa": "🧡", "sem_vaga": "🤍"}
ORDINAL = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣"}


def num(v: float, casas: int = 1) -> str:
    """Vírgula decimal. É produto brasileiro; ponto denuncia software estrangeiro."""
    return f"{v:.{casas}f}".replace(".", ",")


def _achatar(v: VagaSugerida) -> dict:
    return {"id": v.id_escola, "nome": v.nome, "bairro": v.bairro, "endereco": v.endereco,
            "lat": v.lat, "lng": v.lng, "vagas": v.vagas_disponiveis,
            "nota": v.nota_corte.pontos, "ano_nota": v.nota_corte.ano,
            "sem_nota": v.nota_corte.indisponivel, "faixa": v.faixa,
            "km": v.distancia_km, "horario": v.horario_atendimento}


def _linha(e: dict) -> str:
    nota = ("nota de corte ainda não divulgada" if e["sem_nota"]
            else f"nota de corte {num(e['nota'])} em {e['ano_nota']}")
    return (f"🏫 {e['nome']}\n"
            f"   {e['bairro']} · {num(e['km'])} km · {e['vagas']} vagas\n"
            f"   {FAIXA[e['faixa']]} {nota}")


def localizacao(p: Passo) -> MensagemSaida:
    local = p.texto.strip()
    if len(re.sub(r"\D", "", local)) not in (0, 8) or len(local) < 3:
        return MensagemSaida(p.txt("local_invalido"))

    p.dados["local"] = local
    try:
        sugestoes = p.backend.escolas_proximas(
            local, date.fromisoformat(p.dados["data_nascimento"]), n=3)
    except BackendIndisponivel:
        return MensagemSaida(p.txt("backend_fora"))

    if not sugestoes:
        return MensagemSaida(p.txt("sem_escolas"))

    p.dados["escolas"] = [_achatar(v) for v in sugestoes]
    p.dados["preferencias"] = []
    p.ir("ESCOLHA")
    return _painel(p)


def _restantes(p: Passo) -> list[dict]:
    escolhidas = set(p.dados["preferencias"])
    return [e for e in p.dados["escolas"] if e["id"] not in escolhidas]


def _painel(p: Passo) -> MensagemSaida:
    escolas = p.dados["escolas"]
    corpo = "\n\n".join(_linha(e) for e in escolas)
    return MensagemSaida(
        f"Encontrei essas creches mais próximas de você:\n\n{corpo}\n\n"
        f"A nota de corte é a pontuação do último aprovado no ano passado — serve de "
        f"referência, não é garantia.\n\n{p.txt('escolha_ordenada')}",
        botoes=botoes_nomeados([(f"esc:{e['id']}", e["nome"]) for e in escolas]),
    )


def escolha(p: Passo) -> MensagemSaida:
    if p.msg.escolha == "pronto":
        return _confirmar(p)

    if not (p.msg.escolha or "").startswith("esc:"):
        return _painel(p) if not p.dados["preferencias"] else _proxima(p)

    p.dados["preferencias"].append(p.msg.escolha[4:])

    if not _restantes(p):
        return _confirmar(p)
    return _proxima(p)


def _proxima(p: Passo) -> MensagemSaida:
    posicao = len(p.dados["preferencias"])
    ultima = next(e for e in p.dados["escolas"]
                  if e["id"] == p.dados["preferencias"][-1])
    restantes = _restantes(p)

    # 2 restantes + "Pronto" = 3 botões. Sempre cabe.
    botoes = botoes_nomeados([(f"esc:{e['id']}", e["nome"]) for e in restantes[:2]])
    return MensagemSaida(
        p.txt("mais_uma", posicao=f"{ORDINAL[posicao]} {ultima['nome']}"),
        botoes=(*botoes, Botao("pronto", "Pronto, é só isso")),
    )


def _confirmar(p: Passo) -> MensagemSaida:
    p.ir("CONFIRMA_ESCOLAS")
    nomes = {e["id"]: e["nome"] for e in p.dados["escolas"]}
    lista = "\n".join(f"{ORDINAL[i]} {nomes[x]}"
                      for i, x in enumerate(p.dados["preferencias"], 1))
    return MensagemSaida(
        f"Sua lista final, em ordem de preferência:\n\n{lista}\n\nPosso confirmar?",
        botoes=(Botao("confirma", "Confirmar"), Botao("refazer", "Quero alterar")),
    )


def confirma_escolas(p: Passo) -> MensagemSaida:
    if p.msg.escolha == "refazer":
        p.dados["preferencias"] = []
        p.ir("ESCOLHA")
        return _painel(p)

    if p.msg.escolha == "confirma":
        p.ir("ENTREGA")
        return MensagemSaida(
            p.txt("como_entregar"),
            botoes=(Botao("whatsapp", "Enviar por aqui"),
                    Botao("creche", "Levar na creche"),
                    Botao("cras", "Levar num CRAS")),
        )

    return _confirmar(p)
