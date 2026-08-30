"""DEBUG_CONTEUDO espelha a conversa no console — mas nunca os bytes da foto."""

from __future__ import annotations

from creche_bot.canal.telegram import _resumo_entrada, _resumo_saida
from creche_bot.canal.tipos import Anexo, Botao, MensagemEntrada, MensagemSaida


def test_anexo_aparece_como_tamanho_e_nunca_como_bytes():
    foto = b"\x89PNG\r\n" + b"segredo" * 4096
    m = MensagemEntrada(canal="telegram", id_externo="42", id_mensagem="7",
                        texto="olha a certidão", anexo=Anexo(conteudo=foto, mime="image/png"))

    traco = _resumo_entrada(m)

    assert "olha a certidão" in traco
    assert "image/png" in traco and "28 KB" in traco
    assert "segredo" not in traco and "PNG" not in traco


def test_saida_mostra_texto_e_rotulos():
    m = MensagemSaida("Está tudo certo?", botoes=(Botao("s", "Sim"), Botao("n", "Corrigir")))
    assert _resumo_saida(m) == "'Está tudo certo?' botões: Sim | Corrigir"
