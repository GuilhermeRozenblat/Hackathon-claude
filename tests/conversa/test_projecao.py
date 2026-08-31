"""O que a família digita vira coluna consultável, e o que não pode virar, não vira.

Roda contra as duas implementações de repositório pela fixture `repo` do conftest.
"""

from __future__ import annotations

import itertools

import pytest

from creche_bot.backend.mapa import BackendMapa
from creche_bot.canal.tipos import MensagemEntrada
from creche_bot.conversa import projecao
from creche_bot.conversa.maquina import Maquina
from creche_bot.ia.redacao import RedatorEstatico

_seq = itertools.count(1)

CPF_NOVO = "111.444.777-35"


def msg(texto=None, escolha=None) -> MensagemEntrada:
    return MensagemEntrada(canal="telegram", id_externo="777",
                           id_mensagem=str(next(_seq)), texto=texto, escolha=escolha)


@pytest.fixture
def bot(repo):
    return Maquina(BackendMapa(), RedatorEstatico(), repo)


# Blocos 0 a 6, na ordem do roteiro: a criança primeiro, o responsável depois.
# No bloco 2 a família recusa o dado sensível, que é o caminho mais curto até o endereço.
ATE_O_ENDERECO = [
    msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"),
    msg(CPF_NOVO), msg("10/01/2024"),                                    # bloco 1
    msg(escolha="nunca"), msg(escolha="pular"),                          # bloco 2
    msg("Ana Beatriz da Silva"), msg(escolha="consta"),                  # bloco 3
    msg("Maria da Silva Santos"),
    msg("Maria da Silva Santos"), msg(CPF_NOVO), msg("07/11/1990"),
    msg("21999998888"), msg(escolha="nao"), msg(escolha="nao"),          # bloco 4
    msg(escolha="certo"),                                                # bloco 5
    msg("22710-560, 100"), msg(escolha="confirma"),                      # bloco 6
]


def andar(bot, entradas):
    resposta = None
    for entrada in entradas:
        resposta = bot.processar(entrada)
    return resposta


# ------------------------------------------------- a projeção, isoladamente
def test_contexto_vazio_nao_vira_linha():
    """`/start` por hábito não pode criar cadastro em branco no banco."""
    assert projecao.cadastro_de("c1", {}) is None
    assert projecao.cadastro_de("c1", {"visto_em": "2026-08-30"}) is None


def test_inscricao_ja_efetivada_nao_reabre_cadastro():
    """O contexto continua cheio depois do protocolo; sem esta guarda o turno seguinte
    duplicaria a criança que acabou de ser inscrita."""
    dados = {"nome_crianca": "Ana", "numero": "2026-0000001"}
    assert projecao.cadastro_de("c1", dados) is None


def test_preferencias_guardam_a_ordem_e_o_fato_da_tela():
    dados = {
        "nome_crianca": "Ana",
        "escolas": [{"id": "a", "nome": "CRECHE A", "km": 1.2, "ociosa": False,
                     "concorrencia": [5.0, 2025], "chance": 0.18},
                    {"id": "b", "nome": "CRECHE B", "km": 0.4, "ociosa": True,
                     "concorrencia": None, "chance": 0.62}],
        "preferencias": ["b", "a"],
    }
    cadastro = projecao.cadastro_de("c1", dados)
    assert [p.posicao for p in cadastro.preferencias] == [1, 2]
    assert cadastro.preferencias[0].id_escola == "b"
    assert cadastro.preferencias[0].vaga_ociosa is True
    assert cadastro.preferencias[0].chance == 0.62       # a que estava NA TELA
    assert cadastro.preferencias[1].familias_por_vaga == 5.0
    assert cadastro.preferencias[1].ano_referencia == 2025


def test_criterio_sensivel_vai_marcado_e_sem_o_que_foi_contado():
    """LGPD art. 11: o banco sabe que "violencia_domestica" foi declarado. Nada além."""
    dados = {
        "nome_crianca": "Ana",
        "criterios": [{"codigo": "violencia_domestica", "sensivel": True},
                      {"codigo": "cadunico", "sensivel": False}],
        "declarados": ["violencia_domestica", "cadunico"],
        "comprovados": ["cadunico"],
    }
    cadastro = projecao.cadastro_de("c1", dados)
    por_codigo = {c.codigo: c for c in cadastro.criterios}
    assert por_codigo["violencia_domestica"].sensivel is True
    assert por_codigo["cadunico"].sensivel is False
    assert por_codigo["cadunico"].comprovado is True
    assert por_codigo["violencia_domestica"].comprovado is False
    # Nenhum campo carrega texto livre: só código e booleano.
    assert set(vars(por_codigo["violencia_domestica"])) == {
        "codigo", "declarado", "comprovado", "sensivel"}


def test_criterio_nao_declarado_nao_vira_linha_falsa():
    """A régua muda todo ano; gravar ausência inventaria pergunta que não foi feita."""
    dados = {"nome_crianca": "Ana",
             "criterios": [{"codigo": "cadunico", "sensivel": False},
                           {"codigo": "monoparental", "sensivel": False}],
             "declarados": ["cadunico"]}
    cadastro = projecao.cadastro_de("c1", dados)
    assert [c.codigo for c in cadastro.criterios] == ["cadunico"]


# --------------------------------------------------- fim a fim, pelo repositório
def test_resposta_digitada_chega_ao_repositorio_antes_do_fim(bot, repo):
    """Grava a cada turno, não só no envio: quem abandona no meio é o que interessa medir."""
    andar(bot, ATE_O_ENDERECO)
    contato_id = repo.contato_de("telegram", "777")
    cadastro = repo.cadastro_de(contato_id)

    assert cadastro is not None
    assert cadastro.protocolo is None            # ainda aberto
    assert cadastro.nome_crianca == "Ana Beatriz da Silva"
    assert cadastro.nascimento_crianca == "2024-01-10"
    assert cadastro.cep == "22710560"
    assert cadastro.bairro == "Curicica"         # derivado do CEP, nunca digitado


def test_toda_coluna_do_cadastro_e_alcancavel_pelo_roteiro(bot, repo):
    """Coluna que o roteiro não preenche vira barra em zero no painel, que é pior que
    não existir: parece abandono da família e é desalinhamento nosso. Este teste anda o
    cadastro inteiro e cobra que cada coluna tenha sido alcançada por alguma pergunta."""
    com_email = [
        msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"),
        msg(CPF_NOVO), msg("10/01/2024"),
        msg(escolha="nunca"), msg(escolha="pular"),
        msg("Ana Beatriz da Silva"), msg(escolha="consta"),
        msg("Maria da Silva Santos"),
        msg("Maria da Silva Santos"), msg(CPF_NOVO), msg("07/11/1990"),
        msg("21999998888"), msg(escolha="nao"), msg(escolha="sim"),
        msg("maria@exemplo.com"),
        msg(escolha="certo"),
        msg("22710-560, 100"), msg(escolha="confirma"), msg(escolha="integral"),
    ]
    andar(bot, com_email)
    cadastro = repo.cadastro_de(repo.contato_de("telegram", "777"))

    vazias = [c for c, v in vars(cadastro).items()
              if v is None and c not in ("protocolo",)]
    assert not vazias, f"nenhuma pergunta do roteiro preenche: {vazias}"


def test_o_documento_da_crianca_e_o_cpf_que_o_bloco_1_pede(bot, repo):
    """O bloco 1 pede o CPF da criança, e ele tem que chegar à coluna. Antes o dado era
    coletado e descartado na projeção, porque a coluna nasceu com outro nome."""
    andar(bot, ATE_O_ENDERECO)
    cadastro = repo.cadastro_de(repo.contato_de("telegram", "777"))
    assert cadastro.documento_crianca == "11144477735"    # normalizado, como todo CPF


def test_origem_escolar_chega_refinada(bot, repo):
    """"Estuda em outra" é a porta para a segunda pergunta, não uma resposta: o que vai
    para a coluna é `particular` ou `outra_rede`."""
    entradas = [msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"),
                msg(CPF_NOVO), msg("10/01/2024"),
                msg(escolha="outra"), msg(escolha="particular")]
    andar(bot, entradas)
    cadastro = repo.cadastro_de(repo.contato_de("telegram", "777"))
    assert cadastro.origem == "particular"


def test_envio_carimba_o_protocolo_e_abre_a_linha_do_tempo(bot, repo):
    painel = andar(bot, [*ATE_O_ENDERECO, msg(escolha="integral")])
    andar(bot, [msg(escolha=painel.botoes[0].id), msg(escolha="pronto"),
                msg(escolha="confirmar"), msg(escolha="nao"), msg(escolha="pronto")])

    contato_id = repo.contato_de("telegram", "777")
    assert repo.cadastro_de(contato_id) is None          # o aberto foi fechado

    # O protocolo veio na sessão; é por ele que o cadastro fechado é alcançável.
    _, contexto = repo.carregar_sessao(contato_id)
    protocolo = contexto["numero"]

    fechado = repo.cadastro_de(contato_id, protocolo)
    assert fechado is not None and fechado.protocolo == protocolo
    assert [p.posicao for p in fechado.preferencias] == [1]

    eventos = repo.eventos(protocolo)
    assert [e.etapa_codigo for e in eventos] == ["recebida"]
    assert eventos[0].tipo == "aguardando"


def test_apagar_tudo_nao_deixa_orfao(bot, repo):
    """LGPD art. 18: cadastro, régua, preferências e linha do tempo somem junto."""
    painel = andar(bot, [*ATE_O_ENDERECO, msg(escolha="integral")])
    andar(bot, [msg(escolha=painel.botoes[0].id), msg(escolha="pronto"),
                msg(escolha="confirmar"), msg(escolha="nao"), msg(escolha="pronto")])

    contato_id = repo.contato_de("telegram", "777")
    _, contexto = repo.carregar_sessao(contato_id)
    protocolo = contexto["numero"]

    repo.apagar_tudo(contato_id)
    assert repo.cadastro_de(contato_id) is None
    assert repo.cadastro_de(contato_id, protocolo) is None
    assert repo.eventos(protocolo) == []
