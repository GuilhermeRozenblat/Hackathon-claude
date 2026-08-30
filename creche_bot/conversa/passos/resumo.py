"""Bloco 11 — o resumo antes de enviar.

Mostra o que é acionável: o que já está comprovado e o que ainda falta comprovar.

NUNCA mostra pontuação nem posição na fila. A classificação roda depois do fechamento das
inscrições; prometer posição aqui é criar expectativa que a SME não pode honrar.
"""

from __future__ import annotations

from creche_bot.canal.tipos import Botao, ItemLista, MensagemSaida
from creche_bot.conversa.formulario import campo_de, formatar
from creche_bot.conversa.passos.criterios import pendentes
from creche_bot.conversa.sessao import Passo
from creche_bot.dominio.tipos import GRUPAMENTO_LEGIVEL, HORARIO_LEGIVEL

BOTOES_RESUMO = (Botao("enviar", "Enviar inscrição"), Botao("corrigir", "Quero corrigir"))

# Correção volta ao BLOCO dono do campo, não a um campo solto: é assim que o roteiro
# descreve, e é o que evita deixar a conversa num estado meio preenchido.
AREAS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("crianca", "Dados da criança", "CADASTRO",
     ("nome_crianca", "nascimento_crianca", "sexo", "filiacao_consta", "filiacao",
      "documento_crianca", "cpf_crianca", "dnv", "nis_crianca", "grupamento")),
    ("responsavel", "Meus dados", "CADASTRO",
     ("nome_responsavel", "nascimento_responsavel", "relacao", "relacao_outra")),
    ("endereco", "Endereço", "ENDERECO_CEP", ("endereco",)),
    ("horario", "Horário da vaga", "HORARIO", ("horario",)),
    ("criterios", "Perguntas de prioridade", "CRIT_CADUNICO",
     ("declarados", "comprovados", "nis", "nome_irmao", "criterios")),
    ("contato", "Meu contato", "CONTATO",
     ("numero_de_contato", "telefone", "tem_outro_contato", "outro_contato",
      "quer_email", "email")),
    ("escolas", "Creches escolhidas", "ESCOLAS", ("escolas", "preferencias")),
)


def _rotulo(dados: dict, codigo: str) -> str:
    for c in dados.get("criterios", ()):
        if c["codigo"] == codigo:
            return c["rotulo"]
    return codigo.replace("_", " ")


def montar(dados: dict) -> str:
    linhas = []

    nome = dados.get("nome_crianca", "a criança")
    turma = GRUPAMENTO_LEGIVEL.get(dados.get("grupamento", ""), "creche")
    horario = HORARIO_LEGIVEL.get(dados.get("horario", ""), "")
    linhas.append(f"👶 {nome} — {turma}, {horario}".rstrip(", "))

    if (e := dados.get("endereco")):
        linhas.append(f"📍 {e['logradouro']}, {e['numero']} — {e['bairro']}")

    if (prefs := dados.get("preferencias")):
        nomes = {x["id"]: x["nome"] for x in dados.get("escolas", ())}
        escolhidas = " · ".join(f"{i}. {nomes.get(x, x)}"
                                for i, x in enumerate(prefs, 1))
        linhas.append(f"🏫 {escolhidas}")

    if (telefone := dados.get("telefone")):
        linhas.append(f"📞 {formatar(campo_de('telefone'), telefone)}")
    if (email := dados.get("email")):
        linhas.append(f"✉️ {email}")

    comprovados = dados.get("comprovados", ())
    if comprovados:
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
    from creche_bot.conversa.passos.pendencias import enviar

    if p.msg.escolha == "corrigir":
        p.ir("CORRECAO")
        return MensagemSaida(
            p.txt("qual_corrigir"),
            lista=tuple(ItemLista(codigo, rotulo) for codigo, rotulo, _, _ in AREAS))

    if p.msg.escolha == "enviar":
        return enviar(p)

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
