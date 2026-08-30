"""Os blocos 3, 4, 5 e 9 do roteiro como DADOS, não como código.

"Uma pergunta por mensagem" é literalmente uma lista de perguntas. Um handler por campo
seria 15 funções quase idênticas — a máquina caminha estas listas e produz a mesma coisa.

Produto edita este arquivo sem tocar em lógica nenhuma.

Note o que NÃO está aqui: grupamento, bairro, distância e pontuação. São derivados, e
perguntar à família o que o sistema já sabe é o desenho errado.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from creche_bot.canal.tipos import MAX_BOTOES

Tipo = Literal["texto", "cpf", "data", "telefone", "email", "numero", "botoes"]


@dataclass(frozen=True)
class Campo:
    chave: str
    pergunta: str
    tipo: Tipo = "texto"
    opcoes: tuple[tuple[str, str], ...] = ()      # (id, rótulo) — máx. 3, limite WhatsApp
    eco: bool = False                             # "Recebido: Fulano ✅"
    erro: str = "Não entendi 🤔 Pode mandar de novo?"
    escape: tuple[str, str] | None = None         # (id, rótulo) de fuga em campo aberto
    digitos: tuple[int, int] = (1, 40)            # faixa de tamanho para tipo "numero"
    pular_se: Callable[[dict[str, Any]], bool] | None = field(default=None, compare=False)
    pergunta_alt: Callable[[dict[str, Any]], str] | None = field(default=None, compare=False)

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
def digitos_de(v: str) -> str:
    return re.sub(r"\D", "", v or "")


def cpf_valido(bruto: str) -> bool:
    """Dígito verificador. Sem isso, erro de digitação vira busca vazia no histórico e a
    família ouve "não achei seu cadastro" quando o cadastro existe."""
    d = digitos_de(bruto)
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for corte in (9, 10):
        soma = sum(int(d[i]) * (corte + 1 - i) for i in range(corte))
        if (soma * 10) % 11 % 10 != int(d[corte]):
            return False
    return True


def validar(campo: Campo, bruto: str) -> tuple[bool, Any]:
    """(ok, valor_normalizado). Validação de fronteira: nada entra torto no cadastro."""
    texto = (bruto or "").strip()

    if campo.tipo == "cpf":
        return (cpf_valido(texto), digitos_de(texto))

    if campo.tipo == "data":
        m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", texto)
        if not m:
            return False, None
        try:
            valor = date(int(m[3]), int(m[2]), int(m[1]))
        except ValueError:
            return False, None
        return (date(1900, 1, 1) <= valor <= date.today(), valor.isoformat())

    if campo.tipo == "telefone":
        d = digitos_de(texto)
        return (10 <= len(d) <= 11, d)

    if campo.tipo == "numero":
        d = digitos_de(texto)
        return (campo.digitos[0] <= len(d) <= campo.digitos[1], d)

    if campo.tipo == "email":
        return (bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", texto)), texto.lower())

    # Nome exige duas palavras: nome abreviado é a primeira causa de não achar a
    # inscrição depois, na consulta. Por isso o roteiro pede "sem abreviar".
    if campo.chave.startswith(("nome", "filiacao", "busca_nome", "busca_filiacao", "irmao")):
        return (len(texto.split()) >= 2 and len(texto) >= 5, " ".join(texto.split()))

    return (len(texto) >= 3, texto)


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


# ---------------------------------------------- blocos 3, 4 e 5 — o cadastro
CADASTRO: tuple[Campo, ...] = (
    # ---- Bloco 3: o responsável, que é a âncora da conta
    Campo("nome_responsavel", "Qual é o seu nome completo? (sem abreviar)", eco=True,
          erro="Preciso do nome completo, com sobrenome 🙂"),
    # Responde sozinha o critério de desempate "responsável menor de 18 anos". Os
    # critérios "60 anos ou mais" e "mãe adolescente" existiram só de 2021 a 2023 e não
    # existem mais na régua — não derive esses.
    Campo("nascimento_responsavel", "E qual a sua data de nascimento? (dia/mês/ano)",
          "data", eco=True, erro="Não peguei a data 🤔 Escreve assim: 07/11/1990"),
    Campo("relacao", "Qual a sua relação com a criança?", "botoes",
          (("mae", "Mãe"), ("pai", "Pai"), ("outra", "Outra"))),
    # 5 opções não cabem em 3 botões: a 3ª abre a segunda pergunta.
    Campo("relacao_outra", "Qual delas?", "botoes",
          (("avo", "Avó ou avô"), ("responsavel_legal", "Responsável legal"),
           ("outro", "Outro")),
          pular_se=lambda d: d.get("relacao") != "outra"),

    # ---- Bloco 4: a criança
    Campo("nome_crianca", "Agora a criança. Qual o nome completo dela? (sem abreviar)",
          eco=True, erro="Preciso do nome completo, com sobrenome 🙂"),
    Campo("nascimento_crianca", "E a data de nascimento? (dia/mês/ano)", "data", eco=True,
          erro="Não peguei a data 🤔 Escreve assim: 10/01/2024"),
    Campo("sexo", "A criança é menino ou menina?", "botoes",
          (("menino", "Menino"), ("menina", "Menina"))),
    # O portal trata isso nas duas telas de consulta: é a chave alternativa de busca, e
    # existe justamente para criança sem filiação registrada.
    Campo("filiacao_consta",
          "A filiação (nome da mãe e/ou pai) consta na certidão de nascimento dela?",
          "botoes", (("consta", "Consta"), ("nao_consta", "Não consta"))),
    Campo("filiacao",
          "Pode me passar o nome completo da mãe e/ou do pai, como está na certidão?",
          eco=True,
          pergunta_alt=lambda d: ("Pode me passar o nome do responsável legal pela "
                                  "criança?") if d.get("filiacao_consta") == "nao_consta"
          else None),

    # ---- Bloco 5: chave natural da criança, precedência CPF > DNV > NIS
    Campo("documento_crianca", "Você tem o CPF da criança?", "botoes",
          (("cpf", "Tenho o CPF"), ("dnv", "Tenho a DNV"),
           ("nenhum", "Não tenho os dois"))),
    Campo("cpf_crianca", "Pode mandar? (só os números)", "cpf", eco=True,
          pular_se=lambda d: d.get("documento_crianca") != "cpf",
          erro="Esse CPF não confere 🤔 Pode conferir os números?"),
    Campo("dnv", "Manda o número da Declaração de Nascido Vivo — é aquele papel da "
                 "maternidade.", "numero", eco=True, digitos=(9, 13),
          pular_se=lambda d: d.get("documento_crianca") != "dnv",
          erro="Não peguei o número 🤔 Manda só os dígitos."),
    # Sem nenhuma das três a inscrição SEGUE — só fica marcada para conferência.
    Campo("nis_crianca",
          "Sem problema. Você sabe o NIS da criança? Se não souber, seguimos assim mesmo "
          "e a equipe confere depois.", "numero", eco=True, digitos=(11, 11),
          escape=("nao_sei", "Não sei o NIS"),
          pular_se=lambda d: d.get("documento_crianca") != "nenhum",
          erro="O NIS tem 11 dígitos 🤔 Se não estiver achando, toca em 'Não sei o NIS'."),
)


# ----------------------------------------------------------- bloco 9 — contato
CONTATO: tuple[Campo, ...] = (
    Campo("numero_de_contato",
          "Esse número que você está usando serve para eu te avisar sobre a vaga?",
          "botoes", (("este", "Pode ser esse"), ("outro", "Prefiro outro"))),
    Campo("telefone", "Qual número? (com DDD)", "telefone", eco=True,
          pular_se=lambda d: d.get("numero_de_contato") != "outro",
          erro="Esse telefone não parece completo 🤔 Manda com DDD."),
    Campo("tem_outro_contato",
          "Tem outro contato de alguém da família, caso eu não consiga falar com você?",
          "botoes", (("sim", "Tenho outro"), ("nao", "Não tenho"))),
    Campo("outro_contato", "Qual o número? (com DDD)", "telefone", eco=True,
          pular_se=lambda d: d.get("tem_outro_contato") != "sim",
          erro="Esse telefone não parece completo 🤔 Manda com DDD."),
    Campo("quer_email", "Quer me passar um e-mail também? É opcional.", "botoes",
          (("sim", "Passar e-mail"), ("nao", "Pular"))),
    Campo("email", "Pode mandar o e-mail?", "email", eco=True,
          pular_se=lambda d: d.get("quer_email") != "sim",
          erro="Esse e-mail parece incompleto 🤔 Manda de novo?"),
)


# ------------------------------------- bloco C.1 — achar inscrição pelo nome
CONSULTA: tuple[Campo, ...] = (
    Campo("busca_nome", "Sem problema, dá pra achar assim também. Qual o nome completo "
                        "da criança? (sem abreviar)",
          erro="Preciso do nome completo, com sobrenome 🙂"),
    Campo("busca_nascimento", "E a data de nascimento dela?", "data",
          erro="Não peguei a data 🤔 Escreve assim: 10/01/2024"),
    Campo("busca_filiacao_consta",
          "A filiação (nome da mãe e/ou pai) consta na certidão de nascimento?", "botoes",
          (("consta", "Consta"), ("nao_consta", "Não consta"))),
    Campo("busca_filiacao",
          "Pode me passar o nome completo da mãe ou do pai, como está na certidão?",
          pergunta_alt=lambda d: "Pode me passar o nome do responsável legal?"
          if d.get("busca_filiacao_consta") == "nao_consta" else None),
)

LISTAS: dict[str, tuple[Campo, ...]] = {
    "CADASTRO": CADASTRO, "CONTATO": CONTATO, "CONSULTA": CONSULTA,
}


def proximo_campo(dados: dict[str, Any], campos: tuple[Campo, ...]) -> Campo | None:
    """Primeiro campo ainda não preenchido e não pulado. `None` = lista completa."""
    for campo in campos:
        if campo.chave in dados:
            continue
        if campo.pular_se is not None and campo.pular_se(dados):
            continue
        return campo
    return None


def campo_de(chave: str) -> Campo | None:
    for lista in LISTAS.values():
        for campo in lista:
            if campo.chave == chave:
                return campo
    return None
