"""Áudio e pergunta solta: os dois caminhos novos que entram na máquina de estados.

Sem rede: o transcritor é uma função, e o redator é um dublê que sempre responde.
"""

from __future__ import annotations

from creche_bot.backend.mock import BackendMock
from creche_bot.canal.tipos import Anexo, MensagemEntrada
from creche_bot.conversa.maquina import LIMITE_DUVIDAS, Maquina
from creche_bot.dados.memoria import RepositorioMemoria
from creche_bot.ia.redacao import RedatorEstatico


class RedatorFalante(RedatorEstatico):
    """Como o RedatorClaude se comporta: sempre devolve uma resposta livre."""

    def __init__(self) -> None:
        self.perguntas: list[str] = []

    def responder_duvida(self, pergunta: str, etapa: str) -> str:
        self.perguntas.append(pergunta)
        return f"Resposta sobre {etapa}"


def montar(redator=None, transcritor=None) -> Maquina:
    return Maquina(BackendMock(), redator or RedatorEstatico(), RepositorioMemoria(),
                   transcritor)


def audio(conteudo: bytes = b"opus") -> MensagemEntrada:
    return MensagemEntrada(canal="telegram", id_externo="777", id_mensagem="1",
                           anexo=Anexo(conteudo, "audio/ogg"))


def texto(t: str, id_msg: str = "1") -> MensagemEntrada:
    return MensagemEntrada(canal="telegram", id_externo="777", id_mensagem=id_msg, texto=t)


def test_audio_vira_texto_e_segue_o_mesmo_caminho():
    bot = montar(transcritor=lambda _: "quero começar")
    assert "Zé Matrícula" in bot.processar(audio()).texto


def test_audio_indecifravel_pede_para_escrever():
    bot = montar(transcritor=lambda _: None)
    assert "escrever" in bot.processar(audio()).texto


def test_sem_transcritor_o_bot_avisa_em_vez_de_quebrar():
    assert "escrever" in montar().processar(audio()).texto


def test_duvida_nao_faz_perder_o_lugar_na_fila():
    """Perguntar no meio do cadastro responde a pergunta e mantém o estado."""
    redator = RedatorFalante()
    bot = montar(redator)
    bot.processar(texto("/start"))

    resposta = bot.processar(texto("como funciona a fila?", "2"))

    assert "Resposta sobre PORTA" in resposta.texto
    assert bot.processar(texto("oi", "3")).texto == bot.processar(texto("oi", "4")).texto


def test_cota_corta_o_chat_aberto_como_botao_de_gastar():
    redator = RedatorFalante()
    bot = montar(redator)
    for i in range(LIMITE_DUVIDAS + 3):
        bot.processar(texto("como funciona?", str(i)))

    assert len(redator.perguntas) == LIMITE_DUVIDAS


def test_dado_pessoal_nao_vai_junto_com_a_duvida():
    """Só o nome da etapa vai para o modelo — nada do que a família já contou."""
    redator = RedatorFalante()
    bot = montar(redator)
    bot.processar(texto("/start"))
    bot.processar(texto("como funciona a fila?", "2"))

    assert redator.perguntas == ["como funciona a fila?"]
