"""Blocos 12 e 13 — comprovação do que ficou pendente, e o protocolo.

O WhatsApp não é uma opção entre três: é o caminho recomendado. Hoje a comprovação
acontece depois, presencialmente, e valida 8,0% dos casos. Capturar a evidência dentro da
conversa é o produto — as outras duas portas existem para quem não consegue.

A lista de documentos é CONDICIONAL ao que a família declarou. Lista genérica faz a
família levar o papel errado e voltar para casa sem resolver.
"""

from __future__ import annotations

from creche_bot.backend.porta import BackendIndisponivel
from creche_bot.canal.tipos import Botao, Local, MensagemSaida
from creche_bot.conversa.passos.criterios import pendentes
from creche_bot.conversa.sessao import Passo
from creche_bot.dados.porta import Inscricao

BOTOES_ENTREGA = (Botao("whatsapp", "Mandar foto aqui"),
                  Botao("creche", "Levar na creche"),
                  Botao("cras", "Levar num CRAS"))

BOTOES_OUTRA = (Botao("outra_crianca", "Sim, outra criança"),
                Botao("terminei", "Não, terminei"))


def _documentos(dados: dict) -> list[str]:
    """O que comprova cada critério que ficou pendente. Só isso, nada genérico."""
    falta = set(pendentes(dados))
    return [c["documento"] for c in dados.get("criterios", ())
            if c["codigo"] in falta and c["documento"]]


def enviar(p: Passo) -> MensagemSaida:
    """Efetiva a inscrição no matricula.rio e segue para pendências ou protocolo."""
    p.dados.setdefault("chave_idempotencia",
                       f"{p.contato_id}:{p.dados.get('nome_crianca', '')}")
    try:
        numero = p.backend.inscrever(dict(p.dados), list(p.dados["preferencias"]))
    except BackendIndisponivel:
        return MensagemSaida(p.txt("backend_fora"))

    p.dados["numero"] = numero
    nomes = {x["id"]: x["nome"] for x in p.dados.get("escolas", ())}
    primeira = p.dados["preferencias"][0]
    p.repo.salvar_inscricao(Inscricao(
        protocolo=numero, contato_id=p.contato_id, id_escola=primeira,
        nome_escola=nomes.get(primeira, ""),
        nome_crianca=p.dados.get("nome_crianca", "a criança"),
        etapa_codigo="recebida"))

    if _documentos(p.dados):
        p.ir("PENDENCIAS")
        return MensagemSaida(
            p.txt("falta_documento", documentos=_lista(p.dados)), botoes=BOTOES_ENTREGA)
    return protocolo(p)


def _lista(dados: dict) -> str:
    return "\n".join(f"📄 {d}" for d in _documentos(dados))


def como_entregar(p: Passo) -> MensagemSaida:
    forma = p.msg.escolha
    if forma not in ("whatsapp", "creche", "cras"):
        return MensagemSaida(p.txt("falta_documento", documentos=_lista(p.dados)),
                             botoes=BOTOES_ENTREGA)

    p.dados["forma_entrega"] = forma
    if forma == "whatsapp":
        p.ir("RECEBER_DOC")
        return MensagemSaida(p.txt("mandar_foto_aqui"),
                             botoes=(Botao("depois", "Mando depois"),))

    try:
        pontos = p.backend.pontos_de_entrega(
            forma, p.dados["preferencias"][0], p.dados["endereco"]["cep"])
    except BackendIndisponivel:
        return MensagemSaida(p.txt("backend_fora"))

    lugares = "\n\n".join(f"📍 {x.nome}\n{x.endereco}\n🕐 {x.horario}" for x in pontos)
    aviso = f"\n\n{p.txt('aviso_cras')}" if forma == "cras" else ""
    ponto = pontos[0]
    resposta = MensagemSaida(
        f"Combinado. Leve:\n\n{_lista(p.dados)}\n\n{lugares}{aviso}",
        local=(Local(ponto.lat, ponto.lng, ponto.nome, ponto.endereco)
               if ponto.lat is not None else None))
    seguinte = protocolo(p)
    return MensagemSaida(f"{resposta.texto}\n\n{seguinte.texto}",
                         botoes=seguinte.botoes, local=resposta.local)


def receber_documento(p: Passo) -> MensagemSaida:
    """12a — a foto chega aqui mesmo, que é o caminho que valida de verdade."""
    if p.msg.escolha == "depois":
        return protocolo(p, prefixo=f"{p.txt('documento_depois')}\n\n")

    if p.msg.anexo is None:
        return MensagemSaida(p.txt("pedir_foto"),
                             botoes=(Botao("depois", "Mando depois"),))

    falta = pendentes(p.dados)
    try:
        lido = p.backend.enviar_documento(p.dados["numero"], falta[0],
                                          p.msg.anexo.conteudo, p.msg.anexo.mime)
    except BackendIndisponivel:
        return MensagemSaida(p.txt("backend_fora"))

    if lido.confianca == "baixa":
        return MensagemSaida(p.txt("documento_ilegivel"),
                             botoes=(Botao("depois", "Mando depois"),))

    p.dados.setdefault("comprovados", []).append(falta[0])
    if pendentes(p.dados):
        return MensagemSaida(f"{p.txt('documento_recebido')}\n\n"
                             f"{p.txt('falta_documento', documentos=_lista(p.dados))}",
                             botoes=(Botao("depois", "Mando depois"),))
    return protocolo(p, prefixo=f"{p.txt('documento_conferido')}\n\n")


def protocolo(p: Passo, prefixo: str = "") -> MensagemSaida:
    """Bloco 13."""
    p.ir("PROTOCOLO")
    return MensagemSaida(
        prefixo + p.txt("protocolo", numero=p.dados["numero"],
                        resultado=p.backend.data_do_resultado().strftime("%d/%m/%Y")),
        botoes=BOTOES_OUTRA)


def depois_do_protocolo(p: Passo) -> MensagemSaida:
    """1.738 responsáveis inscreveram 2 ou mais crianças em 2025. Reaproveita tudo do
    responsável — só a criança e a pergunta do irmão recomeçam."""
    from creche_bot.conversa.passos.endereco import pedir_cep
    from creche_bot.conversa.passos.formulario_passo import perguntar
    from creche_bot.conversa.passos.responsavel import DO_RESPONSAVEL

    if p.msg.escolha == "outra_crianca":
        guardado = {c: v for c, v in p.dados.items() if c in DO_RESPONSAVEL}
        p.dados.clear()
        p.dados.update(guardado)
        p.ir("CADASTRO")
        return perguntar(p, "CADASTRO", pedir_cep, prefixo=f"{p.txt('outra_crianca')}\n\n")

    p.ir("ACOMPANHAR")
    return MensagemSaida(p.txt("terminei"))
