"""CONTRATO CONGELADO — Fase 0.1.

Tipos de domínio que cruzam fronteira de módulo. Sem dependência de banco, de canal
ou de IA: é só vocabulário compartilhado.

## O padrão central deste arquivo: vocabulário aberto, comportamento fechado

O backend externo define QUAIS etapas existem ("aguardando_analise",
"entregar_docs_na_unidade", ...). Esse vocabulário é dele, muda sem nos avisar, e varia
por município. Por isso `Etapa.codigo` é **str aberta**, nunca enum.

Nós definimos O QUE FAZER com cada etapa. Isso é nosso, é pequeno e é estável — por isso
`TipoEtapa` é **fechado**. A tradução `codigo -> tipo` vive numa única tabela, no
adaptador (`backend/http.py`), com default seguro.

Efeito: etapa nova no backend que caia num tipo conhecido funciona **sem mudar código**.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, NewType

# O nome da turma vem do município (Berçário I, Maternal II, ...). Não é enum de
# propósito: cada prefeitura nomeia do seu jeito, e enum quebraria na primeira.
Turma = NewType("Turma", str)

Faixa = Literal["alta", "media", "baixa", "sem_vaga"]

TipoEtapa = Literal[
    "aguardando",       # nada a fazer. O bot TRANQUILIZA e NÃO cobra.
    "acao_no_chat",     # falta o usuário mandar algo por aqui. O bot pede.
    "acao_presencial",  # o usuário precisa ir até a unidade. O bot dá endereço, prazo e pino.
    "concluida",        # deu certo. O bot comemora.
    "encerrada",        # não deu, ou desistiu. O bot acolhe e oferece as outras opções.
]


@dataclass(frozen=True)
class Escola:
    id_escola: str
    nome: str
    regiao: str
    bairro: str
    cep: str
    endereco: str
    lat: float
    lng: float


@dataclass(frozen=True)
class NotaCorte:
    """Pontuação do último candidato admitido — REFERÊNCIA HISTÓRICA, não previsão.

    O sistema não seleciona quem entra: quem aloca é o município. E a nota de corte
    sozinha não diz a chance da família, porque ela não conhece a própria pontuação.
    Por isso `ano` é campo obrigatório: a UI é obrigada a dizer de quando é o número.

    Não existe "probabilidade de conseguir a vaga" em lugar nenhum deste código.
    """
    pontos: float
    ano: int
    indisponivel: bool = False   # escola nova ou sem histórico


@dataclass(frozen=True)
class VagaSugerida:
    id_escola: str
    nome: str
    bairro: str
    endereco: str
    lat: float
    lng: float
    turma: Turma
    vagas_disponiveis: int
    nota_corte: NotaCorte
    faixa: Faixa            # derivada da nota DENTRO desta lista, nunca absoluta
    distancia_km: float
    horario_atendimento: str = ""


FormaEntrega = Literal["whatsapp", "creche", "cras"]

OrigemEscolar = Literal["rede_municipal", "particular", "nunca_estudou", "outra_rede"]

TipoNecessidade = Literal[
    "deficiencia_fisica", "deficiencia_intelectual", "tgd_tea",
    "altas_habilidades", "outra",
]


@dataclass(frozen=True)
class CadastroExistente:
    """O que o data lake devolve quando já conhece o candidato.

    Campo ausente é None — o resumo mostra "não informado" e deixa a família preencher.
    """
    cpf: str
    nome_candidato: str | None = None
    data_nascimento: date | None = None
    origem_escolar: OrigemEscolar | None = None
    matricula: str | None = None
    tem_necessidade: bool | None = None
    tipo_necessidade: TipoNecessidade | None = None
    nome_mae: str | None = None
    nome_pai: str | None = None
    nome_responsavel: str | None = None
    telefone: str | None = None
    email: str | None = None


@dataclass(frozen=True)
class PontoEntrega:
    """Onde a família leva os documentos: a creche escolhida ou um CRAS."""
    nome: str
    endereco: str
    horario: str
    lat: float | None = None
    lng: float | None = None


TipoDocumento = Literal[
    "rg", "cpf", "certidao_nascimento",
    "comprovante_residencia", "comprovante_renda", "desconhecido",
]

Intencao = Literal["responder", "corrigir", "duvida", "desistir", "fora_de_contexto"]


@dataclass(frozen=True)
class DadosExtraidos:
    """O que a leitura de um documento devolve.

    Campo não encontrado é None — NUNCA um chute. E `confianca == "baixa"` faz o passo
    pedir de novo em vez de gravar dado errado no cadastro.
    """
    tipo_documento: TipoDocumento = "desconhecido"
    confianca: Literal["alta", "media", "baixa"] = "baixa"
    nome_candidato: str | None = None
    data_nascimento: date | None = None
    cpf: str | None = None
    nome_responsavel: str | None = None
    cep: str | None = None
    observacao: str | None = None      # "foto tremida", "documento cortado"


@dataclass(frozen=True)
class Classificacao:
    """Para mensagem fora do roteiro: o passo decide sem perder o lugar na fila."""
    intencao: Intencao = "responder"
    campo_alvo: str | None = None


@dataclass(frozen=True)
class Pendencia:
    """Algo que falta. `entrega` decide se o bot pede foto ou manda o usuário à unidade."""
    codigo: str                             # "comprovante_residencia"
    titulo: str                             # "Comprovante de residência"
    entrega: Literal["chat", "presencial"]
    prazo: date | None = None


@dataclass(frozen=True)
class Etapa:
    codigo: str          # vocabulário do backend. ABERTO.
    titulo: str          # legível, já em português de gente
    tipo: TipoEtapa      # nossa taxonomia. FECHADA. É o que o bot usa para decidir.
    ordem: int           # 1-based
    total: int           # "passo 3 de 5" — é o que tira a ansiedade de quem espera
    pendencias: tuple[Pendencia, ...] = ()
    prazo: date | None = None
    endereco_entrega: str | None = None   # obrigatório quando tipo == "acao_presencial"
    lat: float | None = None
    lng: float | None = None

    def __post_init__(self) -> None:
        assert 1 <= self.ordem <= self.total, f"etapa {self.ordem}/{self.total} inconsistente"
        if self.tipo == "acao_presencial":
            assert self.endereco_entrega, (
                f"etapa {self.codigo!r} é presencial e não tem endereço — "
                "o usuário não saberia para onde ir"
            )


@dataclass(frozen=True)
class Situacao:
    """Onde a pessoa está na inscrição. É o que o backend devolve e o bot narra."""
    protocolo: str
    id_escola: str
    nome_escola: str
    etapa: Etapa
    atualizado_em: datetime
