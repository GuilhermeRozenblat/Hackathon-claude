"""Blocos 2 e 2a — identificação do responsável e reconhecimento do cadastro anterior.

Começa pelo adulto, não pela criança. O CPF do responsável é mais confiável, é a âncora
da conta, e é o que reconhece reinscrição e irmãos. Exigir CPF de criança de 0 a 3 anos
no primeiro turno derruba família na porta.
"""

from __future__ import annotations

from creche_bot.backend.porta import BackendIndisponivel
from creche_bot.canal.tipos import Botao, MensagemSaida
from creche_bot.conversa.formulario import cpf_valido, digitos_de
from creche_bot.conversa.sessao import Passo
from creche_bot.dominio.tipos import CadastroAnterior

BOTOES_CADASTRO = (Botao("tudo_certo", "Tudo certo"),
                   Botao("mudei_endereco", "Mudei de endereço"),
                   Botao("outra_crianca", "É outra criança"))

# Campos que descrevem o responsável. Ficam quando a família inscreve uma segunda
# criança — 1.738 responsáveis fizeram isso em 2025.
DO_RESPONSAVEL = ("cpf_responsavel", "nome_responsavel", "nascimento_responsavel",
                  "relacao", "relacao_outra", "telefone", "email",
                  "numero_de_contato", "tem_outro_contato", "outro_contato",
                  "quer_email", "endereco", "esperou_na_fila")


def pedir_cpf(p: Passo) -> MensagemSaida:
    p.ir("CPF_RESPONSAVEL")
    return MensagemSaida(p.txt("pedir_cpf"))


def cpf_responsavel(p: Passo) -> MensagemSaida:
    if not cpf_valido(p.texto):
        tentativas = p.dados.get("erros_cpf", 0) + 1
        p.dados["erros_cpf"] = tentativas
        if tentativas >= 3:
            return p.diz("atendente",
                         botoes=(Botao("atendente", "Falar com a CRE"),
                                 Botao("tentar", "Tentar de novo")))
        return p.diz("cpf_invalido")

    p.dados.pop("erros_cpf", None)
    p.dados["cpf_responsavel"] = digitos_de(p.texto)

    try:
        cadastro = p.backend.buscar_por_responsavel(p.dados["cpf_responsavel"])
    except BackendIndisponivel:
        return p.diz("backend_fora")

    if cadastro is None or not cadastro.criancas:
        return _preencher_do_zero(p)
    return _mostrar_cadastro(p, cadastro)


def _preencher_do_zero(p: Passo) -> MensagemSaida:
    from creche_bot.conversa.passos.endereco import pedir_cep
    from creche_bot.conversa.passos.formulario_passo import perguntar

    p.ir("CADASTRO")
    return perguntar(p, "CADASTRO", pedir_cep, prefixo=f"{p.txt('nao_achou')}\n\n")


def _mostrar_cadastro(p: Passo, cadastro: CadastroAnterior) -> MensagemSaida:
    """Bloco 2a. Dispara em 27,9% dos casos."""
    crianca = cadastro.criancas[0]
    p.dados["cadastro_anterior"] = {
        "nome_responsavel": cadastro.nome_responsavel,
        "nascimento_responsavel": (cadastro.data_nascimento.isoformat()
                                   if cadastro.data_nascimento else None),
        "telefone": cadastro.telefone,
        "nome_crianca": crianca.nome,
        "nascimento_crianca": crianca.data_nascimento.isoformat(),
        "endereco": _achatar(cadastro),
    }
    # Auto-preenche o critério "esperou na fila no ano anterior", e JÁ VALIDADO, porque
    # a fonte é o próprio banco. Hoje 14,5% declaram e só 12,1% conseguem comprovar.
    if cadastro.esperou_na_fila:
        p.dados["esperou_na_fila"] = True
        p.dados.setdefault("comprovados", []).append("fila_ano_anterior")

    p.ir("CADASTRO_ANTERIOR")
    endereco = cadastro.endereco
    return p.diz("achou_cadastro", nome=crianca.nome,
                 nascimento=crianca.data_nascimento.strftime("%d/%m/%Y"),
                 endereco=str(endereco) if endereco else "endereço não informado",
                 botoes=BOTOES_CADASTRO)


def _achatar(cadastro: CadastroAnterior) -> dict | None:
    e = cadastro.endereco
    if e is None:
        return None
    return {"cep": e.cep, "numero": e.numero, "logradouro": e.logradouro,
            "bairro": e.bairro, "lat": e.lat, "lng": e.lng}


def cadastro_anterior(p: Passo) -> MensagemSaida:
    from creche_bot.conversa.passos.endereco import pedir_cep
    from creche_bot.conversa.passos.escolas import pedir_horario
    from creche_bot.conversa.passos.formulario_passo import perguntar

    anterior = p.dados.get("cadastro_anterior", {})
    escolha = p.msg.escolha

    if escolha == "tudo_certo":
        p.dados.update({c: v for c, v in anterior.items() if v is not None})
        return pedir_horario(p)

    if escolha == "mudei_endereco":
        p.dados.update({c: v for c, v in anterior.items()
                        if v is not None and c != "endereco"})
        return pedir_cep(p)

    if escolha == "outra_crianca":
        # Reaproveita responsável e endereço; só a criança recomeça.
        p.dados.update({c: v for c, v in anterior.items()
                        if v is not None and c in DO_RESPONSAVEL})
        p.ir("CADASTRO")
        return perguntar(p, "CADASTRO", pedir_cep)

    return p.diz("nao_entendi", botoes=BOTOES_CADASTRO)
