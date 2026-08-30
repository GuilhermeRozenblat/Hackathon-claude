"""As duas implementações de `Repositorio` têm que ser indistinguíveis.

O bot roda com Postgres em produção e com memória no `make memoria`. Se as duas
divergirem, um caminho passa aqui e quebra lá.

A fixture `repo` vem de `tests/conftest.py` e roda cada teste DUAS vezes: em memória e
no Postgres. Sem `DATABASE_URL_TESTE` a metade Postgres é pulada, e ninguém fica
bloqueado por banco fora do ar.
"""

from __future__ import annotations

import pytest

from creche_bot.dados.porta import Inscricao, Repositorio


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


# ---------------------------------------------------------------------------
# Armadilhas que só aparecem quando a implementação sai da memória. Cada uma
# destas custou um comentário em `dados/CLAUDE.md`; aqui elas viram teste.
# ---------------------------------------------------------------------------

MAX_TENTATIVAS = 5


def _com_inscricao(repo, protocolo="2026-1", nome="Ana Beatriz") -> str:
    contato = repo.contato_de("telegram", "1")
    repo.salvar_inscricao(Inscricao(protocolo=protocolo, contato_id=contato,
                                    id_escola="edi", nome_escola="EDI Leila Diniz",
                                    nome_crianca=nome, etapa_codigo="recebida"))
    return contato


def test_carregar_sessao_devolve_copia(repo):
    """O chamador muta o dict que recebe. Devolver a referência interna faria o estado
    mudar sem passar por salvar_sessao() — e o restart perderia a conversa."""
    contato = repo.contato_de("telegram", "1")
    repo.salvar_sessao(contato, "CRIT_NIS", {"declarados": ["cadunico"]})

    _, dados = repo.carregar_sessao(contato)
    dados["declarados"].append("intruso")
    dados["n"] = 99

    assert repo.carregar_sessao(contato)[1] == {"declarados": ["cadunico"]}


def test_id_externo_de_contato_desconhecido(repo):
    assert repo.id_externo_de("nao-existe") is None


def test_reregistrar_consentimento_nao_quebra(repo):
    """A família pode reiniciar o fluxo; a segunda passagem não pode estourar chave."""
    contato = repo.contato_de("telegram", "1")
    repo.registrar_consentimento(contato, "inscricao/v1", "telegram", "1")
    repo.registrar_consentimento(contato, "inscricao/v2", "telegram", "1")
    assert repo.tem_consentimento(contato)


def test_salvar_inscricao_duas_vezes_nao_duplica(repo):
    contato = _com_inscricao(repo)
    repo.salvar_inscricao(Inscricao(protocolo="2026-1", contato_id=contato,
                                    id_escola="outra", nome_escola="EDI Tim Lopes",
                                    nome_crianca="Ana Beatriz", etapa_codigo="recebida"))
    assert repo.inscricao("2026-1").nome_escola == "EDI Tim Lopes"


def test_atualizar_etapa_de_inscricao_desconhecida_nao_explode(repo):
    """O backend manda mudança de inscrição feita em outra instalação."""
    repo.atualizar_etapa("2026-nao-existe", "convocada")
    assert repo.inscricao("2026-nao-existe") is None


def test_pendentes_ignora_evento_sem_inscricao(repo):
    """Sem o contato_id da inscrição não há para quem entregar."""
    repo.enfileirar("2026-orfao", "convocacao", {})
    assert repo.pendentes() == []


def test_pendentes_respeita_a_ordem_de_chegada(repo):
    _com_inscricao(repo)
    for i in range(3):
        repo.enfileirar("2026-1", "convocacao", {"ordem": i})

    eventos = repo.pendentes()
    assert [e.variaveis["ordem"] for e in eventos] == [0, 1, 2]


def test_pendentes_respeita_o_limite(repo):
    _com_inscricao(repo)
    for i in range(5):
        repo.enfileirar("2026-1", "convocacao", {"ordem": i})
    assert len(repo.pendentes(limite=2)) == 2


def test_falha_para_de_insistir_no_teto(repo):
    """Falhou, tenta de novo — mas depois de N falhas para de girar."""
    _com_inscricao(repo)
    repo.enfileirar("2026-1", "convocacao", {})

    for _ in range(MAX_TENTATIVAS - 1):
        evento_id = repo.pendentes()[0].id
        repo.marcar_falha(evento_id)
        assert repo.pendentes(), "evento sumiu antes do teto de tentativas"

    repo.marcar_falha(evento_id)
    assert repo.pendentes() == []


def test_variaveis_com_acento_e_aninhamento(repo):
    """jsonb ida e volta: acento corrompido vira nome de criança errado no chat."""
    _com_inscricao(repo)
    variaveis = {"nome_crianca": "João", "pendencias": ["certidão", "comprovante"],
                 "endereco": {"rua": "R. das Acácias", "n": 240}, "prazo": None}
    repo.enfileirar("2026-1", "convocacao", variaveis)
    assert repo.pendentes()[0].variaveis == variaveis


def test_apagar_tudo_nao_deixa_orfao_na_outbox(repo):
    """A outbox não tem FK para contato. Sobrar linha ali é nome de criança guardado
    depois que a família pediu para sumir — LGPD art. 18."""
    contato = _com_inscricao(repo)
    repo.enfileirar("2026-1", "convocacao", {"nome_crianca": "Ana Beatriz"})

    repo.apagar_tudo(contato)

    # Recria o mesmo protocolo para outro contato: se o evento antigo ressuscitar,
    # ele seria entregue para a pessoa errada.
    repo.salvar_inscricao(Inscricao(protocolo="2026-1",
                                    contato_id=repo.contato_de("telegram", "2"),
                                    id_escola="edi", nome_escola="EDI Leila Diniz",
                                    nome_crianca="Outra Criança", etapa_codigo="recebida"))
    assert repo.pendentes() == [], "evento do contato apagado ressuscitou"


# ------------------------------------------------------- postura do schema
# Não dependem de banco: leem o DDL e a montagem da conexão.


def test_esquema_fica_fora_do_schema_public():
    """No `public` as tabelas ficam ao alcance da Data API do Supabase, que responde a
    quem tem a chave anônima — e elas guardam nome de criança e CPF."""
    from creche_bot.dados import postgres

    assert "CREATE SCHEMA IF NOT EXISTS {s}" in postgres.ESQUEMA
    assert "public." not in postgres.ESQUEMA
    assert "ENABLE ROW LEVEL SECURITY" in postgres.ESQUEMA


def test_conexao_exige_tls():
    """CPF e nome de criança não atravessam a internet em texto claro."""
    from creche_bot.dados.postgres import _com_tls

    assert _com_tls("postgresql://u:p@host/db").endswith("?sslmode=require")
    assert _com_tls("postgresql://u:p@host/db?a=1").endswith("&sslmode=require")
    assert _com_tls("postgresql://u:p@h/db?sslmode=verify-full").count("sslmode") == 1


def test_schema_invalido_nao_vira_sql():
    """O nome do schema é concatenado na query; identificador é a única forma aceita."""
    from creche_bot.dados.postgres import RepositorioPostgres

    with pytest.raises(AssertionError, match="schema inválido"):
        RepositorioPostgres("postgresql://x/y", schema="creche; DROP SCHEMA creche")
