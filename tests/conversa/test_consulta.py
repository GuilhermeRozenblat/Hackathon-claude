"""Bloco C — acompanhar uma inscrição que já existe.

Cobre os sete desfechos possíveis, os dois caminhos de busca do portal, e a regra que não
pode ser quebrada: a família vê UM estado, nunca a situação por opção de creche.
"""

from __future__ import annotations

import itertools
from datetime import date

import pytest

from creche_bot.backend.mock import NUMERO_CONHECIDO, BackendMock
from creche_bot.canal.tipos import Anexo, MensagemEntrada
from creche_bot.conversa.maquina import Maquina
from creche_bot.dados.memoria import RepositorioMemoria
from creche_bot.ia.redacao import RedatorEstatico

_seq = itertools.count(1)


@pytest.fixture
def bot():
    return Maquina(BackendMock(), RedatorEstatico(), RepositorioMemoria())


def msg(texto=None, escolha=None, anexo=None):
    return MensagemEntrada(canal="telegram", id_externo="9", id_mensagem=str(next(_seq)),
                           texto=texto, escolha=escolha,
                           anexo=Anexo(anexo, "image/jpeg") if anexo else None)


def consultar(bot, numero: str, nascimento: str):
    for e in (msg("/start"), msg(escolha="acompanhar"), msg(escolha="com_numero")):
        bot.processar(e)
    return bot.processar(msg(f"{numero} {nascimento}"))


# Um por estado, com a frequência real de 2025 no comentário.
CASOS = [
    (NUMERO_CONHECIDO, "10/01/2024", "vaga confirmada", "Ana"),      # 67,7%
    ("2026-0847220", "15/03/2022", "lista de espera", "Pedro"),      # 11,2%
    ("2026-0847231", "02/07/2023", "não seguiu", "Lucas"),           # 9,5%
    ("2026-0847244", "20/11/2023", "chamada", "Sofia"),              # 7,7%
    ("2026-0847255", "05/02/2024", "cancelada", "Miguel"),           # 3,8%
    ("2026-0847266", "09/05/2023", "selecionada", "Helena"),         # 0,2%
    ("2026-0847277", "18/04/2024", "ativa", "Théo"),                 # 0,0%
]


@pytest.mark.parametrize(("numero", "nascimento", "esperado", "nome"), CASOS)
def test_os_sete_desfechos_tem_tela(bot, numero, nascimento, esperado, nome):
    r = consultar(bot, numero, nascimento)
    assert esperado in r.texto.lower() or esperado in r.texto
    assert nome in r.texto


def test_nunca_mostra_a_situacao_bruta_da_opcao(bot):
    """77,8% das linhas "Cancelado pelo sistema" pertencem a inscrição ATENDIDA. Uma
    família com vaga veria "cancelado" em 4 das 5 escolhas dela."""
    r = consultar(bot, NUMERO_CONHECIDO, "10/01/2024")
    assert "cancelado pelo sistema" not in r.texto.lower()
    assert "vaga confirmada" in r.texto.lower()


def test_nunca_informa_posicao_na_fila_nem_pontuacao(bot):
    for numero, nascimento, _, _ in CASOS:
        r = consultar(Maquina(BackendMock(), RedatorEstatico(), RepositorioMemoria()),
                      numero, nascimento)
        baixo = r.texto.lower()
        for proibido in ("posição", "sua pontuação", "pontos", "lugar na fila", "º na fila"):
            assert proibido not in baixo, f"{numero}: {baixo}"


def test_selecionada_e_o_primeiro_balao(bot):
    """Prazo vencendo em silêncio é o que faz 7,7% perder a vaga já convocada."""
    r = consultar(bot, "2026-0847266", "09/05/2023")
    assert r.figurinha == "festa", "convocação é fato consumado: pode comemorar"
    assert "confirmar até" in r.texto
    assert {b.id for b in r.botoes} == {"confirmar", "nao_posso"}


def test_lista_de_espera_cobra_o_documento_que_falta(bot):
    """É aqui que a consulta deixa de ser passiva: quem está na fila com critério
    pendente é exatamente quem perdeu pontuação por não comprovar."""
    r = consultar(bot, "2026-0847220", "15/03/2022")
    assert "falta comprovar" in r.texto.lower()
    assert {b.id for b in r.botoes} == {"mandar_nis", "depois"}

    r = bot.processar(msg(escolha="mandar_nis"))
    assert "NIS" in r.texto
    r = bot.processar(msg("12345678901"))
    assert "NIS" in r.texto or "avise" in r.texto.lower()


def test_nao_seguiu_nao_inventa_o_motivo(bot):
    """Estado ambíguo no banco. Encaminhe, não adivinhe."""
    r = consultar(bot, "2026-0847231", "02/07/2023")
    assert "costuma acontecer" in r.texto
    assert "1746" in r.texto


def test_caminho_por_nome_funciona_sem_o_numero(bot):
    """Nem todo mundo guarda o número, e há criança sem filiação na certidão."""
    for e in (msg("/start"), msg(escolha="acompanhar"), msg(escolha="sem_numero")):
        r = bot.processar(e)
    assert "nome completo" in r.texto

    r = bot.processar(msg("Lucas Andrade"))
    assert "data de nascimento" in r.texto
    r = bot.processar(msg("02/07/2023"))
    assert "certidão" in r.texto
    r = bot.processar(msg(escolha="nao_consta"))
    assert "responsável legal" in r.texto, "sem filiação, pergunta o responsável legal"

    r = bot.processar(msg("Ana Paula Andrade"))
    assert "Lucas" in r.texto


def test_nao_achou_explica_e_nao_deixa_em_loop(bot):
    r = consultar(bot, "2026-9999999", "01/01/2020")
    assert "não achei" in r.texto.lower()
    assert "abreviado" in r.texto, "o motivo mais comum vem primeiro"
    assert {b.id for b in r.botoes} == {"tentar", "inscrever", "atendente"}


def test_tres_tentativas_e_oferece_atendente(bot):
    for e in (msg("/start"), msg(escolha="acompanhar"), msg(escolha="com_numero")):
        bot.processar(e)
    for _ in range(2):
        r = bot.processar(msg("não sei o número"))
        assert "número da inscrição" in r.texto
    r = bot.processar(msg("também não"))
    assert "não achei" in r.texto.lower()


def test_ativar_avisos_e_o_turno_mais_valioso(bot):
    """É assim que o bot alcança quem se inscreveu pelo site."""
    consultar(bot, NUMERO_CONHECIDO, "10/01/2024")
    r = bot.processar(msg(escolha="acoes"))
    assert {i.id for i in r.lista} == {"doc", "telefone", "endereco", "outra"}


def test_atualizar_telefone_parece_pequeno_e_nao_e(bot):
    """Contato desatualizado é uma das causas dos 7,7% que perdem a vaga convocados."""
    consultar(bot, NUMERO_CONHECIDO, "10/01/2024")
    bot.processar(msg(escolha="acoes"))
    r = bot.processar(msg(escolha="telefone"))
    assert "número novo" in r.texto

    r = bot.processar(msg("(21) 99887-7665"))
    assert "(21) 99887-7665" in r.texto
    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "9"))
    assert dados["telefone"] == "21998877665", "guarda normalizado, mostra legível"


def test_mudanca_de_endereco_vai_para_a_cre(bot):
    """Pode alterar o polo de classificação: não é edição de cadastro."""
    consultar(bot, NUMERO_CONHECIDO, "10/01/2024")
    bot.processar(msg(escolha="acoes"))
    r = bot.processar(msg(escolha="endereco"))
    assert "polo" in r.texto and "1746" in r.texto


def test_confirmar_a_vaga_registra_e_oferece_avisos(bot):
    consultar(bot, "2026-0847266", "09/05/2023")
    r = bot.processar(msg(escolha="confirmar"))
    assert "confirmado" in r.texto.lower()
    assert "avise" in r.texto.lower() or "novidade" in r.texto.lower()


def test_consulta_nao_exige_o_consentimento_de_inscricao(bot):
    """Consultar a própria inscrição é direito de acesso (art. 18), não tratamento novo —
    e exigir o consentimento de inscrição barraria quem se inscreveu pelo site."""
    r = consultar(bot, NUMERO_CONHECIDO, "10/01/2024")
    assert "Ana" in r.texto
    assert not bot._repo.tem_consentimento(bot._repo.contato_de("telegram", "9"))


def test_desfecho_do_mock_bate_com_a_precedencia_do_dominio():
    from creche_bot.dominio.tipos import desfecho_entre

    b = BackendMock()
    achados = b.consultar_por_numero(NUMERO_CONHECIDO, date(2024, 1, 10))
    assert achados[0].estado == desfecho_entre([achados[0].estado, "cancelada"])
