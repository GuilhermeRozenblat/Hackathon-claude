"""Blocos 0, 0.1 e 1 — porta de entrada, retomada e consentimento.

Três portas na primeira tela, de propósito: inscrever, acompanhar e tirar dúvida. A do
meio serve inclusive para quem se inscreveu pelo site — é leitura pura, não toca no fluxo
de inscrição, e alcança as ~62 mil famílias que usaram o portal normalmente.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from creche_bot.backend.porta import BackendIndisponivel
from creche_bot.canal.tipos import Botao, MensagemSaida
from creche_bot.conversa.sessao import Passo
from creche_bot.ia.persona import CONSENTIMENTO, CONSENTIMENTO_VERSAO, TERMO

# Conversa de WhatsApp cai. Sessão viva por 72h; depois disso, recomeça limpa.
VALIDADE_SESSAO = timedelta(hours=72)

BOTOES_INICIO = (Botao("inscrever", "Quero inscrever"),
                 Botao("acompanhar", "Acompanhar inscrição"),
                 Botao("duvidas", "Tenho dúvidas"))

BOTOES_CONSENTIMENTO = (Botao("autorizo", "Autorizo"),
                        Botao("ler_termo", "Ler o termo"))

# Onde a conversa parou, em português de gente. É o que a retomada diz de volta.
ONDE_PAROU: dict[str, str] = {
    "CADASTRO": "nos seus dados",
    "ENDERECO_CEP": "no endereço",
    "ENDERECO_CONFIRMA": "no endereço",
    "HORARIO": "no horário da vaga",
    "CRIT_CADUNICO": "nas perguntas de prioridade",
    "CRIT_NIS": "no número do NIS",
    "CRIT_ESPECIAL": "nas perguntas de prioridade",
    "CRIT_FAMILIA": "nas perguntas de prioridade",
    "CRIT_IRMAO": "nas perguntas de prioridade",
    "CRIT_GATE": "nas perguntas de prioridade",
    "CRIT_SENSIVEL": "nas perguntas de prioridade",
    "CRIT_ANEXO": "nos documentos",
    "CONTATO": "no seu contato",
    "ESCOLAS": "na escolha das creches",
    "RESUMO": "no resumo",
    "PENDENCIAS": "nos documentos",
}


def sessao_expirada(dados: dict) -> bool:
    visto = dados.get("visto_em")
    if not visto:
        return False
    return datetime.fromisoformat(visto) < datetime.now() - VALIDADE_SESSAO


def inicio(p: Passo) -> MensagemSaida:
    p.ir("PORTA")
    return p.diz("saudacao", botoes=BOTOES_INICIO)


def retomada(p: Passo, estado_salvo: str) -> MensagemSaida:
    """Bloco 0.1 — não recomeça quem já estava no meio."""
    p.dados["retomar_para"] = estado_salvo
    p.ir("RETOMADA")
    return MensagemSaida(
        p.txt("retomar", onde=ONDE_PAROU.get(estado_salvo, "onde a gente parou")),
        botoes=(Botao("continuar", "Continuar"), Botao("recomecar", "Começar de novo")))


def porta(p: Passo) -> MensagemSaida:
    """A escolha do bloco 0."""
    if p.msg.escolha == "acompanhar":
        from creche_bot.conversa.passos.consulta import comecar

        return comecar(p)

    if p.msg.escolha == "duvidas":
        p.ir("PORTA")
        return MensagemSaida(p.txt("duvidas"), botoes=BOTOES_INICIO)

    if p.msg.escolha != "inscrever":
        return p.diz("nao_entendi", botoes=BOTOES_INICIO)

    # Fora do período, inscrever não é uma opção — e prometer que é seria mentira.
    try:
        abertura, fechamento = p.backend.periodo_de_inscricao()
    except BackendIndisponivel:
        return p.diz("backend_fora")

    if not abertura <= date.today() <= fechamento:
        p.ir("FORA_DO_PERIODO")
        return p.diz("fora_do_periodo", abertura=abertura.strftime("%d/%m"),
                     fechamento=fechamento.strftime("%d/%m/%Y"),
                     botoes=(Botao("avisar", "Quero ser avisada"),
                             Botao("acompanhar", "Acompanhar inscrição")))

    p.ir("CONSENTIMENTO")
    return MensagemSaida(CONSENTIMENTO, botoes=BOTOES_CONSENTIMENTO)


def fora_do_periodo(p: Passo) -> MensagemSaida:
    if p.msg.escolha == "acompanhar":
        from creche_bot.conversa.passos.consulta import comecar

        return comecar(p)
    p.repo.registrar_consentimento(p.contato_id, f"comunicacao/{CONSENTIMENTO_VERSAO}",
                                   p.msg.canal, p.msg.id_externo)
    p.ir("PORTA")
    return p.diz("aviso_ligado", botoes=BOTOES_INICIO)


def consentimento(p: Passo) -> MensagemSaida:
    """Bloco 1 — gate obrigatório.

    Algumas perguntas do bloco 8 tratam de saúde, violência e situação prisional. Sem
    base legal isso não pode nem ser gravado. O consentimento específico para dado
    sensível é pedido separado, no 8.4, e só para quem chega lá.
    """
    if p.msg.escolha == "ler_termo":
        return MensagemSaida(TERMO, botoes=BOTOES_CONSENTIMENTO)

    if p.msg.escolha != "autorizo":
        return MensagemSaida(p.txt("preciso_autorizacao"), botoes=BOTOES_CONSENTIMENTO)

    p.repo.registrar_consentimento(p.contato_id, f"inscricao/{CONSENTIMENTO_VERSAO}",
                                   p.msg.canal, p.msg.id_externo)
    from creche_bot.conversa.passos.responsavel import pedir_cpf

    return pedir_cpf(p)


def retomar(p: Passo) -> MensagemSaida:
    from creche_bot.conversa.maquina import PASSOS

    if p.msg.escolha == "continuar":
        estado = p.dados.pop("retomar_para", "PORTA")
        p.ir(estado)
        return PASSOS[estado](p)

    if p.msg.escolha == "recomecar":
        p.dados.clear()
        return inicio(p)

    return p.diz("nao_entendi",
                 botoes=(Botao("continuar", "Continuar"),
                         Botao("recomecar", "Começar de novo")))
