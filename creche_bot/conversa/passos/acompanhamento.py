"""Efetivar a inscrição e narrar em que etapa a pessoa está.

O comportamento sai de `etapa.tipo`, NUNCA de `etapa.codigo`: o código é vocabulário do
backend e muda por município; o tipo é nosso e tem cinco valores.
"""

from __future__ import annotations

from creche_bot.backend.porta import BackendIndisponivel
from creche_bot.canal.tipos import Botao, Local, MensagemSaida
from creche_bot.conversa.sessao import Passo
from creche_bot.dominio.tipos import Situacao


def narrar(sit: Situacao, nome: str) -> MensagemSaida:
    e = sit.etapa
    cabecalho = (f"Inscrição de {nome} na {sit.nome_escola}\n"
                 f"Passo {e.ordem} de {e.total} — {e.titulo}")

    if e.tipo == "acao_no_chat":
        itens = "\n".join(f"• {x.titulo}" for x in e.pendencias)
        prazo = f"\n\nPrazo: {e.prazo:%d/%m}" if e.prazo else ""
        return MensagemSaida(f"{cabecalho}\n\nFalta você me mandar:\n{itens}{prazo}",
                             figurinha="atencao")

    if e.tipo == "acao_presencial":
        prazo = f"\nAté {e.prazo:%d/%m}" if e.prazo else ""
        return MensagemSaida(
            f"{cabecalho}\n\nLeve os documentos originais em:\n{e.endereco_entrega}{prazo}",
            local=(Local(e.lat, e.lng, sit.nome_escola, e.endereco_entrega)
                   if e.lat is not None else None),
            figurinha="mapa",
        )

    if e.tipo == "concluida":
        return MensagemSaida(f"CONSEGUIU! {nome} tem vaga na {sit.nome_escola} 🎉\n\n"
                             "Parabéns, viu. Você fez tudo certinho.", figurinha="festa")

    if e.tipo == "encerrada":
        return MensagemSaida(
            f"{cabecalho}\n\nDessa vez não deu 🫂 Mas tem outras creches com vaga e eu te "
            "ajudo a tentar de novo.",
            botoes=(Botao("recomecar", "Ver outras"),), figurinha="abraco")

    # "aguardando" e qualquer etapa desconhecida caem aqui: informa e NÃO cobra nada.
    return MensagemSaida(f"{cabecalho}\n\nTá tudo certo, é só esperar. "
                         "Eu te aviso assim que mudar 💚", figurinha="coracao")


def acompanhamento(p: Passo) -> MensagemSaida:
    if p.msg.escolha == "recomecar":
        for chave in ("escolas", "preferencias", "protocolo", "forma_entrega"):
            p.dados.pop(chave, None)
        p.ir("LOCALIZACAO")
        return MensagemSaida(p.txt("pedir_local"))

    protocolo = p.dados.get("protocolo")
    if not protocolo:
        p.ir("INICIO")
        return MensagemSaida(p.txt("sem_inscricao"))

    try:
        sit = p.backend.situacao(protocolo)
    except (BackendIndisponivel, KeyError):
        return MensagemSaida(p.txt("backend_fora"))

    return narrar(sit, p.dados.get("nome_candidato", "o candidato").split()[0])
