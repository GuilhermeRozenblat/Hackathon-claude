"""Bloco 8 — como a documentação chega até a rede, e o protocolo.

Três caminhos, e eles NÃO são equivalentes:

  whatsapp → a família manda por aqui; sabemos exatamente quando chegou.
  creche   → entrega presencial; a creche confirma, e o backend nos conta.
  cras     → entrega no CRAS, que depois repassa à creche.

O terceiro tem uma lacuna conhecida do processo (não do código): hoje ninguém avisa
quando os documentos saem do CRAS e chegam à creche. Modelamos a etapa mesmo assim, com
o texto sendo honesto sobre o que ainda não sabemos — ver `ARQUITETURA.md` §11.1.
"""

from __future__ import annotations

from creche_bot.backend.porta import BackendIndisponivel
from creche_bot.canal.tipos import Botao, Local, MensagemSaida
from creche_bot.conversa.sessao import Passo
from creche_bot.dados.porta import Inscricao

FORMAS = {"whatsapp", "creche", "cras"}


def entrega(p: Passo) -> MensagemSaida:
    forma = p.msg.escolha
    if forma not in FORMAS:
        return MensagemSaida(
            p.txt("como_entregar"),
            botoes=(Botao("whatsapp", "Enviar por aqui"),
                    Botao("creche", "Levar na creche"),
                    Botao("cras", "Levar num CRAS")),
        )

    p.dados["forma_entrega"] = forma
    try:
        situacao = p.backend.inscrever(dict(p.dados), p.dados["preferencias"], forma)
        documentos = p.backend.documentos_exigidos(p.dados["preferencias"][0])
        pontos = p.backend.pontos_de_entrega(forma, p.dados["preferencias"][0],
                                             p.dados.get("local", ""))
    except BackendIndisponivel:
        return MensagemSaida(p.txt("backend_fora"))

    p.repo.salvar_inscricao(Inscricao(
        protocolo=situacao.protocolo, contato_id=p.contato_id,
        id_escola=situacao.id_escola, nome_escola=situacao.nome_escola,
        nome_crianca=p.dados.get("nome_candidato", "o candidato"),
        etapa_codigo=situacao.etapa.codigo,
    ))
    p.dados["protocolo"] = situacao.protocolo

    lista = "\n".join(f"📄 {d}" for d in documentos)
    rodape = (f"Seu número de protocolo é {situacao.protocolo}\n"
              f"Vou te avisar por aqui a cada atualização ✅")

    if forma == "whatsapp":
        p.ir("RECEBER_DOCUMENTOS")
        return MensagemSaida(
            f"{p.txt('mandar_aqui')}\n\nVocê vai precisar destes:\n{lista}\n\n{rodape}")

    p.ir("ACOMPANHAMENTO")

    if forma == "creche":
        ponto = pontos[0]
        return MensagemSaida(
            f"Sem problemas! Aqui está o que você precisa levar:\n\n{lista}\n\n"
            f"📍 {ponto.nome}\n{ponto.endereco}\n🕐 {ponto.horario}\n\n{rodape}",
            local=(Local(ponto.lat, ponto.lng, ponto.nome, ponto.endereco)
                   if ponto.lat is not None else None),
        )

    # CRAS: enderecos de todos os pontos, e honestidade sobre o que ainda não sabemos.
    enderecos = "\n\n".join(f"📍 {c.nome}\n{c.endereco}\n🕐 {c.horario}" for c in pontos)
    return MensagemSaida(
        f"Combinado! Aqui está o que você precisa:\n\n{lista}\n\n"
        f"CRAS mais próximos:\n\n{enderecos}\n\n"
        f"⚠️ Depois que o CRAS receber, os documentos ainda seguem para a creche. "
        f"Esse trajeto pode levar alguns dias e eu te aviso assim que a creche "
        f"confirmar.\n\n{rodape}",
        local=(Local(pontos[0].lat, pontos[0].lng, pontos[0].nome, pontos[0].endereco)
               if pontos and pontos[0].lat is not None else None),
    )


def receber_documentos(p: Passo) -> MensagemSaida:
    """8a — a família manda os arquivos por aqui, um de cada vez."""
    if p.msg.escolha == "terminei":
        p.ir("ACOMPANHAMENTO")
        return MensagemSaida(
            f"Tudo recebido! ✅\n\nProtocolo {p.dados['protocolo']}. "
            f"Agora é com a gente — te aviso a cada novidade 💙")

    if p.msg.anexo is None:
        return MensagemSaida(
            "Pode mandar o próximo documento 📎",
            botoes=(Botao("terminei", "Terminei, é só isso"),))

    try:
        r = p.backend.enviar_documento(p.dados["protocolo"], p.msg.anexo.conteudo,
                                       p.msg.anexo.mime)
    except BackendIndisponivel:
        return MensagemSaida(p.txt("backend_fora"))

    if r.confianca == "baixa":
        # Documento ilegível não vira dado errado no cadastro.
        return MensagemSaida(p.txt("documento_ilegivel"))

    recebidos = p.dados.get("documentos_recebidos", 0) + 1
    p.dados["documentos_recebidos"] = recebidos
    return MensagemSaida(
        f"{p.txt('documento_recebido')} ({recebidos} já recebido"
        f"{'s' if recebidos > 1 else ''})\n\nPode mandar o próximo 📎",
        botoes=(Botao("terminei", "Terminei, é só isso"),))
