"""Áudio e pergunta solta: os dois caminhos novos que entram na máquina de estados.

Sem rede: o transcritor é uma função, e o redator é um dublê que sempre responde.
"""

from __future__ import annotations

from creche_bot.backend.mock import BackendMock
from creche_bot.canal.tipos import Anexo, MensagemEntrada
from creche_bot.conversa.maquina import LIMITE_DUVIDAS, Maquina
from creche_bot.dados.memoria import RepositorioMemoria
from creche_bot.dominio.tipos import Classificacao
from creche_bot.ia.redacao import RedatorEstatico

CPF_NOVO = "111.444.777-35"      # válido, e o histórico não conhece


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


def toca(escolha: str, id_msg: str = "2") -> MensagemEntrada:
    return MensagemEntrada(canal="telegram", id_externo="777", id_mensagem=id_msg,
                           escolha=escolha)


def comecar(bot) -> None:
    """/start passa pelo bloco 0.0, a tela que pergunta sobre a IA, antes do roteiro."""
    bot.processar(texto("/start"))
    bot.processar(toca("sem_ia"))


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
    comecar(bot)

    resposta = bot.processar(texto("como funciona a fila?", "3"))

    assert "Resposta sobre PORTA" in resposta.texto
    assert bot.processar(texto("oi", "4")).texto == bot.processar(texto("oi", "5")).texto


def test_cota_corta_o_chat_aberto_como_botao_de_gastar():
    redator = RedatorFalante()
    bot = montar(redator)
    for i in range(LIMITE_DUVIDAS + 3):
        bot.processar(texto("como funciona?", str(i)))

    assert len(redator.perguntas) == LIMITE_DUVIDAS


def test_dado_pessoal_nao_vai_junto_com_a_duvida():
    """Só o nome da etapa vai para o modelo, e nada do que a família já contou."""
    redator = RedatorFalante()
    bot = montar(redator)
    comecar(bot)
    bot.processar(texto("como funciona a fila?", "3"))

    assert redator.perguntas == ["como funciona a fila?"]


# --------------------------------------------- quem se perdeu, e não quem errou


class RedatorPerdido(RedatorEstatico):
    """Como o RedatorClaude quando o modelo diz que a mensagem não responde a pergunta."""

    def classificar(self, mensagem: str, estado: str) -> Classificacao:
        return Classificacao(intencao="fora_de_contexto")


class RedatorEspiao(RedatorEstatico):
    """Anota o contexto que iria para o modelo, e deixa o roteiro seguir normalmente."""

    def __init__(self) -> None:
        self.etapas: list[str] = []

    def classificar(self, mensagem: str, estado: str) -> Classificacao:
        self.etapas.append(estado)
        return super().classificar(mensagem, estado)


def ate_o_cpf(bot) -> None:
    bot.processar(texto("/start"))
    for i, escolha in enumerate(("sem_ia", "inscrever", "autorizo"), start=2):
        bot.processar(MensagemEntrada(canal="telegram", id_externo="777",
                                      id_mensagem=str(i), escolha=escolha))


def test_quem_se_perdeu_ouve_a_pergunta_de_novo_em_vez_de_um_erro():
    bot = montar(RedatorPerdido())
    ate_o_cpf(bot)

    r = bot.processar(texto("minha filha tem 2 anos e a gente mudou de casa", "4"))

    assert "desencontrou" in r.texto
    assert "CPF" in r.texto, "a pergunta que estava no ar volta junto com o aviso"


def test_reorientar_duas_vezes_seguidas_seria_loop():
    """Classificador que erra não pode prender a família fora do próprio cadastro."""
    bot = montar(RedatorPerdido())
    ate_o_cpf(bot)

    primeira = bot.processar(texto("qualquer coisa", "4"))
    segunda = bot.processar(texto("outra coisa qualquer", "5"))

    assert "desencontrou" in primeira.texto
    assert "desencontrou" not in segunda.texto, "na segunda o campo valida e reclama"


def test_se_perder_nao_consome_a_resposta_nem_conta_erro():
    bot = montar(RedatorPerdido())
    ate_o_cpf(bot)
    bot.processar(texto("não sei o que você quer", "4"))

    # O CPF continua sendo o que o bot espera: a mensagem anterior não foi consumida.
    assert "data de nascimento" in bot.processar(texto(CPF_NOVO, "5")).texto


def test_o_classificador_ve_a_pergunta_no_ar_mas_nao_o_que_a_familia_respondeu():
    """Dado da família não entra em prompt. A pergunta estática do campo, sim."""
    redator = RedatorEspiao()
    bot = montar(redator)
    ate_o_cpf(bot)
    for i, t in enumerate((CPF_NOVO, "10/01/2024"), start=4):
        bot.processar(texto(t, str(i)))

    assert any("data de nascimento dela" in e for e in redator.etapas)
    assert not any(CPF_NOVO in e or "10/01/2024" in e for e in redator.etapas)


def test_comando_nao_gasta_chamada_de_classificacao():
    redator = RedatorEspiao()
    bot = montar(redator)
    bot.processar(texto("/start"))
    bot.processar(texto("/ajuda", "2"))

    assert redator.etapas == [], "barra é comando, não é resposta nem pergunta"
