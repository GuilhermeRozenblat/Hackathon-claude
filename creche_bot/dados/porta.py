"""CONTRATO CONGELADO — Fase 0.2. A fronteira com a persistência.

Quem trabalha no canal, na conversa ou na notificação **nunca** conhece banco. Não há
`sqlite3`, `SELECT`, `session` nem `connection` fora das implementações desta porta.

Duas implementações hoje:
  · `memoria.RepositorioMemoria` — zero dependência, zero setup. É o que garante que o
    trabalho de Telegram nunca fica bloqueado por uma refatoração no banco.
  · `sqlite.RepositorioSQLite`  — o que roda por padrão; ponto de partida do Postgres.

Adicionar campo aqui = PR próprio. Todo mundo depende deste arquivo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class Inscricao:
    protocolo: str
    contato_id: str
    id_escola: str
    nome_escola: str
    nome_crianca: str
    etapa_codigo: str | None = None


@dataclass(frozen=True)
class RespostaCriterio:
    """Uma resposta da régua de prioridade, já reduzida a código + booleano.

    O texto que a família digitou NUNCA chega aqui: o que a inscrição precisa é qual
    critério foi declarado e qual está comprovado. `sensivel` marca as linhas de LGPD
    art. 11 (saúde, violência, substâncias, situação prisional) para que quem consultar
    o banco saiba que aquela coluna não é um booleano qualquer.
    """
    codigo: str
    declarado: bool
    comprovado: bool = False
    sensivel: bool = False


@dataclass(frozen=True)
class PreferenciaEscola:
    """Uma opção de creche, na POSIÇÃO em que a família a colocou. 1 é a primeira.

    Guarda junto o fato que estava na tela quando ela escolheu — distância, vaga aberta
    e concorrência do ano de `ano_referencia`. Sem isso não dá para auditar depois com
    base em que a escolha foi feita, e o painel muda de um processo para o outro.
    """
    posicao: int
    id_escola: str
    nome_escola: str
    distancia_km: float | None = None
    vaga_ociosa: bool = False
    familias_por_vaga: float | None = None
    ano_referencia: int | None = None


@dataclass(frozen=True)
class Cadastro:
    """O que a família respondeu, em colunas — a mesma coisa que o jsonb da sessão tem,
    numa forma que aguenta SQL.

    Datas viajam como ISO `str`, não `date`: é o formato que já atravessa
    `sessao.contexto`, e converter em dois lugares só criaria uma terceira grafia.

    `protocolo` é `None` até a inscrição ser efetivada. É o que distingue o cadastro
    ABERTO (um por contato, sobrescrito a cada resposta) dos já enviados — 1.738
    responsáveis inscreveram duas ou mais crianças em 2025, e cada uma vira sua linha.
    """
    contato_id: str
    protocolo: str | None = None
    nome_crianca: str | None = None
    nascimento_crianca: str | None = None
    sexo: str | None = None
    grupamento: str | None = None
    documento_crianca: str | None = None
    nome_responsavel: str | None = None
    cpf_responsavel: str | None = None
    relacao: str | None = None
    cep: str | None = None
    numero: str | None = None
    logradouro: str | None = None
    bairro: str | None = None
    lat: float | None = None
    lng: float | None = None
    horario: str | None = None
    telefone: str | None = None
    email: str | None = None
    criterios: tuple[RespostaCriterio, ...] = ()
    preferencias: tuple[PreferenciaEscola, ...] = ()


@dataclass(frozen=True)
class EventoInscricao:
    """Uma linha da história da inscrição, para a família ver o caminho e não só o agora.

    `tipo` é o `TipoEtapa` do domínio, gravado como texto: é por ele que a tela decide o
    tom, e o `codigo` do backend muda por município.
    """
    protocolo: str
    etapa_codigo: str
    tipo: str
    titulo: str
    quando: str = ""


@dataclass(frozen=True)
class EventoPendente:
    """Uma linha da outbox pronta para entregar. `id` é o que marca enviado/falha."""
    id: int
    protocolo: str
    contato_id: str
    chave: str
    variaveis: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Repositorio(Protocol):
    # ------------------------------------------------------------- identidade
    def contato_de(self, canal: str, id_externo: str) -> str:
        """UUID interno do contato, criando na primeira mensagem. Idempotente.

        `id_externo` NUNCA é chave primária: é isso que faz a mesma pessoa migrar do
        Telegram para o WhatsApp sem perder o cadastro.
        """

    def id_externo_de(self, contato_id: str, canal: str = "telegram") -> str | None: ...

    # ----------------------------------------------------------- consentimento
    def registrar_consentimento(
        self, contato_id: str, versao: str, canal: str, id_externo: str
    ) -> None: ...

    def tem_consentimento(self, contato_id: str) -> bool: ...

    # ------------------------------------------------------------------ sessão
    def carregar_sessao(self, contato_id: str) -> tuple[str, dict[str, Any]]:
        """(estado, contexto). Contato sem sessão devolve ("INICIO", {})."""

    def salvar_sessao(self, contato_id: str, estado: str, contexto: dict[str, Any]) -> None: ...

    # ---------------------------------------------------------------- cadastro
    def salvar_cadastro(self, cadastro: Cadastro) -> None:
        """Grava o cadastro ABERTO do contato (`protocolo is None`), sobrescrevendo.

        Chamado a cada turno da conversa, não só no fim: família que abandona no meio
        deixa rastro do que já respondeu, e é justamente esse abandono que interessa
        medir. Critérios e preferências vão na mesma transação — meia gravação faria a
        régua discordar da escolha de creche.
        """

    def cadastro_de(self, contato_id: str, protocolo: str | None = None) -> Cadastro | None:
        """O cadastro aberto do contato, ou o de um protocolo já enviado."""

    def fechar_cadastro(self, contato_id: str, protocolo: str) -> None:
        """Carimba o protocolo no cadastro aberto. Depois disso ele não é mais reescrito,
        e a próxima criança começa uma linha nova."""

    # --------------------------------------------------------------- inscrição
    def salvar_inscricao(self, inscricao: Inscricao) -> None: ...

    def inscricao(self, protocolo: str) -> Inscricao | None: ...

    def atualizar_etapa(self, protocolo: str, etapa_codigo: str) -> None: ...

    # ---------------------------------------------------- acompanhamento da vaga
    def registrar_evento(self, evento: EventoInscricao) -> None:
        """Acrescenta uma etapa à história da inscrição. Idempotente por
        (protocolo, etapa_codigo): o polling relê a mesma situação várias vezes."""

    def eventos(self, protocolo: str) -> list[EventoInscricao]:
        """A história em ordem cronológica. É o que o /status mostra como linha do tempo."""

    # ------------------------------------------------------------------ outbox
    def enfileirar(self, protocolo: str, chave: str, variaveis: dict[str, Any]) -> None: ...

    def pendentes(self, limite: int = 50) -> list[EventoPendente]:
        """Eventos não entregues que ainda não estouraram o teto de tentativas."""

    def marcar_enviado(self, evento_id: int) -> None: ...

    def marcar_falha(self, evento_id: int) -> None: ...

    # ------------------------------------------------------------ marca d'água
    def ler_marca(self, chave: str) -> str | None: ...

    def gravar_marca(self, chave: str, valor: str) -> None: ...

    # -------------------------------------------------------------------- LGPD
    def apagar_tudo(self, contato_id: str) -> int:
        """Direito de eliminação (LGPD art. 18). Não pode deixar órfão em lugar nenhum."""
