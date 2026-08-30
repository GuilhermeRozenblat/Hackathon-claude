"""Bloco 5 — resumo e correção. É a última chance de pegar erro de digitação."""

from __future__ import annotations

from creche_bot.canal.tipos import Botao, ItemLista, MensagemSaida
from creche_bot.conversa.formulario import (
    FORMULARIO,
    Campo,
    formatar,
    proximo_campo,
    validar,
)
from creche_bot.conversa.sessao import Passo

# Ordem e rótulo do que aparece no resumo. Chave -> como a família chama aquilo.
LINHAS: tuple[tuple[str, str], ...] = (
    ("nome_candidato", "Candidato"),
    ("cpf", "CPF"),
    ("data_nascimento", "Nascimento"),
    ("origem_escolar", "Origem escolar"),
    ("matricula", "Matrícula"),
    ("tem_necessidade", "Atendimento especializado"),
    ("tipo_necessidade", "Tipo"),
    ("filiacao", "Filiação"),
    ("nome_responsavel", "Responsável"),
    ("telefone", "Telefone"),
    ("email", "E-mail"),
)

LEGIVEL = {
    "rede_municipal": "rede municipal", "particular": "escola particular",
    "nunca_estudou": "nunca estudou", "outra_rede": "outra rede/cidade",
    "sim": "sim", "nao": "não", "nao_informar": "não informado",
    "deficiencia_fisica": "deficiência física",
    "deficiencia_intelectual": "deficiência intelectual",
    "tgd_tea": "TGD/TEA", "altas_habilidades": "altas habilidades", "outra": "outra",
}


def _valor(dados: dict, chave: str) -> str | None:
    bruto = dados.get(chave)
    if bruto in (None, "", "ja_respondi"):
        return None
    campo = next((c for c in FORMULARIO if c.chave == chave), None)
    if campo is not None:
        return LEGIVEL.get(str(bruto), formatar(campo, bruto))
    if chave == "cpf":
        return formatar(Campo("cpf", "", "cpf"), bruto)
    if chave == "data_nascimento":
        return formatar(Campo("d", "", "data"), bruto)
    return LEGIVEL.get(str(bruto), str(bruto))


def montar(dados: dict) -> str:
    return "\n".join(f"• {rotulo}: {v}" for chave, rotulo in LINHAS
                     if (v := _valor(dados, chave)) is not None)


def resumo(p: Passo) -> MensagemSaida:
    p.ir("RESUMO")
    return MensagemSaida(
        p.txt("confirmar_resumo", resumo=montar(p.dados)),
        botoes=(Botao("ok", "Está tudo certo"), Botao("corrigir", "Quero corrigir")),
    )


def confirmacao(p: Passo) -> MensagemSaida:
    if p.msg.escolha == "corrigir":
        p.ir("CORRECAO")
        # Lista, não botões: são até 11 campos e o WhatsApp aceita 10 itens de lista.
        itens = tuple(ItemLista(chave, rotulo, _valor(p.dados, chave))
                      for chave, rotulo in LINHAS
                      if _valor(p.dados, chave) is not None)[:10]
        return MensagemSaida(p.txt("qual_corrigir"), lista=itens)

    if p.msg.escolha == "ok":
        p.ir("LOCALIZACAO")
        return MensagemSaida(p.txt("pedir_local"))

    return resumo(p)


def correcao(p: Passo) -> MensagemSaida:
    """Apaga o campo escolhido e volta ao formulário, que reencontra a lacuna sozinho."""
    escolhido = p.msg.escolha
    campo = next((c for c in FORMULARIO if c.chave == escolhido), None)

    if escolhido in ("cpf", "data_nascimento"):
        p.dados.pop("cpf", None)
        p.dados.pop("data_nascimento", None)
        p.ir("BUSCA_CPF")
        return MensagemSaida(p.txt("pedir_cpf"))

    if campo is None:
        return resumo(p)

    p.dados.pop(escolhido, None)
    p.dados.pop("perguntou", None)
    from creche_bot.conversa.passos.formulario_passo import perguntar_proximo

    return perguntar_proximo(p)


__all__ = ["Campo", "confirmacao", "correcao", "montar", "proximo_campo", "resumo",
           "validar"]
