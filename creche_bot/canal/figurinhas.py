"""Chave de figurinha -> o que a plataforma entende.

Quem escolhe a chave é a conversa (`ia/persona.py`, mapa `FIGURINHAS`); aqui só mora a
tradução para o que o Telegram sabe mandar hoje.

**Nada que insinue sorte ou promessa de vaga**: 🤞, 🍀, 🏆, 🎰. O sistema cadastra e
informa; comemorar antes da classificação é prometer o que a SME não pode honrar. Há
teste que cobra isso.

# ponytail: emoji, não sticker. Sticker de verdade exige criar um pack no @Stickers e
# guardar o file_id de cada um, fricção que não paga nada durante a validação. Quando o
# pack existir, preencha FILE_IDS e o render passa a mandar sticker de verdade.
"""

EMOJI: dict[str, str] = {
    "ola": "👋",
    "vamos_la": "🚀",
    "pensando": "🤔",
    "comemorando": "🎉",
    "festa": "🥳",
    "joia": "👍",
    "atencao": "⚠️",
    "espera": "⏳",
    "coracao": "💚",
    "abraco": "🫂",
    "ops": "😅",
    "foto": "📸",
    "escola": "🏫",
    "telefone": "📞",
    "mapa": "📍",
}

# Preencher quando houver pack próprio (@Stickers). Chave sem file_id cai no emoji.
FILE_IDS: dict[str, str] = {}


def emoji(chave: str | None) -> str:
    return EMOJI.get(chave or "", "")


def file_id(chave: str | None) -> str | None:
    return FILE_IDS.get(chave or "")
