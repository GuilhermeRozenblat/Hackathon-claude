"""O `/demo`: as três famílias prontas, e a saída de volta ao bot normal.

Roda contra o `BackendMock`, sem rede: a demonstração de verdade usa o `BackendMapa`, mas
quem quebra aqui é o carregamento da sessão, não a oferta de creches.
"""

from __future__ import annotations

import itertools

import pytest

from creche_bot.backend.mock import BackendMock
from creche_bot.canal.tipos import MensagemEntrada
from creche_bot.conversa.maquina import Maquina
from creche_bot.conversa.passos.demo import OPCOES
from creche_bot.ia.redacao import RedatorEstatico

_seq = itertools.count(1)


@pytest.fixture
def bot(repo):
    return Maquina(BackendMock(), RedatorEstatico(), repo)


def msg(texto=None, escolha=None) -> MensagemEntrada:
    return MensagemEntrada(canal="telegram", id_externo="42", id_mensagem=str(next(_seq)),
                           texto=texto, escolha=escolha)


def abrir(bot, persona: str):
    bot.processar(msg("/demo"))
    return bot.processar(msg(escolha=persona))


def test_menu_abre_sem_consentimento(bot):
    """`DEMO` fora de `LIVRES` derruba o avaliador para o INICIO, e só a banca descobre."""
    r = bot.processar(msg("/demo"))
    assert {i.id for i in r.lista} == {"escolhendo", "inscrita", "volta", "normal"}
    assert not r.botoes


def test_a_saida_devolve_o_bot_normal(bot):
    """Escolher demo tem que ter volta: sem isto a demonstração vira porta sem maçaneta."""
    abrir(bot, "escolhendo")
    r = bot.processar(msg("/demo"))
    r = bot.processar(msg(escolha="normal"))
    assert {b.id for b in r.botoes} == {"inscrever", "acompanhar", "duvidas"}


def test_escolhendo_cai_no_painel_de_creches_e_continua(bot):
    """Sem consentimento, endereço, grupamento ou horário, isto não chega ao painel."""
    r = abrir(bot, "escolhendo")
    assert r.botoes, r.texto
    # A tela seguinte é a da escolha, não a saudação: a demo entrou no roteiro, não ao lado.
    seguinte = bot.processar(msg(escolha=r.botoes[0].id))
    assert "1a opção" in seguinte.texto or "Pronto" in {b.rotulo for b in seguinte.botoes}


def test_inscrita_grava_inscricao_com_o_cadastro_que_a_gerou(bot, repo):
    """A projeção para de gravar quando existe `numero`, e o painel mostraria inscrição
    órfã. É o defeito que a linha do `salvar_cadastro` em `demo.py` existe para impedir."""
    r = abrir(bot, "inscrita")
    contato = repo.contato_de("telegram", "42")
    _, dados = repo.carregar_sessao(contato)
    protocolo = dados["numero"]

    assert protocolo in r.texto
    assert repo.inscricao(protocolo) is not None
    cadastro = repo.cadastro_de(contato, protocolo)
    assert cadastro is not None and cadastro.preferencias
    assert repo.eventos(protocolo)


def test_inscrita_duas_vezes_nao_duplica_a_inscricao(bot, repo):
    """`chave_idempotencia` é contato + nome da criança, e os dois se repetem."""
    primeiro = abrir(bot, "inscrita")
    segundo = abrir(bot, "inscrita")
    contato = repo.contato_de("telegram", "42")
    assert repo.carregar_sessao(contato)[1]["numero"] in primeiro.texto
    assert repo.carregar_sessao(contato)[1]["numero"] in segundo.texto


def test_escolher_persona_nao_desliga_a_ia_ja_ligada(bot, repo):
    """Mesmo gesto do "Começar de novo" da retomada: trocar de persona não é uma decisão
    sobre a chave de IA que a pessoa já cadastrou."""
    contato = repo.contato_de("telegram", "42")
    _, dados = repo.carregar_sessao(contato)
    dados["chave_ia"] = "sk-ant-teste"
    repo.salvar_sessao(contato, "INICIO", dados)

    abrir(bot, "escolhendo")
    _, dados = repo.carregar_sessao(contato)
    assert dados.get("chave_ia") == "sk-ant-teste"


def test_volta_reconhece_o_cadastro_do_ano_passado(bot):
    r = abrir(bot, "volta")
    assert "Curicica" in r.texto
    assert {b.id for b in r.botoes} == {"tudo_certo", "mudei_endereco"}


def test_nenhuma_tela_da_demo_promete_vaga_nem_usa_markdown():
    """As telas daqui não passam por `ia/persona.py`, então a varredura de lá não as cobre."""
    proibidas = ("garantido", "com certeza", "vai conseguir", "sua pontuação",
                 "nota de corte", "posição na fila", "sua chance")
    from creche_bot.conversa.passos.demo import MENU

    for texto in [MENU, *(f"{i.titulo} {i.descricao}" for i in OPCOES)]:
        assert not any(x in texto.lower() for x in proibidas), texto
        assert not any(m in texto for m in ("**", "__", "`", "# ")), texto
    # O WhatsApp corta o título de um item de lista, como corta o rótulo de botão.
    assert all(len(i.titulo) <= 20 for i in OPCOES)
