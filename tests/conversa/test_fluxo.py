"""O roteiro do Zé Matrícula, ponta a ponta. Sem rede, sem Telegram, sem chave de API.

Cada teste roda contra as DUAS implementações de repositório. Se divergirem, acusa aqui.
"""

from __future__ import annotations

import itertools
import tempfile

import pytest

from creche_bot.backend.mock import CPF_CONHECIDO, BackendMock
from creche_bot.canal.tipos import Anexo, MensagemEntrada, MensagemSaida
from creche_bot.conversa.maquina import Maquina
from creche_bot.dados.memoria import RepositorioMemoria
from creche_bot.dados.sqlite import RepositorioSQLite
from creche_bot.ia.redacao import RedatorEstatico

_seq = itertools.count(1)


@pytest.fixture(params=["memoria", "sqlite"])
def bot(request):
    repo = (RepositorioMemoria() if request.param == "memoria"
            else RepositorioSQLite(tempfile.mktemp(suffix=".db")))
    return Maquina(BackendMock(), RedatorEstatico(), repo)


def msg(texto=None, escolha=None, anexo=None) -> MensagemEntrada:
    return MensagemEntrada(
        canal="telegram", id_externo="777", id_mensagem=str(next(_seq)),
        texto=texto, escolha=escolha,
        anexo=Anexo(anexo, "image/jpeg") if anexo else None,
    )


def responder(bot, *entradas) -> MensagemSaida:
    resposta = None
    for e in entradas:
        resposta = bot.processar(e if isinstance(e, MensagemEntrada) else msg(e))
    return resposta


CADASTRO_NOVO = [
    msg("/start"), msg(escolha="aceito"),
    msg("999.888.777-66"), msg("10/02/2024"),          # data lake não conhece
    msg(escolha="nunca_estudou"), msg(escolha="nunca_estudou"),
    msg(escolha="nao"),                                # sem necessidade especial
    msg("Pedro Henrique Lima"), msg(escolha="sim"),
    msg("Carla Souza Lima"), msg("Carla Souza Lima"),
    msg("07/11/1990"),                                 # nascimento do responsável
    msg(escolha="nao"),                                # sem deficiência na família
    msg("(21) 99988-7766"), msg(escolha="nao"),        # sem segundo contato
    msg(escolha="nao"),                                # sem e-mail
]


def test_cadastro_novo_ate_o_resumo(bot):
    r = responder(bot, *CADASTRO_NOVO)
    assert "resumo" in r.texto.lower()
    assert "Pedro Henrique Lima" in r.texto
    assert "nunca estudou" in r.texto
    assert len(r.botoes) == 2


def test_data_lake_encontra_e_pula_para_o_resumo(bot):
    """Bloco 1 SIM: CPF conhecido + data certa pula todo o preenchimento."""
    r = responder(bot, msg("/start"), msg(escolha="aceito"),
                  msg(CPF_CONHECIDO), msg("18/03/2024"))
    assert "encontrei um cadastro" in r.texto.lower()

    r = bot.processar(msg("segue"))
    assert "Sofia Ribeiro Alves" in r.texto
    assert "Juliana Ribeiro Alves" in r.texto
    assert "E-mail" not in r.texto, "campo ausente no data lake não pode aparecer no resumo"


def test_cpf_certo_data_errada_nao_traz_outra_crianca(bot):
    r = responder(bot, msg("/start"), msg(escolha="aceito"),
                  msg(CPF_CONHECIDO), msg("01/01/2020"))
    assert "não encontrei" in r.texto.lower()


def test_fluxo_completo_ate_protocolo(bot):
    responder(bot, *CADASTRO_NOVO)
    r = bot.processar(msg(escolha="ok"))                 # resumo confirmado
    assert "CEP ou bairro" in r.texto

    r = bot.processar(msg("20220-030"))
    assert r.texto.count("🏫") == 3
    assert "nota de corte" in r.texto.lower()
    assert len(r.botoes) == 3

    primeira = r.botoes[0].id
    r = bot.processar(msg(escolha=primeira))             # 1ª preferência
    assert "1️⃣" in r.texto and len(r.botoes) == 3       # 2 restantes + Pronto

    r = bot.processar(msg(escolha="pronto"))
    assert "ordem de preferência" in r.texto.lower()

    r = bot.processar(msg(escolha="confirma"))
    assert len(r.botoes) == 3                            # WhatsApp / creche / CRAS

    r = bot.processar(msg(escolha="cras"))
    assert "RIO-" in r.texto
    assert "CRAS" in r.texto
    assert r.local is not None, "entrega presencial tem que mandar o pino"


def test_cras_avisa_sobre_o_trajeto_ate_a_creche(bot):
    """Lacuna conhecida do processo: ninguém avisa quando o CRAS repassa à creche.
    O texto tem que ser honesto sobre isso em vez de deixar a família no escuro."""
    responder(bot, *CADASTRO_NOVO)
    bot.processar(msg(escolha="ok"))
    r = bot.processar(msg("20220-030"))
    bot.processar(msg(escolha=r.botoes[0].id))
    bot.processar(msg(escolha="pronto"))
    bot.processar(msg(escolha="confirma"))
    r = bot.processar(msg(escolha="cras"))
    assert "seguem para a creche" in r.texto


def test_ordem_de_preferencia_respeita_a_sequencia_de_toques(bot):
    responder(bot, *CADASTRO_NOVO)
    bot.processar(msg(escolha="ok"))
    r = bot.processar(msg("20220-030"))
    ids = [b.id for b in r.botoes]

    bot.processar(msg(escolha=ids[2]))       # escolhe a terceira primeiro
    bot.processar(msg(escolha=ids[0]))
    r = bot.processar(msg(escolha="pronto"))

    linhas = [x for x in r.texto.splitlines() if x.startswith(("1️⃣", "2️⃣"))]
    assert len(linhas) == 2
    assert "Zilda Arns" in linhas[0], "a 1ª tem que ser a primeira tocada"


def test_documento_ilegivel_nao_grava(bot):
    responder(bot, *CADASTRO_NOVO)
    bot.processar(msg(escolha="ok"))
    r = bot.processar(msg("20220-030"))
    bot.processar(msg(escolha=r.botoes[0].id))
    bot.processar(msg(escolha="pronto"))
    bot.processar(msg(escolha="confirma"))
    bot.processar(msg(escolha="whatsapp"))

    r = bot.processar(msg(anexo=b"x" * 10))
    assert "não consegui ler" in r.texto.lower()


def test_correcao_volta_ao_campo_certo(bot):
    responder(bot, *CADASTRO_NOVO)
    r = bot.processar(msg(escolha="corrigir"))
    assert len(r.lista) <= 10

    # São mais campos do que os 10 itens do WhatsApp: a lista pagina em vez de truncar,
    # senão os últimos do formulário ficariam impossíveis de corrigir.
    assert r.lista[-1].id == "mais_campos"
    r = bot.processar(msg(escolha="mais_campos"))
    assert len(r.lista) <= 10 and any(i.id == "telefone" for i in r.lista)

    r = bot.processar(msg(escolha="telefone"))
    assert "telefone" in r.texto.lower()

    r = bot.processar(msg("(21) 3333-4444"))
    assert "resumo" in r.texto.lower()
    # Guardamos normalizado, mostramos legível: o eco existe para a pessoa conferir.
    assert "(21) 3333-4444" in r.texto and "2133334444" not in r.texto


def test_consentimento_sensivel_precede_a_pergunta_de_saude(bot):
    """LGPD art. 11: dado de saúde exige consentimento específico e destacado."""
    r = responder(bot, msg("/start"), msg(escolha="aceito"),
                  msg("999.888.777-66"), msg("10/02/2024"),
                  msg(escolha="nunca_estudou"), msg(escolha="nunca_estudou"))
    assert "opcional" in r.texto.lower()
    assert "dado sensível" in r.texto.lower()
    assert any(b.id == "nao_informar" for b in r.botoes), "tem que dar para recusar"


def test_sem_consentimento_nao_passa_do_inicio(bot):
    bot.processar(msg("/start"))
    r = bot.processar(msg(escolha="recuso"))
    assert "autorização" in r.texto.lower()

    contato = bot._repo.contato_de("telegram", "777")
    bot._repo.salvar_sessao(contato, "FORMULARIO", {})
    bot.processar(msg("tentando pular"))
    assert bot._repo.carregar_sessao(contato)[0] == "CONSENTIMENTO"


def test_nenhuma_tela_estoura_tres_botoes(bot):
    """Varre o roteiro inteiro. MensagemSaida já cobra, mas o teste nomeia a intenção."""
    entradas = [*CADASTRO_NOVO, msg(escolha="ok"), msg("20220-030")]
    for e in entradas:
        r = bot.processar(e)
        assert len(r.botoes) <= 3 and len(r.lista) <= 10


def test_bot_nunca_promete_vaga(bot):
    proibidas = ("garantido", "com certeza", "vai conseguir")
    entradas = [*CADASTRO_NOVO, msg(escolha="ok"), msg("20220-030")]
    for e in entradas:
        texto = bot.processar(e).texto.lower()
        assert not any(x in texto for x in proibidas), texto


def test_ja_tenho_inscricao_vai_para_o_status(bot):
    """Bloco 0 do roteiro tem duas portas: começar, ou consultar o que já existe."""
    r = bot.processar(msg("/start"))
    assert any(b.id == "ja_tenho" for b in r.botoes)

    r = bot.processar(msg(escolha="ja_tenho"))
    assert "ainda não tem inscrição" in r.texto
    contato = bot._repo.contato_de("telegram", "777")
    assert not bot._repo.tem_consentimento(contato), "consultar status não é consentir"


def test_matricula_tem_saida_para_quem_nao_sabe(bot):
    """O roteiro pede o botão 'não sei / não tenho agora'. Sem ele a pessoa trava numa
    pergunta cuja resposta está numa gaveta em casa."""
    r = responder(bot, msg("/start"), msg(escolha="aceito"),
                  msg("999.888.777-66"), msg("10/02/2024"),
                  msg(escolha="rede_municipal"))
    assert "matrícula" in r.texto.lower()
    assert [b.id for b in r.botoes] == ["nao_sei"]

    r = bot.processar(msg(escolha="nao_sei"))
    assert "deficiência" in r.texto.lower(), "seguiu para a próxima pergunta"


def test_prioridade_sai_da_idade_do_responsavel():
    """Critério legal deduzido, não perguntado — o roteiro é explícito nisso."""
    from creche_bot.conversa.formulario import criterios_prioridade

    assert criterios_prioridade({"data_nascimento_responsavel": "1950-06-01"}) == (
        "responsavel_60_mais",)
    assert criterios_prioridade({"data_nascimento_responsavel": "2010-06-01"}) == (
        "responsavel_menor_18",)
    assert criterios_prioridade({"data_nascimento_responsavel": "1990-06-01"}) == ()
    assert criterios_prioridade({}) == (), "sem a data, nada é marcado"


def test_segundo_contato_e_prioridade_aparecem_no_resumo(bot):
    entradas = [
        msg("/start"), msg(escolha="aceito"),
        msg("999.888.777-66"), msg("10/02/2024"),
        msg(escolha="nunca_estudou"), msg(escolha="nunca_estudou"), msg(escolha="nao"),
        msg("Pedro Henrique Lima"), msg(escolha="sim"),
        msg("Carla Souza Lima"), msg("Carla Souza Lima"),
        msg("07/11/1955"),                              # responsável com mais de 60
        msg(escolha="nao"),
        msg("(21) 99988-7766"),
        msg(escolha="sim"), msg("(21) 3333-4444"),      # segundo contato
        msg(escolha="nao"),
    ]
    r = responder(bot, *entradas)
    assert "(21) 3333-4444" in r.texto
    assert "60 anos ou mais" in r.texto


def test_protocolo_vem_com_link_de_acompanhamento(bot):
    responder(bot, *CADASTRO_NOVO)
    bot.processar(msg(escolha="ok"))
    r = bot.processar(msg("20220-030"))
    bot.processar(msg(escolha=r.botoes[0].id))
    bot.processar(msg(escolha="pronto"))
    bot.processar(msg(escolha="confirma"))
    r = bot.processar(msg(escolha="creche"))
    assert "matricula.rio/acompanhar/RIO-" in r.texto


def test_start_nao_apaga_a_inscricao_que_ja_existe(bot):
    """/start recomeça o cadastro. Quem já tem protocolo continua tendo — senão o
    'já tenho inscrição' e o /status respondem sempre que não existe nada."""
    responder(bot, *CADASTRO_NOVO)
    bot.processar(msg(escolha="ok"))
    r = bot.processar(msg("20220-030"))
    bot.processar(msg(escolha=r.botoes[0].id))
    bot.processar(msg(escolha="pronto"))
    bot.processar(msg(escolha="confirma"))
    r = bot.processar(msg(escolha="creche"))
    assert "RIO-" in r.texto

    bot.processar(msg("/start"))
    r = bot.processar(msg(escolha="ja_tenho"))
    assert "Pedro" in r.texto and "Passo 3 de 5" in r.texto

    r = bot.processar(msg("/status"))
    assert "Passo 3 de 5" in r.texto
