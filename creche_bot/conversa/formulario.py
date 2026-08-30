"""Os blocos 2, 3 e 4 do roteiro como DADOS, não como código.

"Uma pergunta por mensagem" é literalmente uma lista de perguntas. Um handler por campo
seria 12 funções quase idênticas — a máquina caminha esta lista e produz a mesma coisa.

Produto edita este arquivo sem tocar em lógica nenhuma.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from creche_bot.canal.tipos import MAX_BOTOES

Tipo = Literal["texto", "cpf", "data", "telefone", "email", "botoes"]


@dataclass(frozen=True)
class Campo:
    chave: str
    pergunta: str
    tipo: Tipo = "texto"
    opcoes: tuple[tuple[str, str], ...] = ()      # (id, rótulo) — máx. 3, limite WhatsApp
    eco: bool = False                             # "Recebido: Fulano ✅"
    erro: str = "Não entendi 🤔 Pode mandar de novo?"
    escape: tuple[str, str] | None = None         # (id, rótulo) de fuga em campo de texto
    pular_se: Callable[[dict[str, Any]], bool] | None = field(default=None, compare=False)
    pergunta_alt: Callable[[dict[str, Any]], str] | None = field(default=None, compare=False)
    aviso: str | None = None                      # texto que precede a pergunta

    def __post_init__(self) -> None:
        assert len(self.opcoes) <= MAX_BOTOES, (
            f"campo {self.chave!r} tem {len(self.opcoes)} opções; "
            f"o WhatsApp aceita {MAX_BOTOES} botões. Quebre em duas perguntas."
        )
        assert (self.tipo == "botoes") == bool(self.opcoes), (
            f"campo {self.chave!r}: tipo 'botoes' e opções têm que andar juntos"
        )
        assert not (self.escape and self.opcoes), (
            f"campo {self.chave!r}: escape é para pergunta aberta; com opções, "
            f"a saída é mais uma opção"
        )


# ----------------------------------------------------------------- validação
def _digitos(v: str) -> str:
    return re.sub(r"\D", "", v or "")


def validar(campo: Campo, bruto: str) -> tuple[bool, Any]:
    """(ok, valor_normalizado). Validação de fronteira: nada entra torto no cadastro."""
    texto = (bruto or "").strip()

    if campo.tipo == "cpf":
        d = _digitos(texto)
        return (len(d) == 11, d)

    if campo.tipo == "data":
        m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", texto)
        if not m:
            return False, None
        try:
            valor = date(int(m[3]), int(m[2]), int(m[1]))
        except ValueError:
            return False, None
        return (valor <= date.today(), valor.isoformat())

    if campo.tipo == "telefone":
        d = _digitos(texto)
        return (10 <= len(d) <= 11, d)

    if campo.tipo == "email":
        return (bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", texto)), texto.lower())

    return (len(texto) >= 3, texto)


# ------------------------------------------------------------- o formulário
# Bloco 2 — sobre a vaga
# Bloco 3 — dados pessoais
# Bloco 4 — contato
FORMULARIO: tuple[Campo, ...] = (
    Campo(
        "origem_escolar", "O candidato já estuda em alguma escola?", "botoes",
        (("rede_municipal", "Rede municipal"), ("particular", "Escola particular"),
         ("nunca_estudou", "Nunca estudou")),
    ),
    # 4ª opção não cabe nos 3 botões do WhatsApp — vira pergunta própria.
    Campo(
        "outra_rede", "É em outra rede ou em outra cidade?", "botoes",
        (("outra_rede", "Sim, outra rede"), ("nunca_estudou", "Não, nunca estudou")),
        pular_se=lambda d: d.get("origem_escolar") != "nunca_estudou",
    ),
    Campo(
        "matricula", "Você tem o número de matrícula dele ou dela em mãos?", "texto",
        escape=("nao_sei", "Não sei agora"),
        pular_se=lambda d: d.get("origem_escolar") != "rede_municipal",
        erro="Não peguei o número 🤔 Se não tiver em mãos, toca em 'Não sei agora'.",
    ),
    Campo(
        "tem_necessidade",
        "O candidato possui deficiência, TGD/TEA ou altas habilidades?", "botoes",
        (("sim", "Sim"), ("nao", "Não"), ("nao_informar", "Prefiro não dizer")),
        aviso="sensivel",          # dispara o consentimento específico da LGPD art. 11
    ),
    Campo(
        "tipo_necessidade", "Qual dessas descreve melhor a situação?", "botoes",
        (("deficiencia_fisica", "Deficiência física"),
         ("deficiencia_intelectual", "Def. intelectual"), ("tgd_tea", "TGD/TEA")),
        pular_se=lambda d: d.get("tem_necessidade") != "sim",
    ),
    Campo(
        "tipo_necessidade_2", "É alguma dessas?", "botoes",
        (("altas_habilidades", "Altas habilidades"), ("outra", "Outra"),
         ("ja_respondi", "Já respondi acima")),
        pular_se=lambda d: d.get("tipo_necessidade") in
        (None, "deficiencia_fisica", "deficiencia_intelectual", "tgd_tea"),
    ),
    Campo("nome_candidato", "Qual é o nome completo do candidato?", eco=True,
          erro="Preciso do nome completo 🙂"),
    Campo(
        "filiacao_na_certidao",
        "A filiação (nome da mãe e/ou pai) consta na certidão de nascimento?", "botoes",
        (("sim", "Sim"), ("nao", "Não")),
    ),
    Campo(
        "filiacao", "Pode me passar o nome completo da mãe e/ou do pai, "
                    "como consta na certidão?", eco=True,
        pergunta_alt=lambda d: ("Pode me passar o nome do responsável legal "
                                "pela criança?") if d.get("filiacao_na_certidao") == "nao"
        else None,
    ),
    Campo("nome_responsavel",
          "E qual é o nome do responsável que vai acompanhar essa matrícula?", eco=True),
    # A idade responde sozinha dois critérios legais de prioridade. Perguntar
    # "você tem 60 anos ou mais?" ou "você é menor de 18?" é constrangedor e
    # desnecessário: a data já diz. Ver `criterios_prioridade()`.
    Campo("data_nascimento_responsavel",
          "Qual é a data de nascimento do responsável? (dia/mês/ano)", "data", eco=True,
          erro="Não peguei a data 🤔 Escreve assim: 07/11/1990"),
    Campo(
        "deficiencia_responsavel",
        "O candidato tem pai, mãe ou responsável com alguma deficiência?", "botoes",
        (("sim", "Sim"), ("nao", "Não"), ("nao_informar", "Prefiro não dizer")),
        aviso="sensivel",
    ),
    Campo("telefone", "Show! Agora preciso do telefone do responsável, "
                      "para mantermos contato sobre a inscrição.", "telefone", eco=True,
          erro="Esse telefone não parece completo 🤔 Manda com DDD."),
    Campo(
        "tem_outro_contato",
        "Tem algum outro celular, de uma segunda pessoa, para o caso de eu não "
        "conseguir falar com você?", "botoes",
        (("sim", "Sim, tenho outro"), ("nao", "Não tenho outro")),
    ),
    Campo("outro_contato", "Pode me passar esse outro número, por favor?",
          "telefone", eco=True,
          pular_se=lambda d: d.get("tem_outro_contato") != "sim",
          erro="Esse telefone não parece completo 🤔 Manda com DDD."),
    Campo("tem_email", "O responsável tem e-mail?", "botoes",
          (("sim", "Sim"), ("nao", "Não"))),
    Campo("email", "Pode me passar o e-mail, por favor?", "email", eco=True,
          pular_se=lambda d: d.get("tem_email") != "sim",
          erro="Esse e-mail parece incompleto 🤔 Manda de novo?"),
)


def formatar(campo: Campo, valor: Any) -> str:
    """Como o valor volta para a pessoa. Guardamos normalizado, mostramos legível —
    o eco existe para ela conferir, e dígito cru é difícil de escanear."""
    v = str(valor)
    if campo.tipo == "cpf" and len(v) == 11:
        return f"{v[:3]}.{v[3:6]}.{v[6:9]}-{v[9:]}"
    if campo.tipo == "telefone" and len(v) in (10, 11):
        meio = 5 if len(v) == 11 else 4
        return f"({v[:2]}) {v[2:2 + meio]}-{v[2 + meio:]}"
    if campo.tipo == "data" and len(v) == 10:
        a, m, d = v.split("-")
        return f"{d}/{m}/{a}"
    return v


PRIORIDADES = {
    "responsavel_60_mais": "responsável com 60 anos ou mais",
    "responsavel_menor_18": "responsável com menos de 18 anos",
}


def _idade(nascimento: date, hoje: date | None = None) -> int:
    hoje = hoje or date.today()
    return hoje.year - nascimento.year - (
        (hoje.month, hoje.day) < (nascimento.month, nascimento.day))


def criterios_prioridade(dados: dict[str, Any]) -> tuple[str, ...]:
    """Critérios legais que saem da idade do responsável, sem perguntar nada a mais.

    MARCAR o critério não é DECIDIR a vaga: quem aloca é o município. Aqui só sai a
    etiqueta que vai junto da inscrição.
    """
    bruto = dados.get("data_nascimento_responsavel")
    if not bruto:
        return ()
    idade = _idade(date.fromisoformat(bruto))
    return tuple(chave for chave, corta in
                 (("responsavel_60_mais", idade >= 60),
                  ("responsavel_menor_18", idade < 18)) if corta)


def proximo_campo(dados: dict[str, Any]) -> Campo | None:
    """Primeiro campo ainda não preenchido e não pulado. `None` = formulário completo."""
    for campo in FORMULARIO:
        if campo.chave in dados:
            continue
        if campo.pular_se is not None and campo.pular_se(dados):
            continue
        return campo
    return None
