"""Bloco 3, parte do responsável: o reconhecimento do cadastro anterior.

O roteiro pesquisa cadastro pelo CPF da criança. O backend não tem essa operação:
`backend/porta.py` só oferece `buscar_por_responsavel(cpf)`, e contrato congelado não
muda dentro de um PR de feature. Então a pesquisa acontece no CPF do responsável, que é
a âncora da conta e é o que reconhece reinscrição e irmãos.

O que a busca aproveita é o endereço e a espera do ano anterior. Nome e nascimento já
vieram nos blocos 1 e 3, e o telefone continua sendo perguntado: é por ele que a família
é convocada, e 7,7% perdem a vaga porque o contato falhou.
"""

from __future__ import annotations

from creche_bot.backend.porta import BackendIndisponivel
from creche_bot.canal.tipos import Botao, MensagemSaida
from creche_bot.conversa.sessao import Passo
from creche_bot.dominio.tipos import CadastroAnterior, Endereco

BOTOES_CADASTRO = (Botao("tudo_certo", "Tudo certo"),
                   Botao("mudei_endereco", "Mudei de endereço"))

# Campos que descrevem o responsável. Ficam quando a família inscreve uma segunda
# criança, e 1.738 responsáveis fizeram isso em 2025.
DO_RESPONSAVEL = ("cpf_responsavel", "nome_responsavel", "nascimento_responsavel",
                  "deficiencia_responsavel", "telefone", "email", "tem_outro_contato",
                  "outro_contato", "quer_email", "endereco", "esperou_na_fila",
                  "consentimento_sensivel")


def olhar_historico(p: Passo) -> MensagemSaida | None:
    """Chamado assim que o CPF do responsável entra no cadastro. Dispara em 27,9%.

    Histórico é bônus, não requisito: backend fora, ou CPF sem cadastro, e o formulário
    segue como se nada tivesse acontecido.
    """
    try:
        cadastro = p.backend.buscar_por_responsavel(p.dados["cpf_responsavel"])
    except BackendIndisponivel:
        return None

    if cadastro is None or not cadastro.criancas:
        return None
    return _mostrar_cadastro(p, cadastro)


def _mostrar_cadastro(p: Passo, cadastro: CadastroAnterior) -> MensagemSaida:
    p.dados["cadastro_anterior"] = {"endereco": _achatar(cadastro)}
    # Auto-preenche o critério "esperou na fila no ano anterior", e JÁ VALIDADO, porque
    # a fonte é o próprio banco. Hoje 14,5% declaram e só 12,1% conseguem comprovar.
    if cadastro.esperou_na_fila:
        p.dados["esperou_na_fila"] = True
        p.dados.setdefault("comprovados", []).append("fila_ano_anterior")

    return confere_cadastro(p)


def confere_cadastro(p: Passo) -> MensagemSaida:
    """Desenha a tela do cadastro anterior, a entrada do CADASTRO_ANTERIOR.

    Lê do contexto, não do backend: assim a retomada redesenha esta tela sem consultar
    o histórico de novo. Sem ela, continuar aqui respondia "não entendi" ao botão.
    """
    e = (p.dados.get("cadastro_anterior") or {}).get("endereco")
    p.ir("CADASTRO_ANTERIOR")
    return p.diz("achou_cadastro",
                 endereco=str(Endereco(**e)) if e else "endereço não informado",
                 botoes=BOTOES_CADASTRO)


def _achatar(cadastro: CadastroAnterior) -> dict | None:
    e = cadastro.endereco
    if e is None:
        return None
    return {"cep": e.cep, "numero": e.numero, "logradouro": e.logradouro,
            "bairro": e.bairro, "lat": e.lat, "lng": e.lng}


def cadastro_anterior(p: Passo) -> MensagemSaida:
    """Aproveita o que a família confirmou e devolve o controle ao formulário."""
    from creche_bot.conversa.maquina import entrar

    anterior = p.dados.pop("cadastro_anterior", {})
    escolha = p.msg.escolha

    if escolha not in ("tudo_certo", "mudei_endereco"):
        p.dados["cadastro_anterior"] = anterior
        return p.diz("nao_entendi", botoes=BOTOES_CADASTRO)

    if escolha == "mudei_endereco":
        anterior.pop("endereco", None)
    p.dados.update({c: v for c, v in anterior.items() if v is not None})

    p.ir("CADASTRO")
    return entrar(p, "CADASTRO")
