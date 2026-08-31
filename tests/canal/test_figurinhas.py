"""A figurinha é decisão de tom, e tom errado aqui vira promessa que a SME não honra."""

from __future__ import annotations

from creche_bot.canal.figurinhas import EMOJI
from creche_bot.canal.render import render
from creche_bot.canal.tipos import MensagemSaida
from creche_bot.ia.persona import FIGURINHAS, TEXTOS


def test_toda_figurinha_do_roteiro_existe_no_catalogo():
    """Chave errada não explode: vira string vazia e a mensagem sai sem emoji nenhum."""
    orfas = sorted(set(FIGURINHAS.values()) - set(EMOJI))
    assert not orfas, f"sem emoji em canal/figurinhas.py: {orfas}"


def test_toda_chave_do_mapa_e_um_texto_que_existe():
    orfas = sorted(set(FIGURINHAS) - set(TEXTOS))
    assert not orfas, f"figurinha para texto que não existe: {orfas}"


def test_nenhum_emoji_insinua_sorte_ou_vaga():
    """O sistema cadastra e informa; ele não decide quem entra."""
    assert not set(EMOJI.values()) & {"🤞", "🍀", "🏆", "🎰", "💰"}


def test_render_pendura_o_emoji_no_fim_do_texto():
    (metodo, params), = render(MensagemSaida("Pronto!", figurinha="festa"))
    assert metodo == "sendMessage"
    assert params["text"] == "Pronto!\n\n🥳"
