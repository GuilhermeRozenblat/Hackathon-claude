"""Caminha uma lista de `Campo`, uma pergunta por mensagem.

Duas funções e uma regra: `perguntar` sempre deixa `dados["perguntou"]` marcando qual
campo está no ar; `responder` só consome a resposta se houver pergunta no ar. Sem isso,
uma mensagem é engolida toda vez que outro passo entrega o controle aqui.

Lista terminada -> o controle vai para `seguir`, e o eco do último campo vai junto, no
mesmo balão. É o que evita um balão só com "Recebido: ✅" e nada mais.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from creche_bot.canal.tipos import Botao, MensagemSaida
from creche_bot.conversa.formulario import (
    LISTAS,
    Campo,
    campo_de,
    formatar,
    proximo_campo,
    validar,
)
from creche_bot.conversa.sessao import Passo

Seguir = Callable[[Passo], MensagemSaida]


def _texto(p: Passo, campo: Campo) -> str:
    return (campo.pergunta_alt and campo.pergunta_alt(p.dados)) or campo.pergunta


def _botoes(campo: Campo) -> tuple[Botao, ...]:
    """Opções fechadas viram botões; pergunta aberta pode ter um só, o de fuga."""
    if campo.opcoes:
        return tuple(Botao(i, r) for i, r in campo.opcoes)
    return (Botao(*campo.escape),) if campo.escape else ()


def perguntar(p: Passo, lista: str, seguir: Seguir, prefixo: str = "") -> MensagemSaida:
    """Faz a próxima pergunta pendente da lista. Lista completa -> entrega a `seguir`."""
    campo = proximo_campo(p.dados, LISTAS[lista])
    if campo is None:
        p.dados.pop("perguntou", None)
        return replace(prox := seguir(p), texto=prefixo + prox.texto)

    # Pergunta de saúde não passa sem o consentimento específico do art. 11. O gate é
    # pedido uma vez só, e vale para o resto da conversa — inclusive para o bloco 8.
    if campo.sensivel and p.dados.get("consentimento_sensivel") is None:
        from creche_bot.conversa.passos.criterios import pedir_gate

        p.dados["gate_volta"] = lista
        return pedir_gate(p, prefixo)

    p.dados["perguntou"] = campo.chave
    return MensagemSaida(prefixo + _texto(p, campo), botoes=_botoes(campo))


def responder(p: Passo, lista: str, seguir: Seguir) -> MensagemSaida:
    """Consome a resposta do campo no ar e anda. É o handler do estado."""
    campo = campo_de(p.dados.get("perguntou", ""))
    if campo is None:                       # ninguém perguntou nada ainda
        return perguntar(p, lista, seguir)

    if campo.opcoes:
        if p.msg.escolha not in {i for i, _ in campo.opcoes}:
            return MensagemSaida(_texto(p, campo), botoes=_botoes(campo))
        p.dados[campo.chave] = p.msg.escolha
    elif campo.escape and p.msg.escolha == campo.escape[0]:
        # "Não sei agora" vale como resposta: nada bloqueia a inscrição além do
        # consentimento e da faixa etária.
        p.dados[campo.chave] = campo.escape[0]
    else:
        ok, valor = validar(campo, p.texto)
        if not ok:
            return _errar(p, campo)
        p.dados[campo.chave] = valor

    p.dados.pop(f"erros_{campo.chave}", None)

    # Os dois pontos do formulário que podem interromper a lista.
    # Creche vai até 3 anos e 11 meses: falhe cedo e explique, em vez de deixar a família
    # descobrir no resultado.
    if campo.chave == "nascimento_crianca" and (fora := _fora_da_faixa(p)) is not None:
        return fora
    # E o CPF do responsável é a chave do histórico: 27,9% já têm cadastro.
    if campo.chave == "cpf_responsavel":
        from creche_bot.conversa.passos.responsavel import olhar_historico

        if (achou := olhar_historico(p)) is not None:
            return achou

    eco = (f"Recebido: {formatar(campo, p.dados[campo.chave])} ✅\n\n"
           if campo.eco and p.dados[campo.chave] != (campo.escape or ("",))[0] else "")
    return perguntar(p, lista, seguir, prefixo=eco)


def _fora_da_faixa(p: Passo) -> MensagemSaida | None:
    """Deriva o grupamento e barra quem já passou da creche. É o único bloqueio do
    fluxo além do consentimento."""
    from datetime import date

    from creche_bot.backend.porta import BackendIndisponivel
    from creche_bot.dominio.tipos import grupamento_de

    try:
        corte = p.backend.data_de_corte()
    except BackendIndisponivel:
        return p.diz("backend_fora")

    nascimento = date.fromisoformat(p.dados["nascimento_crianca"])
    p.dados["grupamento"] = grupamento_de(nascimento, corte)
    if p.dados["grupamento"] != "fora_da_faixa":
        return None

    anos, meses = divmod((corte.year - nascimento.year) * 12
                         + corte.month - nascimento.month, 12)
    p.ir("FORA_DA_FAIXA")
    return p.diz("fora_da_faixa",
                 nome=p.dados.get("nome_crianca", "a criança").split()[0],
                 idade=f"{anos} anos e {meses} meses", mes=f"{corte:%m/%Y}",
                 botoes=(Botao("pre_escola", "Como faço?"),
                         Botao("outra", "Outra criança")))


def _primeiro_nome(dados: dict) -> str:
    """No bloco 1 a data vem antes do nome: a mensagem tem que funcionar sem ele."""
    return (dados.get("nome_crianca") or "").split()[0] if dados.get("nome_crianca") \
        else "a criança"


def _errar(p: Passo, campo: Campo) -> MensagemSaida:
    """Três falhas no mesmo campo e o bot para de insistir: oferece atendente.

    Insistir uma quarta vez com alguém que já errou três é como o fluxo perde a família.
    """
    chave = f"erros_{campo.chave}"
    p.dados[chave] = p.dados.get(chave, 0) + 1
    if p.dados[chave] < 3:
        return MensagemSaida(campo.erro, botoes=_botoes(campo))
    return p.diz("atendente", botoes=(Botao("atendente", "Falar com a CRE"),
                                      Botao("tentar", "Tentar de novo")))
