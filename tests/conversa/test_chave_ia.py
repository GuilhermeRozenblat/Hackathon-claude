"""A IA é de quem conversa: a tela que pergunta, a chave que entra, e o que falha.

Sem rede: `diagnosticar` e `criar` são trocados por dublês, e nenhuma chave de verdade
aparece aqui.
"""

from __future__ import annotations

import pytest

from creche_bot.backend.mock import BackendMock
from creche_bot.canal.tipos import MensagemEntrada
from creche_bot.conversa import maquina as modulo
from creche_bot.conversa.maquina import Maquina
from creche_bot.conversa.passos import ia
from creche_bot.dados.memoria import RepositorioMemoria
from creche_bot.ia.redacao import RedatorEstatico

CHAVE = "sk-ant-api03-chavedementira"
SEM_CREDITO = "a conta da chave está sem crédito na Anthropic"


class RedatorFalante(RedatorEstatico):
    """O que a chave do usuário compra: resposta livre em vez de silêncio."""

    ultima_falha: str | None = None

    def responder_duvida(self, pergunta: str, etapa: str) -> str:
        return "É assim que funciona"


class RedatorCaido(RedatorFalante):
    """Chave que funcionou no cadastro e parou de funcionar no meio da conversa."""

    ultima_falha = SEM_CREDITO


@pytest.fixture
def bot() -> Maquina:
    return Maquina(BackendMock(), RedatorEstatico(), RepositorioMemoria())


@pytest.fixture
def chave_boa(monkeypatch):
    monkeypatch.setattr(ia, "diagnosticar", lambda chave: None)
    monkeypatch.setattr(modulo, "criar", lambda chave: RedatorFalante())


def texto(t: str, id_msg: str = "1") -> MensagemEntrada:
    return MensagemEntrada(canal="telegram", id_externo="777", id_mensagem=id_msg, texto=t)


def toca(escolha: str, id_msg: str = "2") -> MensagemEntrada:
    return MensagemEntrada(canal="telegram", id_externo="777", id_mensagem=id_msg,
                           escolha=escolha)


# ------------------------------------------------------------------ a tela 0.0

def test_a_primeira_tela_pergunta_antes_de_seguir_sem_ia(bot):
    r = bot.processar(texto("/start"))

    assert {b.id for b in r.botoes} == {"ligar_ia", "sem_ia"}
    assert "chave da Anthropic" in r.texto
    assert "funciona igual" in r.texto, "quem seguir sem IA precisa saber o que perde"


def test_ligar_mostra_o_passo_a_passo(bot):
    bot.processar(texto("/start"))

    r = bot.processar(toca("ligar_ia"))

    assert "console.anthropic.com/settings/keys" in r.texto
    assert "sk-ant-" in r.texto
    assert {b.id for b in r.botoes} == {"sem_ia"}, "dá para desistir no meio"


def test_seguir_sem_ia_entrega_o_roteiro_e_nao_pergunta_de_novo(bot):
    bot.processar(texto("/start"))

    r = bot.processar(toca("sem_ia"))
    assert {b.id for b in r.botoes} == {"inscrever", "acompanhar", "duvidas"}

    de_novo = bot.processar(texto("/start", "3"))
    assert {b.id for b in de_novo.botoes} == {"inscrever", "acompanhar", "duvidas"}


def test_ignorar_a_tela_nao_prende_ninguem(bot):
    """Prender alguém numa tela de chave de API seria o pior desfecho de um bot de creche."""
    bot.processar(texto("/start"))

    r = bot.processar(texto("quero inscrever minha filha", "2"))

    assert "/ia" in r.texto, "a pessoa fica sabendo que seguiu sem IA, e como voltar atrás"
    assert {b.id for b in r.botoes} == {"inscrever", "acompanhar", "duvidas"}


# ------------------------------------------------------------ a chave entrando

def test_a_chave_do_usuario_passa_a_responder(bot, chave_boa):
    bot.processar(texto("/start"))
    bot.processar(toca("ligar_ia"))

    r = bot.processar(texto(CHAVE, "3"))
    assert "funcionou" in r.texto
    assert "Apague" in r.texto, "a chave fica no histórico do chat se ninguém avisar"

    assert "É assim que funciona" in bot.processar(texto("e a fila, como é?", "4")).texto


def test_chave_colada_no_meio_do_cadastro_nao_vira_resposta_de_campo(bot, chave_boa):
    """Sem interceptar, a chave seguiria como resposta do campo no ar, gravada como se
    fosse um nome, e ecoada de volta na tela."""
    bot.processar(texto("/start"))
    for i, escolha in enumerate(("sem_ia", "inscrever", "autorizo"), start=2):
        bot.processar(toca(escolha, str(i)))

    r = bot.processar(texto(CHAVE, "5"))

    assert "funcionou" in r.texto
    assert CHAVE not in r.texto, "chave nunca é ecoada de volta"
    assert "CPF" in bot.processar(texto("qualquer coisa", "6")).texto, "o campo continua no ar"


def test_chave_que_nao_funciona_diz_o_motivo_e_nao_fica_salva(bot, monkeypatch):
    monkeypatch.setattr(ia, "diagnosticar", lambda chave: SEM_CREDITO)
    bot.processar(texto("/start"))

    r = bot.processar(texto(CHAVE, "2"))
    assert SEM_CREDITO in r.texto
    assert {b.id for b in r.botoes} == {"sem_ia"}, "sempre há saída pelo cadastro sem IA"

    assert "está desligada" in bot.processar(texto("/ia", "3")).texto


def test_chave_no_meio_de_uma_frase_tambem_e_interceptada(bot, chave_boa):
    """"prontinho, a chave é sk-ant-..." não pode seguir para o roteiro."""
    bot.processar(texto("/start"))

    r = bot.processar(texto(f"prontinho, a chave é {CHAVE}", "2"))

    assert "funcionou" in r.texto


def test_quem_pediu_para_ligar_nao_e_dispensado_na_primeira_hesitacao(bot):
    bot.processar(texto("/start"))
    bot.processar(toca("ligar_ia"))

    r = bot.processar(texto("não achei o botão de criar chave", "3"))

    assert "sk-ant-" in r.texto, "repete a instrução em vez de desistir por ela"
    assert {b.id for b in r.botoes} == {"sem_ia"}


def test_desistir_na_tela_inicial_leva_ao_roteiro(bot):
    bot.processar(texto("/start"))
    bot.processar(toca("ligar_ia"))

    r = bot.processar(texto("/ia remover", "3"))

    assert {b.id for b in r.botoes} == {"inscrever", "acompanhar", "duvidas"}


def test_formato_errado_nem_chega_a_ser_testado(bot):
    bot.processar(texto("/start"))

    r = bot.processar(texto("/ia minha-chave-secreta", "2"))

    assert "sk-ant-" in r.texto


# --------------------------------------------------------- o que falha depois

def test_falha_no_meio_da_conversa_avisa_uma_vez_so(bot, monkeypatch):
    monkeypatch.setattr(ia, "diagnosticar", lambda chave: None)
    monkeypatch.setattr(modulo, "criar", lambda chave: RedatorCaido())
    bot.processar(texto("/start"))
    bot.processar(texto(f"/ia {CHAVE}", "2"))

    primeira = bot.processar(toca("inscrever", "3"))
    segunda = bot.processar(toca("autorizo", "4"))

    assert SEM_CREDITO in primeira.texto and "/ia" in primeira.texto
    assert SEM_CREDITO not in segunda.texto, "avisar a cada mensagem seria a falha oposta"


def test_status_mostra_a_falha_em_vez_de_dizer_que_esta_tudo_bem(bot, monkeypatch):
    monkeypatch.setattr(ia, "diagnosticar", lambda chave: None)
    monkeypatch.setattr(modulo, "criar", lambda chave: RedatorCaido())
    bot.processar(texto("/start"))
    bot.processar(texto(f"/ia {CHAVE}", "2"))
    bot.processar(toca("inscrever", "3"))

    assert SEM_CREDITO in bot.processar(texto("/ia", "4")).texto


def test_pergunta_solta_sem_ia_ensina_a_ligar(bot):
    bot.processar(texto("/start"))
    bot.processar(toca("sem_ia"))

    assert "/ia" in bot.processar(texto("como funciona a fila?", "3")).texto


# ------------------------------------------------------------ ligar e desligar

def test_remover_apaga_a_chave(bot, chave_boa):
    bot.processar(texto("/start"))
    bot.processar(texto(f"/ia {CHAVE}", "2"))

    assert "Apaguei sua chave" in bot.processar(texto("/ia remover", "3")).texto
    assert "está desligada" in bot.processar(texto("/ia", "4")).texto


def test_recomecar_o_cadastro_nao_desliga_a_ia(bot, chave_boa):
    """"Começar de novo" zera o contexto, e a decisão sobre a IA não é contexto de cadastro."""
    bot.processar(texto("/start"))
    bot.processar(texto(f"/ia {CHAVE}", "2"))
    for i, escolha in enumerate(("inscrever", "autorizo"), start=3):
        bot.processar(toca(escolha, str(i)))
    bot.processar(texto("/start", "5"))          # no meio do cadastro: cai na retomada
    bot.processar(toca("recomecar", "6"))

    assert "está ligada" in bot.processar(texto("/ia", "7")).texto


def test_start_nao_desliga_a_ia_que_a_pessoa_acabou_de_ligar(bot, chave_boa):
    bot.processar(texto("/start"))
    bot.processar(texto(f"/ia {CHAVE}", "2"))
    bot.processar(texto("/start", "3"))

    assert "está ligada" in bot.processar(texto("/ia", "4")).texto
