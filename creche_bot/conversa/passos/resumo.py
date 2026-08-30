"""Bloco 5 — o resumo dos dados, antes de partir para a escolha das creches.

Mostra o que a família declarou nos blocos 1 a 4, para conferir ou corrigir.

Duas coisas que NÃO aparecem aqui:

· Pontuação e posição na fila. A classificação roda depois do fechamento das inscrições;
  prometer posição aqui é criar expectativa que a SME não pode honrar.
· Resposta sensível. O roteiro pede "necessidades especiais" no resumo, mas ecoar dado de
  saúde num histórico que fica no aparelho da família é exatamente o que a LGPD art. 11
  manda evitar. Fica guardado, não fica repetido.
"""

from __future__ import annotations

from creche_bot.canal.tipos import Botao, ItemLista, MensagemSaida
from creche_bot.conversa.formulario import campo_de, formatar
from creche_bot.conversa.passos.criterios import pendentes
from creche_bot.conversa.sessao import Passo
from creche_bot.dominio.tipos import GRUPAMENTO_LEGIVEL

BOTOES_RESUMO = (Botao("certo", "Está tudo certo"), Botao("corrigir", "Quero corrigir"))

ORIGEM_LEGIVEL = {"rede_municipal": "já estuda na rede municipal",
                  "nunca": "nunca estudou",
                  "particular": "estuda em escola particular",
                  "outra_rede": "estuda em outra rede ou cidade"}

# Correção volta ao BLOCO dono do campo, não a um campo solto: é assim que o roteiro
# descreve, e é o que evita deixar a conversa num estado meio preenchido.
AREAS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("crianca", "Dados da criança", "CADASTRO",
     ("cpf_crianca", "nome_crianca", "nascimento_crianca", "grupamento",
      "filiacao_consta", "filiacao", "origem", "origem_outra", "matricula",
      "tem_especial", "tipo_especial", "tipo_especial_outro")),
    ("responsavel", "Meus dados", "CADASTRO",
     ("nome_responsavel", "cpf_responsavel", "nascimento_responsavel",
      "deficiencia_responsavel")),
    ("contato", "Meu contato", "CONTATO",
     ("telefone", "tem_outro_contato", "outro_contato", "quer_email", "email")),
)


def _rotulo(dados: dict, codigo: str) -> str:
    for c in dados.get("criterios", ()):
        if c["codigo"] == codigo:
            return c["rotulo"]
    return codigo.replace("_", " ")


def _fone(numero: str) -> str:
    return formatar(campo_de("telefone"), numero)


def montar(dados: dict) -> str:
    linhas = []

    nome = dados.get("nome_crianca", "a criança")
    turma = GRUPAMENTO_LEGIVEL.get(dados.get("grupamento", ""), "creche")
    linhas.append(f"👶 {nome} — {turma}")
    if (cpf := dados.get("cpf_crianca")) and cpf != "nao_tenho":
        linhas.append(f"🪪 CPF {formatar(campo_de('cpf_crianca'), cpf)}")
    if (origem := ORIGEM_LEGIVEL.get(dados.get("origem_outra") or dados.get("origem", ""))):
        linhas.append(f"🏫 {origem}")
    if (filiacao := dados.get("filiacao")):
        linhas.append(f"👪 Filiação: {filiacao}")

    if (responsavel := dados.get("nome_responsavel")):
        linhas.append(f"🙋 Responsável: {responsavel}")
    if (telefone := dados.get("telefone")):
        linhas.append(f"📞 {_fone(telefone)}")
    if (outro := dados.get("outro_contato")):
        linhas.append(f"📞 Outro contato: {_fone(outro)}")
    if (email := dados.get("email")):
        linhas.append(f"✉️ {email}")

    if (comprovados := dados.get("comprovados", ())):
        linhas.append("")
        linhas.append("✅ Já comprovado: "
                      + ", ".join(_rotulo(dados, c) for c in comprovados))
    if (falta := pendentes(dados)):
        linhas.append("⏳ Falta comprovar: "
                      + ", ".join(_rotulo(dados, c) for c in falta))
    return "\n".join(linhas)


def resumo(p: Passo) -> MensagemSaida:
    p.ir("RESUMO")
    return MensagemSaida(p.txt("resumo", resumo=montar(p.dados)), botoes=BOTOES_RESUMO)


def confirmacao(p: Passo) -> MensagemSaida:
    """Confirmado, o roteiro entra no bloco 6 — endereço e escolas."""
    from creche_bot.conversa.passos.endereco import pedir_cep
    from creche_bot.conversa.passos.escolas import pedir_horario

    if p.msg.escolha == "corrigir":
        p.ir("CORRECAO")
        return MensagemSaida(
            p.txt("qual_corrigir"),
            lista=tuple(ItemLista(codigo, rotulo) for codigo, rotulo, _, _ in AREAS))

    if p.msg.escolha == "certo":
        # Endereço vindo do cadastro anterior já foi confirmado no bloco 3.
        return pedir_horario(p) if p.dados.get("endereco") else pedir_cep(p)

    return resumo(p)


def correcao(p: Passo) -> MensagemSaida:
    """Apaga a área escolhida e devolve o controle ao bloco dono dela."""
    from creche_bot.conversa.maquina import entrar

    area = next((a for a in AREAS if a[0] == p.msg.escolha), None)
    if area is None:
        return resumo(p)

    _, _, estado, chaves = area
    for chave in chaves:
        p.dados.pop(chave, None)
    p.dados.pop("perguntou", None)
    p.ir(estado)
    return entrar(p, estado)
