"""Chave de figurinha -> o que a plataforma entende.

# ponytail: emoji, não sticker. Sticker de verdade exige criar um pack no @Stickers e
# guardar o file_id de cada um — friccão que não paga nada durante a validação. Quando o
# pack existir, preencha FILE_IDS e o render passa a mandar sticker de verdade.
"""

EMOJI: dict[str, str] = {
    "ola": "👋",
    "vamos_la": "🚀",
    "pensando": "🤔",
    "comemorando": "🎉",
    "festa": "🥳",
    "atencao": "⚠️",
    "coracao": "💚",
    "abraco": "🫂",
    "foto": "📸",
    "mapa": "📍",
}

# Preencher quando houver pack próprio (@Stickers). Chave sem file_id cai no emoji.
FILE_IDS: dict[str, str] = {}


def emoji(chave: str | None) -> str:
    return EMOJI.get(chave or "", "")


def file_id(chave: str | None) -> str | None:
    return FILE_IDS.get(chave or "")
