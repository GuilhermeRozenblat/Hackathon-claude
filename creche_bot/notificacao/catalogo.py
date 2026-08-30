"""ChaveTemplate + variáveis -> MensagemSaida, por canal.

É aqui que o flip fica barato: a outbox guarda só a chave, e cada canal renderiza do seu
jeito. No Telegram, texto livre com emoji. No WhatsApp (Fase 3), template aprovado pela
Meta com botão que reabre a janela de 24h.

Nenhum texto aqui promete vaga, cita pontuação ou dá posição na fila.
"""

from __future__ import annotations

from typing import Any

from creche_bot.canal.tipos import Botao, Local, MensagemSaida
from creche_bot.notificacao.chaves import VARIAVEIS, ChaveTemplate

_TELEGRAM: dict[ChaveTemplate, tuple[str, str]] = {
    ChaveTemplate.INSCRICAO_CONFIRMADA: (
        "Pronto! A inscrição de {nome_crianca} está feita 🎉\n\n"
        "Número: {numero}\nGuarde esse número. Eu te aviso de cada novidade por aqui.",
        "festa"),
    ChaveTemplate.ETAPA_AVANCOU: (
        "Novidade sobre a inscrição de {nome_crianca} 👀\n\n{titulo_etapa}\n\n"
        "Não precisa fazer nada agora, eu te aviso.", "comemorando"),
    # R1 — ataca direto os 8,0% de validação documental.
    ChaveTemplate.DOCUMENTO_PENDENTE: (
        "Oi! Faltou um documento na inscrição de {nome_crianca}:\n\n{pendencias}\n\n"
        "Sem ele esse critério não conta na classificação. Pode mandar a foto por aqui? 📎",
        "atencao"),
    ChaveTemplate.ACAO_PRESENCIAL: (
        "Precisa dar uma passada na creche pela inscrição de {nome_crianca} 🚀\n\n"
        "{nome_escola}\n{endereco}\nAté {prazo}\n\n"
        "Te mandei o endereço no mapa aqui embaixo.", "mapa"),
    # R2 — o turno que fecha o vazamento dos 7,7%.
    ChaveTemplate.CONVOCACAO: (
        "🎉 Boa notícia! Saiu vaga para {nome_crianca} na {nome_escola}.\n\n"
        "Você tem até {prazo} para confirmar.", "festa"),
    # R3 — reenvio quando o R2 não foi lido em 24h. Depois disso, escalona para a CRE.
    ChaveTemplate.LEMBRETE_CONVOCACAO: (
        "Passando para lembrar: a vaga de {nome_crianca} na {nome_escola} está esperando "
        "sua confirmação até {prazo}.\n\nSe não der, me avisa que eu registro.", "atencao"),
    ChaveTemplate.RESULTADO_CLASSIFICADA: (
        "Saiu o resultado de {nome_crianca}: classificada na {nome_escola}! 🎉",
        "festa"),
    ChaveTemplate.RESULTADO_NAO_CLASSIFICADA: (
        "Saiu o resultado da inscrição de {nome_crianca} 🫂\n\n"
        "Dessa vez não deu. Quem consegue te explicar o que houve é a CRE da sua região, "
        "pelo 1746. E eu te aviso quando o próximo processo abrir.", "abraco"),
    ChaveTemplate.LEMBRETE_INCOMPLETO: (
        "Oi, {nome_responsavel}! 👋\n\nSua inscrição ficou pela metade. Quer terminar? "
        "É rapidinho, e eu guardei tudo que a gente já preencheu.", "coracao"),
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
    if chave in (ChaveTemplate.CONVOCACAO, ChaveTemplate.LEMBRETE_CONVOCACAO):
        msg["botoes"] = (Botao("confirmar_vaga", "Confirmar vaga"),
                         Botao("nao_vou_poder", "Não vou poder"))
    if chave is ChaveTemplate.RESULTADO_NAO_CLASSIFICADA:
        msg["botoes"] = (Botao("avisar_proximo", "Quero ser avisada"),)
    if chave is ChaveTemplate.LEMBRETE_INCOMPLETO:
        msg["botoes"] = (Botao("retomar", "Continuar"),)

    return MensagemSaida(**msg)
