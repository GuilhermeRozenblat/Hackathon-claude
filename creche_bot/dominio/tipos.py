"""CONTRATO CONGELADO — v2, roteiro do processo 195/2025.

Tipos de domínio que cruzam fronteira de módulo. Sem dependência de banco, de canal
ou de IA: é só vocabulário compartilhado.

## Os três padrões que este arquivo carrega

**Vocabulário aberto, comportamento fechado.** O backend externo define QUAIS etapas
existem ("aguardando_analise", ...); esse vocabulário é dele e muda por município, por
isso `Etapa.codigo` é `str`. Nós definimos O QUE FAZER com cada uma, e isso é pequeno e
estável, por isso `TipoEtapa` é `Literal`. Etapa nova que caia num tipo conhecido
funciona sem código novo.

**Régua do processo é DADO, não código.** Pesos, ordem e texto dos critérios de
prioridade mudam todo ano — entre 2023 e 2024 só 3 das 13 perguntas sobreviveram e o teto
caiu de 465 para 100 pontos. Por isso `Criterio` é uma lista que o backend devolve, nunca
um enum aqui dentro.

**Duas visões da inscrição, de propósito.** `Situacao`/`Etapa` é o que MUDA e dispara
notificação. `Desfecho` é o que a família VÊ quando consulta: um estado só, calculado
como a melhor situação entre as opções dela. O banco grava uma situação por opção de
creche, e mostrar isso cru quebra a confiança na hora — 77,8% das linhas
"Cancelado pelo sistema" pertencem a inscrições que foram ATENDIDAS.

**O que não existe aqui: pontuação e posição na fila.** A classificação roda depois do
fechamento das inscrições, é norma (Resolução SME nº 542/2025) e sai de SQL
determinístico. O bot não calcula, não estima e não mostra.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

# ------------------------------------------------------------------ a criança

# Vocabulário INTERNO da rede. A família nunca vê "Berçário" nem "Maternal I" — vê o
# rótulo de `GRUPAMENTO_LEGIVEL`.
Grupamento = Literal["bercario", "maternal_1", "maternal_2", "fora_da_faixa"]

GRUPAMENTO_LEGIVEL: dict[Grupamento, str] = {
    "bercario": "turma de bebês",
    "maternal_1": "turma de 2 anos",
    "maternal_2": "turma de 3 anos",
    "fora_da_faixa": "fora da faixa da creche",
}

# Bandas medidas na base de 2025, na data de corte do processo. Maternal I e II deram
# 0,0% fora da faixa em 91 mil linhas. Creche vai até 3 anos e 11 meses; daí para cima
# é pré-escola, e o bot precisa dizer isso cedo.
BANDAS_EM_MESES: tuple[tuple[int, Grupamento], ...] = (
    (24, "bercario"),
    (36, "maternal_1"),
    (48, "maternal_2"),
)


def meses_entre(nascimento: date, corte: date) -> int:
    meses = (corte.year - nascimento.year) * 12 + corte.month - nascimento.month
    return meses - (corte.day < nascimento.day)


def grupamento_de(nascimento: date, corte: date) -> Grupamento:
    """Deriva o grupamento. NUNCA pergunte isso à família — ela não fala essa língua."""
    meses = meses_entre(nascimento, corte)
    for teto, grupamento in BANDAS_EM_MESES:
        if meses < teto:
            return grupamento
    return "fora_da_faixa"


Horario = Literal["integral", "parcial"]
Sexo = Literal["menino", "menina"]

# 93,8% do Berçário é integral, mas 6,2% é parcial, e no Maternal II a parcial chega a
# 12,5%. O campo particiona a oferta de verdade: sem ele a sugestão não filtra.
HORARIO_LEGIVEL: dict[Horario, str] = {
    "integral": "tempo integral",
    "parcial": "meio período",
}

Relacao = Literal["mae", "pai", "avo", "responsavel_legal", "outro"]

# Chave natural da criança na SME, EM ORDEM DE PRECEDÊNCIA. Pelo menos uma é necessária
# para reconciliar a criança entre processos; sem nenhuma a inscrição segue, mas fica
# marcada para conferência.
DocumentoCrianca = Literal["cpf", "dnv", "nis", "nenhum"]


# ------------------------------------------------------------------- endereço


@dataclass(frozen=True)
class Endereco:
    """Derivado do CEP + número pelo servidor. NUNCA de bairro ou rua digitados.

    Na base histórica o campo livre gerou 1.608 grafias para ~925 bairros — "Inhaúma"
    sozinho tem 13 variantes. O CEP é 100% preenchido e 100% válido desde 2024. Sem o
    número, a precisão cai para ~1,4 km, o suficiente para errar a creche certa dentro
    do raio de 2 km que as famílias aceitam.
    """
    cep: str
    numero: str
    logradouro: str
    bairro: str
    lat: float
    lng: float

    def __str__(self) -> str:
        return f"{self.logradouro}, {self.numero} — {self.bairro}"


# ------------------------------------------------------------- oferta e vaga


@dataclass(frozen=True)
class Concorrencia:
    """Famílias por vaga no processo do ANO PASSADO. Passado, e rotulado como tal.

    Não é nota de corte e não é previsão: a classificação do processo vigente só roda
    depois do fechamento das inscrições, então no momento da conversa ela não existe.
    O teto da régua foi 465 pontos em 2023 e 100 em 2024 — histórico de pontuação não é
    comparável entre anos, mas quantas famílias disputaram cada vaga é fato verificável.
    """
    familias_por_vaga: float
    ano: int


@dataclass(frozen=True)
class VagaSugerida:
    """Uma creche sugerida. Só carrega o que é fato verificável hoje."""
    id_escola: str
    nome: str
    endereco: str
    lat: float
    lng: float
    grupamento: Grupamento
    horario: Horario
    distancia_km: float
    vaga_ociosa: bool                       # tem vaga aberta AGORA
    concorrencia: Concorrencia | None = None   # None = sem histórico comparável
    referencia: str = ""                    # "RIO 2", "PARK SHOPPING" — o apelido do lugar
    polo: str = ""                          # unidade real de classificação; não é microárea
    horario_atendimento: str = ""

    @property
    def minutos_a_pe(self) -> int:
        """~5 km/h. Distância em minutos diz mais à família do que em metros."""
        return max(1, round(self.distancia_km / 5 * 60))


# ------------------------------------------- régua de prioridade do processo


# Como a resposta é coletada. É a FORMA da pergunta, que é estável; o conteúdo vem da
# tabela do processo vigente.
FormaCriterio = Literal["sim_nao", "multipla", "numero", "anexo"]


@dataclass(frozen=True)
class Criterio:
    """Uma pergunta da régua do processo vigente.

    Vem de `ic.pergunta_processo` + `ic.pergunta_catalogo`, ordenada por `ordem`, sem as
    marcadas como autopreenchível. Régua escrita à mão no código quebra na virada do ano.
    """
    codigo: str
    rotulo: str                     # como aparece para a família, já em português de gente
    pontos: int
    grupo: str                      # "8.1", "8.3", "8.4" — o turno em que ela é feita
    sensivel: bool = False          # LGPD art. 11: consentimento próprio, e nunca ecoar
    documento: str | None = None    # o que comprova; None = nada a comprovar
    documento_opcional: bool = False   # violência, substâncias, prisão: nunca exigir


# ------------------------------------------------------ o que a família consulta


EstadoInscricao = Literal[
    "vaga_confirmada",    # 67,7% em 2025
    "lista_de_espera",    # 11,2%
    "nao_seguiu",         # 9,5% — estado ambíguo no banco: não invente o motivo
    "perdeu_prazo",       # 7,7% — a maior parte nunca soube que foi chamada
    "cancelada",          # 3,8%
    "selecionada",        # 0,2% — precisa confirmar, e isso é o PRIMEIRO balão
    "ativa",              # 0,0%
]

# Precedência para calcular o desfecho a partir das situações por opção. A primeira que
# aparecer na lista de opções da família é o que ela vê.
PRECEDENCIA: tuple[EstadoInscricao, ...] = (
    "vaga_confirmada", "ativa", "selecionada", "lista_de_espera",
    "perdeu_prazo", "cancelada", "nao_seguiu",
)


def desfecho_entre(estados: "list[EstadoInscricao]") -> EstadoInscricao:
    """A melhor situação entre as opções. É o ÚNICO estado que pode ser mostrado.

    O banco grava um status por opção de creche, e o cancelamento automático das outras
    opções quando uma é preenchida faz uma família ATENDIDA ver "cancelado" em 4 das 5
    escolhas dela.
    """
    for estado in PRECEDENCIA:
        if estado in estados:
            return estado
    return "nao_seguiu"


@dataclass(frozen=True)
class Desfecho:
    """O que a família vê ao consultar. Um estado, nunca a situação bruta por opção."""
    numero: str
    nome_crianca: str
    data_nascimento: date
    estado: EstadoInscricao
    escolas: tuple[str, ...] = ()             # nomes, na ordem de preferência
    escola_atendida: str | None = None
    endereco_escola: str | None = None
    lat: float | None = None
    lng: float | None = None
    prazo_confirmacao: date | None = None
    data_resultado: date | None = None
    inicio_das_aulas: date | None = None
    # Códigos de `Criterio` declarados e ainda não comprovados. É o que é acionável —
    # e o único número que aparece na consulta.
    pendencias: tuple[str, ...] = ()


@dataclass(frozen=True)
class CriancaConhecida:
    nome: str
    data_nascimento: date


@dataclass(frozen=True)
class CadastroAnterior:
    """O que o histórico devolve para o CPF do RESPONSÁVEL — a âncora da conta.

    27,9% das crianças de 2025 já constavam em 2024. Além de poupar o preenchimento,
    isso auto-preenche e já valida o critério "esperou na fila no ano anterior": hoje
    14,5% declaram e só 12,1% comprovam.
    """
    cpf: str
    nome_responsavel: str | None = None
    data_nascimento: date | None = None
    telefone: str | None = None
    email: str | None = None
    endereco: Endereco | None = None
    criancas: tuple[CriancaConhecida, ...] = ()
    esperou_na_fila: bool = False


# --------------------------------------------------------------- entrega e doc


FormaEntrega = Literal["whatsapp", "creche", "cras"]


@dataclass(frozen=True)
class PontoEntrega:
    nome: str
    endereco: str
    horario: str
    lat: float | None = None
    lng: float | None = None


TipoDocumento = Literal[
    "certidao_nascimento", "laudo_medico", "comprovante_nis",
    "protocolo_refugio", "boletim_ocorrencia", "desconhecido",
]


@dataclass(frozen=True)
class DadosExtraidos:
    """O que a leitura de um documento devolve.

    Campo não encontrado é None — NUNCA um chute. `confianca == "baixa"` faz o passo
    pedir de novo em vez de gravar dado errado no cadastro.
    """
    tipo_documento: TipoDocumento = "desconhecido"
    confianca: Literal["alta", "media", "baixa"] = "baixa"
    nis: str | None = None
    nome: str | None = None
    data_nascimento: date | None = None
    observacao: str | None = None      # "foto tremida", "documento cortado"


Intencao = Literal["responder", "corrigir", "duvida", "desistir", "fora_de_contexto"]


@dataclass(frozen=True)
class Classificacao:
    """Para mensagem fora do roteiro: o passo decide sem perder o lugar na fila."""
    intencao: Intencao = "responder"
    campo_alvo: str | None = None


# ------------------------------------------ o que muda e dispara notificação


TipoEtapa = Literal[
    "aguardando",       # nada a fazer. O bot TRANQUILIZA e NÃO cobra.
    "acao_no_chat",     # falta o usuário mandar algo por aqui. O bot pede.
    "acao_presencial",  # precisa ir até a unidade. O bot dá endereço, prazo e pino.
    "convocacao",       # saiu vaga e há prazo para confirmar. O bot chama, e insiste.
    "concluida",        # deu certo. O bot comemora.
    "encerrada",        # não deu, ou desistiu. O bot acolhe.
]


@dataclass(frozen=True)
class Pendencia:
    """Algo que falta. Nunca bloqueia a inscrição: vira lembrete, não parede."""
    codigo: str                             # o `Criterio.codigo` correspondente
    titulo: str                             # "Laudo da educação especial"
    entrega: Literal["chat", "presencial"]
    prazo: date | None = None


@dataclass(frozen=True)
class Etapa:
    codigo: str          # vocabulário do backend. ABERTO.
    titulo: str          # legível, já em português de gente
    tipo: TipoEtapa      # nossa taxonomia. FECHADA. É o que o bot usa para decidir.
    pendencias: tuple[Pendencia, ...] = ()
    prazo: date | None = None
    endereco_entrega: str | None = None   # obrigatório quando tipo == "acao_presencial"
    lat: float | None = None
    lng: float | None = None

    def __post_init__(self) -> None:
        if self.tipo == "acao_presencial":
            assert self.endereco_entrega, (
                f"etapa {self.codigo!r} é presencial e não tem endereço — "
                "o usuário não saberia para onde ir"
            )
        if self.tipo == "convocacao":
            assert self.prazo, (
                f"etapa {self.codigo!r} é convocação e não tem prazo — o prazo vencendo "
                "em silêncio é o que faz 7,7% perder a vaga já convocada"
            )


@dataclass(frozen=True)
class Situacao:
    """O que o backend devolve quando algo muda. Fonte das notificações R1 a R4."""
    numero: str
    nome_crianca: str
    nome_escola: str
    etapa: Etapa
    atualizado_em: datetime = field(default_factory=datetime.now)
