"""As duas implementações de `Repositorio` têm que ser indistinguíveis.

O bot roda com sqlite em produção e com memória nos testes e no `make memoria`. Se as
duas divergirem, um caminho passa aqui e quebra lá.
"""

from __future__ import annotations

import tempfile

import pytest

from creche_bot.dados.memoria import RepositorioMemoria
from creche_bot.dados.porta import Inscricao, Repositorio
from creche_bot.dados.sqlite import RepositorioSQLite


@pytest.fixture(params=["memoria", "sqlite"])
def repo(request):
    return (RepositorioMemoria() if request.param == "memoria"
            else RepositorioSQLite(tempfile.mktemp(suffix=".db")))


def test_implementa_a_porta(repo):
    assert isinstance(repo, Repositorio)


def test_mesmo_canal_e_id_dao_o_mesmo_contato(repo):
    a = repo.contato_de("telegram", "42")
    assert repo.contato_de("telegram", "42") == a
    assert repo.contato_de("telegram", "43") != a
    assert repo.contato_de("whatsapp", "42") != a, "o id externo não é PK entre canais"


def test_sessao_nasce_no_inicio(repo):
    estado, dados = repo.carregar_sessao(repo.contato_de("telegram", "1"))
    assert estado == "INICIO" and dados == {}


def test_sessao_sobrevive_ao_round_trip(repo):
    """Restart não pode perder conversa — o estado mora aqui, não no processo."""
    contato = repo.contato_de("telegram", "1")
    repo.salvar_sessao(contato, "CRIT_NIS", {"declarados": ["cadunico"], "n": 3})

    estado, dados = repo.carregar_sessao(contato)
    assert estado == "CRIT_NIS"
    assert dados == {"declarados": ["cadunico"], "n": 3}


def test_salvar_sessao_sobrescreve_e_nao_acumula(repo):
    contato = repo.contato_de("telegram", "1")
    repo.salvar_sessao(contato, "A", {"x": 1})
    repo.salvar_sessao(contato, "B", {"y": 2})
    assert repo.carregar_sessao(contato) == ("B", {"y": 2})


def test_consentimento_e_registrado_por_contato(repo):
    contato = repo.contato_de("telegram", "1")
    assert not repo.tem_consentimento(contato)

    repo.registrar_consentimento(contato, "inscricao/2026-08-30", "telegram", "1")
    assert repo.tem_consentimento(contato)
    assert not repo.tem_consentimento(repo.contato_de("telegram", "2"))


def test_id_externo_volta_para_o_envio_proativo(repo):
    """Sem isso a outbox não sabe para qual chat mandar."""
    contato = repo.contato_de("telegram", "777")
    repo.registrar_consentimento(contato, "inscricao/v1", "telegram", "777")
    assert repo.id_externo_de(contato) == "777"


def test_inscricao_e_recuperada_pelo_numero(repo):
    contato = repo.contato_de("telegram", "1")
    repo.salvar_inscricao(Inscricao(protocolo="2026-1", contato_id=contato,
                                    id_escola="edi", nome_escola="EDI Leila Diniz",
                                    nome_crianca="Ana Beatriz", etapa_codigo="recebida"))
    guardada = repo.inscricao("2026-1")
    assert guardada.nome_crianca == "Ana Beatriz"
    assert repo.inscricao("2026-nao-existe") is None


def test_atualizar_etapa_e_o_que_evita_notificar_duas_vezes(repo):
    contato = repo.contato_de("telegram", "1")
    repo.salvar_inscricao(Inscricao(protocolo="2026-1", contato_id=contato,
                                    id_escola="edi", nome_escola="EDI",
                                    nome_crianca="Ana", etapa_codigo="recebida"))
    repo.atualizar_etapa("2026-1", "convocada")
    assert repo.inscricao("2026-1").etapa_codigo == "convocada"


def test_outbox_entrega_uma_vez_so(repo):
    contato = repo.contato_de("telegram", "1")
    repo.salvar_inscricao(Inscricao(protocolo="2026-1", contato_id=contato,
                                    id_escola="edi", nome_escola="EDI",
                                    nome_crianca="Ana", etapa_codigo="recebida"))
    repo.enfileirar("2026-1", "convocacao", {"nome_crianca": "Ana"})

    pendentes = repo.pendentes()
    assert len(pendentes) == 1 and pendentes[0].variaveis == {"nome_crianca": "Ana"}

    repo.marcar_enviado(pendentes[0].id)
    assert repo.pendentes() == [], "marcado como enviado não pode voltar para a fila"


def test_falha_nao_perde_o_evento(repo):
    """Se o envio falhar, o evento fica na fila e NÃO é buscado de novo no backend."""
    contato = repo.contato_de("telegram", "1")
    repo.salvar_inscricao(Inscricao(protocolo="2026-1", contato_id=contato,
                                    id_escola="edi", nome_escola="EDI",
                                    nome_crianca="Ana", etapa_codigo="recebida"))
    repo.enfileirar("2026-1", "convocacao", {"nome_crianca": "Ana"})
    repo.marcar_falha(repo.pendentes()[0].id)
    assert repo.pendentes(), "falha não pode sumir com a mensagem"


def test_marca_dagua_persiste(repo):
    assert repo.ler_marca("backend") is None
    repo.gravar_marca("backend", "7")
    assert repo.ler_marca("backend") == "7"


def test_apagar_tudo_e_o_direito_de_eliminacao(repo):
    """LGPD art. 18. É o que o /apagar chama, e tem que levar tudo junto."""
    contato = repo.contato_de("telegram", "1")
    repo.registrar_consentimento(contato, "inscricao/v1", "telegram", "1")
    repo.salvar_sessao(contato, "CADASTRO", {"cpf_responsavel": "52998224725"})
    repo.salvar_inscricao(Inscricao(protocolo="2026-1", contato_id=contato,
                                    id_escola="edi", nome_escola="EDI",
                                    nome_crianca="Ana", etapa_codigo="recebida"))

    assert repo.apagar_tudo(contato) > 0
    assert not repo.tem_consentimento(contato)
    assert repo.carregar_sessao(contato) == ("INICIO", {})


def test_apagar_nao_atinge_quem_nao_pediu(repo):
    um, outro = repo.contato_de("telegram", "1"), repo.contato_de("telegram", "2")
    repo.registrar_consentimento(outro, "inscricao/v1", "telegram", "2")
    repo.salvar_sessao(outro, "CADASTRO", {"x": 1})

    repo.apagar_tudo(um)
    assert repo.tem_consentimento(outro)
    assert repo.carregar_sessao(outro)[0] == "CADASTRO"
