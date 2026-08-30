"""Bloco 0 e 1 — boas-vindas, consentimento e consulta ao data lake."""

from __future__ import annotations

from datetime import date

from creche_bot.backend.porta import BackendIndisponivel
from creche_bot.canal.tipos import Botao, MensagemSaida
from creche_bot.conversa.formulario import Campo, validar
from creche_bot.conversa.sessao import Passo
from creche_bot.ia.persona import CONSENTIMENTO, CONSENTIMENTO_VERSAO

_CPF = Campo("cpf", "", "cpf")
_DATA = Campo("data_nascimento", "", "data")


def inicio(p: Passo) -> MensagemSaida:
    p.ir("CONSENTIMENTO")
    return MensagemSaida(
        f"{p.txt('saudacao')}\n\n{CONSENTIMENTO}",
        botoes=(Botao("aceito", "Vamos começar"), Botao("recuso", "Agora não")),
    )


def consentimento(p: Passo) -> MensagemSaida:
    if p.msg.escolha == "recuso":
        p.ir("INICIO")
        return MensagemSaida(p.txt("recusou"))

    if p.msg.escolha != "aceito":
        return MensagemSaida(
            "Preciso da sua autorização para continuar 🤝",
            botoes=(Botao("aceito", "Vamos começar"), Botao("recuso", "Agora não")),
        )

    p.repo.registrar_consentimento(p.contato_id, CONSENTIMENTO_VERSAO,
                                   p.msg.canal, p.msg.id_externo)
    p.ir("BUSCA_CPF")
    return MensagemSaida(p.txt("pedir_cpf"))


def busca_cpf(p: Passo) -> MensagemSaida:
    ok, cpf = validar(_CPF, p.texto)
    if not ok:
        return MensagemSaida(p.txt("cpf_invalido"))
    p.dados["cpf"] = cpf
    p.ir("BUSCA_NASCIMENTO")
    return MensagemSaida(p.txt("pedir_nascimento"))


def busca_nascimento(p: Passo) -> MensagemSaida:
    ok, nascimento = validar(_DATA, p.texto)
    if not ok:
        return MensagemSaida(p.txt("data_invalida"))
    p.dados["data_nascimento"] = nascimento

    try:
        cadastro = p.backend.buscar_candidato(p.dados["cpf"], date.fromisoformat(nascimento))
    except BackendIndisponivel:
        return MensagemSaida(p.txt("backend_fora"))

    if cadastro is None:
        from creche_bot.conversa.passos.formulario_passo import perguntar_proximo

        return perguntar_proximo(p, prefixo=f"{p.txt('nao_achou')}\n\n")

    # Cadastro encontrado: preenche o que veio e pula direto para o resumo (Bloco 5).
    # Campo ausente continua ausente — o resumo mostra "não informado".
    for chave, valor in vars(cadastro).items():
        if valor is not None and chave not in ("cpf", "data_nascimento"):
            p.dados[chave] = valor.isoformat() if isinstance(valor, date) else valor
    p.dados["veio_do_cadastro"] = True
    from creche_bot.conversa.passos.resumo import resumo

    pronto = resumo(p)
    return MensagemSaida(f"{p.txt('achou_cadastro')}\n\n{pronto.texto}",
                         botoes=pronto.botoes)
