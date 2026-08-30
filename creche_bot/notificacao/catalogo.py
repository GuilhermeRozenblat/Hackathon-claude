"""ChaveTemplate + variáveis -> MensagemSaida, por canal.

É aqui que o flip fica barato: a outbox guarda só a chave, e cada canal renderiza do seu
jeito. No Telegram, texto livre com emoji. No WhatsApp (Fase 3), template aprovado pela
Meta com botão que reabre a janela de 24h.
"""

from __future__ import annotations

from typing import Any

from creche_bot.canal.tipos import Botao, Local, MensagemSaida
from creche_bot.notificacao.chaves import VARIAVEIS, ChaveTemplate

_TELEGRAM: dict[ChaveTemplate, tuple[str, str]] = {
    ChaveTemplate.INSCRICAO_CONFIRMADA: (
        "Pronto, {nome_crianca} tá inscrito(a) na {nome_escola}! 🎉\n\n"
        "Protocolo: {protocolo}\nVou te avisar de cada novidade.", "festa"),
    ChaveTemplate.ETAPA_AVANCOU: (
        "Novidade sobre {nome_crianca} 👀\n\n"
        "Agora está em: {titulo_etapa}\nPasso {ordem} de {total} — tá andando!\n\n"
        "Não precisa fazer nada agora, eu te aviso.", "comemorando"),
    ChaveTemplate.PENDENCIA_NO_CHAT: (
        "Oi! Falta pouco pra inscrição de {nome_crianca} 💚\n\n"
        "Preciso que você me mande por aqui:\n{pendencias}\n\nPrazo: {prazo}", "atencao"),
    ChaveTemplate.ACAO_PRESENCIAL: (
        "Chegou a hora de ir na creche, {nome_crianca} tá quase lá! 🚀\n\n"
        "Leve os documentos originais na {nome_escola}\n{endereco}\nAté {prazo}\n\n"
        "Te mandei o endereço no mapa aqui embaixo.", "mapa"),
    ChaveTemplate.RESULTADO_APROVADO: (
        "CONSEGUIU! {nome_crianca} tem vaga na {nome_escola}! 🎉🎉\n\n"
        "Parabéns, viu. Você fez tudo certinho.", "festa"),
    ChaveTemplate.RESULTADO_RECUSADO: (
        "Vim te contar sobre {nome_crianca} na {nome_escola} 🫂\n\n"
        "Dessa vez não deu. Mas isso não é o fim: tem outras creches com vaga aberta e eu "
        "te ajudo a tentar. Quer ver?", "abraco"),
    ChaveTemplate.LEMBRETE_INCOMPLETO: (
        "Oi, {nome_responsavel}! 👋\n\nSua inscrição ficou pela metade. Quer terminar? "
        "É rapidinho, tá quase.", "coracao"),
}


def renderizar(chave: ChaveTemplate, variaveis: dict[str, Any],
               canal: str = "telegram") -> MensagemSaida:
    faltando = set(VARIAVEIS[chave]) - set(variaveis)
    if faltando:
        # Falhar aqui, e não no envio: no WhatsApp uma variável faltando é erro em produção.
        raise ValueError(f"{chave}: faltam as variáveis {sorted(faltando)}")

    if canal != "telegram":
        raise NotImplementedError(f"canal {canal!r} — Fase 3, veja creche_bot/backend/CLAUDE.md")

    modelo, figurinha = _TELEGRAM[chave]
    msg: dict[str, Any] = {"texto": modelo.format(**variaveis), "figurinha": figurinha}

    if chave is ChaveTemplate.ACAO_PRESENCIAL and variaveis.get("lat") is not None:
        msg["local"] = Local(variaveis["lat"], variaveis["lng"],
                             variaveis["nome_escola"], variaveis["endereco"])
    if chave is ChaveTemplate.RESULTADO_RECUSADO:
        msg["botoes"] = (Botao("ver_outras", "Ver outras"), Botao("agora_nao", "Agora não"))
    if chave is ChaveTemplate.LEMBRETE_INCOMPLETO:
        msg["botoes"] = (Botao("retomar", "Bora terminar"),)

    return MensagemSaida(**msg)
