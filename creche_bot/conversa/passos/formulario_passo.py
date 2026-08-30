"""Blocos 2, 3 e 4 — caminha o formulário declarativo, uma pergunta por mensagem.

Duas funções e uma regra: `perguntar_proximo` sempre deixa `dados["perguntou"]` marcando
qual campo está no ar; `formulario` só consome a resposta se houver pergunta no ar. Sem
isso, uma mensagem é engolida toda vez que outro passo entrega o controle aqui.
"""

from __future__ import annotations

from creche_bot.canal.tipos import Botao, MensagemSaida
from creche_bot.conversa.formulario import Campo, formatar, proximo_campo, validar
from creche_bot.conversa.sessao import Passo
from creche_bot.ia.persona import CONSENTIMENTO_SENSIVEL


def _texto_da_pergunta(p: Passo, campo: Campo) -> str:
    texto = (campo.pergunta_alt and campo.pergunta_alt(p.dados)) or campo.pergunta

    # LGPD art. 11: dado de saúde exige consentimento específico e destacado. Vem
    # imediatamente antes da pergunta, e "prefiro não dizer" é sempre uma das opções.
    if campo.aviso == "sensivel" and not p.dados.get("avisou_sensivel"):
        p.dados["avisou_sensivel"] = True
        texto = f"{CONSENTIMENTO_SENSIVEL}\n\n{texto}"
    return texto


def perguntar_proximo(p: Passo, prefixo: str = "") -> MensagemSaida:
    """Faz a próxima pergunta pendente. Formulário completo -> vai para o resumo.

    Outros passos chamam isto para entregar o controle sem perder uma mensagem.
    """
    campo = proximo_campo(p.dados)
    if campo is None:
        p.dados.pop("perguntou", None)
        from creche_bot.conversa.passos.resumo import resumo

        pronto = resumo(p)
        return MensagemSaida(prefixo + pronto.texto, botoes=pronto.botoes)

    p.dados["perguntou"] = campo.chave
    p.ir("FORMULARIO")
    return MensagemSaida(prefixo + _texto_da_pergunta(p, campo), botoes=_botoes(campo))


def formulario(p: Passo) -> MensagemSaida:
    no_ar = p.dados.get("perguntou")
    campo = next((c for c in _todos() if c.chave == no_ar), None)

    if campo is None:                       # ninguém perguntou nada ainda
        return perguntar_proximo(p)

    if campo.opcoes:
        if p.msg.escolha not in {i for i, _ in campo.opcoes}:
            return MensagemSaida(_texto_da_pergunta(p, campo), botoes=_botoes(campo))
        p.dados[campo.chave] = p.msg.escolha
    elif campo.escape and p.msg.escolha == campo.escape[0]:
        # "Não sei agora": vale como resposta. A pessoa não fica presa numa pergunta
        # cuja resposta ela não tem em mãos.
        p.dados[campo.chave] = campo.escape[0]
    else:
        ok, valor = validar(campo, p.texto)
        if not ok:
            return MensagemSaida(campo.erro)
        p.dados[campo.chave] = valor

    eco = (f"Recebido: {formatar(campo, p.dados[campo.chave])} ✅\n\n"
           if campo.eco and p.dados[campo.chave] != (campo.escape or ("",))[0] else "")
    return perguntar_proximo(p, prefixo=eco)


def _botoes(campo: Campo) -> tuple[Botao, ...]:
    """Opções fechadas viram botões; pergunta aberta pode ter um só, o de fuga."""
    if campo.opcoes:
        return tuple(Botao(i, r) for i, r in campo.opcoes)
    return (Botao(*campo.escape),) if campo.escape else ()


def _todos() -> tuple[Campo, ...]:
    from creche_bot.conversa.formulario import FORMULARIO

    return FORMULARIO
