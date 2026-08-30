"""Bloco 6 — horário da vaga, painel de creches e a confirmação da escolha (bloco 7).

## O que este painel PODE mostrar

Distância, vaga aberta agora e concorrência do ano passado. São fatos verificáveis.

## O que ele NUNCA mostra: nota de corte

O roteiro pede "nota de corte: X pontos" em cada creche. Esse número não existe no
momento da conversa: a classificação do processo vigente só roda depois do fechamento
das inscrições. E o teto da régua foi 465 pontos em 2023 e 100 em
2024, então histórico de pontuação não é comparável entre anos. Prometer isso sobre
alocação de vaga pública é passivo.

## Múltipla ordenável sem widget de múltipla ordenável

O WhatsApp tem 3 botões ou 10 itens de lista, sem ordenação. A ordem sai da SEQUÊNCIA DE
TOQUES: cada toque acrescenta uma preferência e o bot confirma a posição. E "Pronto"
aparece desde o primeiro toque, porque forçar 5 opções não muda o desfecho — em 2025 a
taxa de atendimento foi 68,8% com 1 opção e 69,7% com 5.
"""

from __future__ import annotations

from creche_bot.backend.porta import BackendIndisponivel
from creche_bot.canal.tipos import Botao, MensagemSaida, botoes_nomeados
from creche_bot.conversa.sessao import Passo
from creche_bot.dominio.tipos import (
    GRUPAMENTO_LEGIVEL,
    HORARIO_LEGIVEL,
    VagaSugerida,
    grupamento_de,
)

ORDINAL = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣"}
BOTOES_HORARIO = (Botao("integral", "Integral"), Botao("parcial", "Parcial"))


def num(v: float, casas: int = 1) -> str:
    """Vírgula decimal. É produto brasileiro; ponto denuncia software estrangeiro."""
    return f"{v:.{casas}f}".replace(".", ",")


def distancia(km: float, minutos: int) -> str:
    if km < 1:
        return f"{round(km * 1000)} m (uns {minutos} min a pé)"
    return f"{num(km)} km"


# ---------------------------------------------------- bloco 6, antes do painel
def pedir_horario(p: Passo) -> MensagemSaida:
    _garantir_grupamento(p)
    p.ir("HORARIO")
    return MensagemSaida(p.txt("pedir_horario"), botoes=BOTOES_HORARIO)


def _garantir_grupamento(p: Passo) -> None:
    """Derivado da data de nascimento — nunca perguntado. "Berçário" e "Maternal I" são
    vocabulário interno da rede, não de família."""
    if p.dados.get("grupamento") or "nascimento_crianca" not in p.dados:
        return
    from datetime import date

    p.dados["grupamento"] = grupamento_de(
        date.fromisoformat(p.dados["nascimento_crianca"]), p.backend.data_de_corte())


def horario(p: Passo) -> MensagemSaida:
    if p.msg.escolha not in ("integral", "parcial"):
        return p.diz("nao_entendi", botoes=BOTOES_HORARIO)
    p.dados["horario"] = p.msg.escolha
    return sugerir(p)


# ------------------------------------------------------- bloco 6, o painel
def _achatar(v: VagaSugerida) -> dict:
    return {"id": v.id_escola, "nome": v.nome, "endereco": v.endereco,
            "lat": v.lat, "lng": v.lng, "km": v.distancia_km,
            "minutos": v.minutos_a_pe, "ociosa": v.vaga_ociosa,
            "referencia": v.referencia,
            "concorrencia": (None if v.concorrencia is None else
                             [v.concorrencia.familias_por_vaga, v.concorrencia.ano])}


def _linha(e: dict, posicao: int) -> str:
    partes = [distancia(e["km"], e["minutos"])]
    if e["referencia"]:
        # A família reconhece o lugar pelo apelido, não pelo nome oficial.
        partes.append(e["referencia"])
    if e["ociosa"]:
        partes.append("🟢 tem vaga aberta agora")
    elif e["concorrencia"]:
        por_vaga, ano = e["concorrencia"]
        partes.append(f"em {ano}, {num(por_vaga, 0)} famílias por vaga")
    return f"{ORDINAL[posicao]} {e['nome']}\n   " + " · ".join(partes)


def sugerir(p: Passo) -> MensagemSaida:
    from creche_bot.conversa.passos.endereco import endereco_de

    try:
        sugestoes = p.backend.escolas_proximas(
            endereco_de(p.dados), p.dados["grupamento"], p.dados["horario"], n=3)
    except BackendIndisponivel:
        return p.diz("backend_fora")

    if not sugestoes:
        p.ir("ESCOLAS")
        return p.diz("sem_escolas")

    p.dados["escolas"] = [_achatar(v) for v in sugestoes]
    p.dados["preferencias"] = []
    p.ir("ESCOLAS")
    return _painel(p)


def _painel(p: Passo) -> MensagemSaida:
    escolas = p.dados["escolas"]
    corpo = "\n\n".join(_linha(e, i) for i, e in enumerate(escolas, 1))
    return p.diz("achei_creches",
                 grupamento=GRUPAMENTO_LEGIVEL[p.dados["grupamento"]],
                 horario=HORARIO_LEGIVEL[p.dados["horario"]], creches=corpo,
                 botoes=botoes_nomeados([(f"esc:{e['id']}", e["nome"]) for e in escolas]))


def _restantes(p: Passo) -> list[dict]:
    escolhidas = set(p.dados["preferencias"])
    return [e for e in p.dados["escolas"] if e["id"] not in escolhidas]


def escolher(p: Passo) -> MensagemSaida:
    if p.msg.escolha == "pronto":
        return _confirmar(p)

    if not (p.msg.escolha or "").startswith("esc:"):
        return _painel(p) if not p.dados.get("preferencias") else _mais_uma(p)

    p.dados["preferencias"].append(p.msg.escolha[4:])
    return _confirmar(p) if not _restantes(p) else _mais_uma(p)


def _mais_uma(p: Passo) -> MensagemSaida:
    posicao = len(p.dados["preferencias"])
    ultima = next(e for e in p.dados["escolas"]
                  if e["id"] == p.dados["preferencias"][-1])
    # 2 restantes + "Pronto" = 3 botões. Sempre cabe.
    botoes = botoes_nomeados([(f"esc:{e['id']}", e["nome"]) for e in _restantes(p)[:2]])
    return p.diz("mais_uma", posicao=f"{ORDINAL[posicao]} {ultima['nome']}",
                 botoes=(*botoes, Botao("pronto", "Pronto, é só isso")))


# ------------------------------------------------------------------ bloco 7
def _confirmar(p: Passo) -> MensagemSaida:
    if not p.dados["preferencias"]:
        return _painel(p)
    return confirmar_escolhas(p)


def _escolhidas(p: Passo) -> str:
    nomes = {e["id"]: e["nome"] for e in p.dados["escolas"]}
    return "\n".join(f"{ORDINAL[i]} {nomes.get(x, x)}"
                     for i, x in enumerate(p.dados["preferencias"], 1))


def confirmar_escolhas(p: Passo) -> MensagemSaida:
    p.ir("CONFIRMA_ESCOLAS")
    return p.diz("confirmar_escolhas", escolhas=_escolhidas(p),
                 botoes=(Botao("confirmar", "Confirmar"),
                         Botao("alterar", "Quero alterar")))


def escolhas_confirmadas(p: Passo) -> MensagemSaida:
    from creche_bot.conversa.passos.criterios import comecar

    if p.msg.escolha == "confirmar":
        return comecar(p)

    if p.msg.escolha == "alterar":
        p.dados["preferencias"] = []
        p.ir("ESCOLAS")
        return _painel(p)

    return confirmar_escolhas(p)
