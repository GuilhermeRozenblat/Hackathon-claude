"""CONTRATO CONGELADO: Fase 0. Não altere sem PR próprio revisado por todas as trilhas.

O modelo canônico de mensagem. É o que torna o flip Telegram -> WhatsApp barato:
o núcleo fala este dialeto e nunca sabe em qual plataforma está.

Os limites aqui são os do WhatsApp, que é a plataforma mais restrita. O Telegram é um
superconjunto e aceita tudo. Um fluxo que estoura o limite quebra no pytest hoje, e não
em produção depois do flip.
"""

from dataclasses import dataclass
from typing import Literal

Canal = Literal["telegram", "whatsapp"]

MAX_BOTOES = 3        # WhatsApp: interactive reply buttons
MAX_ITENS_LISTA = 10  # WhatsApp: interactive list rows
MAX_ROTULO = 20       # WhatsApp: título do botão, em caracteres
MAX_TEXTO = 1024      # WhatsApp: corpo de mensagem interativa


@dataclass(frozen=True)
class Anexo:
    conteudo: bytes
    mime: str
    nome: str | None = None


@dataclass(frozen=True)
class MensagemEntrada:
    canal: Canal
    id_externo: str      # chat_id (Telegram) ou wa_id (WhatsApp). NUNCA vira PK interna.
    id_mensagem: str     # idempotência: o WhatsApp reentrega webhook
    texto: str | None = None
    anexo: Anexo | None = None
    escolha: str | None = None   # Botao.id ou ItemLista.id que o usuário tocou


# Palavras que não distinguem uma creche de outra, e são as primeiras a cair na abreviação.
_RUIDO = ("creche", "emei", "cei", "escola", "municipal", "prof.ª", "profª", "prof.",
          "professora", "professor", "da", "de", "do", "das", "dos", "e")


def abreviar(nome: str, limite: int = MAX_ROTULO) -> str:
    """Encurta um nome preservando o que o distingue.

    "CEI Prof.ª Maria Aparecida da Silva" -> "Maria Aparecida"
    Tira o ruído primeiro; só corta letra se ainda não couber.
    """
    if len(nome) <= limite:
        return nome
    palavras = [p for p in nome.split() if p.lower().strip(".") not in _RUIDO]
    if not palavras:
        palavras = nome.split()
    curto = " ".join(palavras)
    while len(curto) > limite and len(palavras) > 1:
        palavras.pop()
        curto = " ".join(palavras)
    return curto if len(curto) <= limite else curto[: limite - 1] + "\u2026"


@dataclass(frozen=True)
class Botao:
    id: str
    rotulo: str


def botoes_nomeados(pares: "list[tuple[str, str]]") -> "tuple[Botao, ...]":
    """(id, nome_longo) -> botões que cabem no limite e continuam distinguíveis.

    Abreviar duas escolas para o mesmo texto é pior que truncar: o usuário escolhe errado
    e nem fica sabendo. Se colidir, numera.
    """
    curtos = [abreviar(nome) for _, nome in pares]
    if len(set(curtos)) < len(curtos):
        curtos = [f"{c[: MAX_ROTULO - 2]} {i + 1}" for i, c in enumerate(curtos)]
    return tuple(Botao(i, c) for (i, _), c in zip(pares, curtos, strict=True))


@dataclass(frozen=True)
class ItemLista:
    id: str
    titulo: str
    descricao: str | None = None


@dataclass(frozen=True)
class Local:
    """Pino nativo. Telegram: sendVenue. WhatsApp: message type `location`.

    AS DUAS PLATAFORMAS EXIGEM lat/lng, e endereço em texto não substitui.
    """
    lat: float
    lng: float
    nome: str
    endereco: str


@dataclass(frozen=True)
class MensagemSaida:
    texto: str                            # TEXTO PURO. Sem markdown: os dialetos divergem.
    botoes: tuple[Botao, ...] = ()
    lista: tuple[ItemLista, ...] = ()
    figurinha: str | None = None          # chave do catálogo, não caminho de arquivo
    local: Local | None = None            # o adapter envia como mensagem separada

    def __post_init__(self) -> None:
        assert self.texto.strip(), "mensagem sem texto"
        assert len(self.botoes) <= MAX_BOTOES, (
            f"{len(self.botoes)} botões; o WhatsApp aceita {MAX_BOTOES}. "
            "Divida o passo em dois. Veja ARQUITETURA.md §10.1."
        )
        assert len(self.lista) <= MAX_ITENS_LISTA, (
            f"{len(self.lista)} itens; o WhatsApp aceita {MAX_ITENS_LISTA}."
        )
        assert not (self.botoes and self.lista), "botões e lista são mutuamente exclusivos"
        for b in self.botoes:
            assert len(b.rotulo) <= MAX_ROTULO, (
                f"rótulo {b.rotulo!r} tem {len(b.rotulo)} chars; o máximo é {MAX_ROTULO}. "
                "Abrevie em canal/render.py."
            )
        ids = [x.id for x in (*self.botoes, *self.lista)]
        assert len(ids) == len(set(ids)), "ids de escolha duplicados"
