"""O mock é o espelho do contrato: o BackendHTTP terá que passar nesta mesma bateria.

Nenhum dado aqui é real — saíram do roteiro v2. Os percentuais nos comentários vêm da
base histórica de 2021 a 2025.
"""

from __future__ import annotations

import io
import json
from datetime import date, timedelta

import pytest

from creche_bot.backend.mock import CPF_CONHECIDO, NUMERO_CONHECIDO, BackendMock
from creche_bot.backend.porta import BackendCreche


@pytest.fixture
def b():
    return BackendMock()


def test_implementa_a_porta(b):
    assert isinstance(b, BackendCreche)


# ------------------------------------------------------------------- processo
def test_periodo_aberto_contem_hoje(b):
    abertura, fechamento = b.periodo_de_inscricao()
    assert abertura <= date.today() <= fechamento


def test_periodo_fechado_esta_no_passado():
    _, fechamento = BackendMock(processo_aberto=False).periodo_de_inscricao()
    assert fechamento < date.today()


def test_data_de_corte_vem_depois_do_fechamento(b):
    assert b.data_de_corte() > b.periodo_de_inscricao()[1]


def test_regua_vem_ordenada_por_grupo(b):
    grupos = [c.grupo for c in b.criterios_do_processo()]
    assert grupos == sorted(grupos), "a ordem da régua é do processo, não do bot"


def test_cadunico_pesa_mais_que_todo_o_resto_somado(b):
    """48,9% declaram CadÚnico e só 6,8% comprovam: é a razão de existir do projeto."""
    criterios = {c.codigo: c.pontos for c in b.criterios_do_processo()}
    assert criterios["cadunico"] > sum(v for k, v in criterios.items() if k != "cadunico")


# ------------------------------------------------------------------ histórico
def test_busca_por_responsavel_precisa_do_cpf_certo(b):
    assert b.buscar_por_responsavel(CPF_CONHECIDO) is not None
    assert b.buscar_por_responsavel("111.444.777-35") is None
    assert b.buscar_por_responsavel("") is None


def test_cadastro_anterior_traz_a_fila_ja_comprovada(b):
    """A fonte é o próprio banco: sai validado de graça."""
    cadastro = b.buscar_por_responsavel(CPF_CONHECIDO)
    assert cadastro.esperou_na_fila is True
    assert cadastro.criancas and cadastro.endereco is not None


# ------------------------------------------------------------------- endereço
def test_cep_resolve_com_coordenadas(b):
    e = b.resolver_cep("22710-560", "100")
    assert (e.bairro, e.numero) == ("Curicica", "100")
    assert e.lat and e.lng, "sem coordenadas não dá para medir distância"
    assert str(e) == "Rua Franz Weissmann, 100 — Curicica"


def test_cep_desconhecido_nao_inventa(b):
    assert b.resolver_cep("00000-000", "1") is None


def test_cep_fora_do_roteiro_vem_da_consulta_externa(b, monkeypatch):
    """Fora dos três CEPs do roteiro o mock pergunta para a BrasilAPI. Sem isso a conversa
    trava no bloco 6 para todo mundo que digita o CEP de casa."""
    from creche_bot.backend import mock

    resposta = json.dumps({"street": "Rua Santa Clara", "neighborhood": "Copacabana",
                           "location": {"coordinates": {"latitude": "-22.9721912",
                                                        "longitude": "-43.1865895"}}})
    mock._buscar_cep.cache_clear()
    monkeypatch.setattr(mock.urllib.request, "urlopen",
                        lambda *a, **k: io.StringIO(resposta))
    e = b.resolver_cep("22041-011", "45")
    assert str(e) == "Rua Santa Clara, 45 — Copacabana"
    assert (e.lat, e.lng) == (-22.9721912, -43.1865895)
    mock._buscar_cep.cache_clear()


def test_cep_sem_rede_nao_inventa_endereco(b, monkeypatch):
    from creche_bot.backend import mock

    def cai(*a, **k):
        raise OSError("sem rede")

    mock._buscar_cep.cache_clear()
    monkeypatch.setattr(mock.urllib.request, "urlopen", cai)
    assert b.resolver_cep("22041-011", "45") is None
    mock._buscar_cep.cache_clear()


# ---------------------------------------------------------------------- oferta
def test_oferta_filtra_por_grupamento_e_horario(b):
    endereco = b.resolver_cep("22710-560", "100")
    parcial = b.escolas_proximas(endereco, "maternal_1", "parcial")
    assert parcial, "há oferta parcial: 6,2% do Berçário e 12,5% do Maternal II"
    assert all(v.horario == "parcial" for v in parcial)

    integral = b.escolas_proximas(endereco, "maternal_1", "integral")
    assert len(integral) > len(parcial), "o horário particiona a oferta de verdade"


def test_vaga_aberta_agora_vem_primeiro(b):
    endereco = b.resolver_cep("22710-560", "100")
    vagas = b.escolas_proximas(endereco, "bercario", "integral")
    assert vagas[0].vaga_ociosa
    assert vagas == sorted(vagas, key=lambda v: (not v.vaga_ociosa, v.distancia_km))


def test_concorrencia_sempre_tem_ano(b):
    """Sem o ano, número histórico vira previsão."""
    endereco = b.resolver_cep("22710-560", "100")
    for vaga in b.escolas_proximas(endereco, "bercario", "integral"):
        assert vaga.concorrencia is None or vaga.concorrencia.ano


def test_vaga_nao_carrega_nota_de_corte(b):
    """A classificação só roda depois do fechamento: no painel ela não existe."""
    endereco = b.resolver_cep("22710-560", "100")
    vaga = b.escolas_proximas(endereco, "bercario", "integral")[0]
    assert not hasattr(vaga, "nota_corte")
    assert not hasattr(vaga, "pontos")


def test_minutos_a_pe_sai_da_distancia(b):
    endereco = b.resolver_cep("22710-560", "100")
    vaga = b.escolas_proximas(endereco, "bercario", "integral")[0]
    assert 1 <= vaga.minutos_a_pe <= 10


# ------------------------------------------------------------------ inscrição
def test_nis_valido_comprova_as_duas_perguntas(b):
    valido, comprova = b.validar_nis("12345678901")
    assert valido and set(comprova) == {"cadunico", "bolsa_familia"}


def test_nis_curto_nao_comprova_nada(b):
    assert b.validar_nis("123") == (False, ())


def test_inscrever_honra_a_chave_de_idempotencia(b):
    """Duas inscrições para a mesma criança se anulam."""
    primeiro = b.inscrever({"chave_idempotencia": "abc"}, ["edi-leila-diniz"])
    assert b.inscrever({"chave_idempotencia": "abc"}, ["edi-leila-diniz"]) == primeiro
    assert b.inscrever({"chave_idempotencia": "xyz"}, ["edi-leila-diniz"]) != primeiro


def test_documento_ilegivel_nao_inventa_dado(b):
    lido = b.enviar_documento("2026-1", "educacao_especial", b"x" * 10, "image/jpeg")
    assert lido.confianca == "baixa"
    assert lido.nis is None and lido.nome is None


def test_comprovante_de_nis_devolve_o_numero(b):
    lido = b.enviar_documento("2026-1", "cadunico", b"x" * 5000, "image/jpeg")
    assert lido.confianca == "alta" and lido.nis


def test_pontos_de_entrega_muda_com_a_forma(b):
    creche = b.pontos_de_entrega("creche", "edi-leila-diniz", "22710560")
    cras = b.pontos_de_entrega("cras", "edi-leila-diniz", "22710560")
    assert creche[0].nome == "EDI Leila Diniz"
    assert len(cras) > 1 and all("CRAS" in p.nome for p in cras)
    assert all(p.horario for p in cras), "sem horário a família bate na porta fechada"


# -------------------------------------------------------------------- consulta
def test_consulta_por_numero_exige_o_nascimento_certo(b):
    assert b.consultar_por_numero(NUMERO_CONHECIDO, date(2024, 1, 10))
    assert not b.consultar_por_numero(NUMERO_CONHECIDO, date(2020, 1, 1))


def test_consulta_por_nome_e_o_segundo_caminho_do_portal(b):
    achados = b.consultar_por_nome("Lucas Andrade", date(2023, 7, 2), "")
    assert achados and achados[0].numero == "2026-0847231"


def test_os_sete_estados_existem_no_mock(b):
    from typing import get_args

    from creche_bot.dominio.tipos import EstadoInscricao

    estados = {d.estado for d in b.consultar_por_responsavel(CPF_CONHECIDO)}
    todos = {d.estado for d in
             [x for n in ("2026-0847220", "2026-0847231", "2026-0847244", "2026-0847255",
                          "2026-0847266", "2026-0847277")
              for x in b.consultar_por_numero(n, _nascimento(b, n))]} | estados
    assert todos == set(get_args(EstadoInscricao)), "toda tela do C.3 precisa de dado"


def _nascimento(b, numero):
    from creche_bot.backend.mock import _DESFECHOS

    return next(d.data_nascimento for d in _DESFECHOS if d.numero == numero)


def test_inscricao_recem_feita_e_consultavel(b):
    """Quem acabou de se inscrever pelo bot é justamente quem mais volta para conferir."""
    numero = b.inscrever({"nome_crianca": "Ana Beatriz da Silva",
                          "nascimento_crianca": "2024-01-10"}, ["edi-leila-diniz"])
    achados = b.consultar_por_numero(numero, date(2024, 1, 10))
    assert achados and achados[0].estado == "ativa"


# --------------------------------------------------------------- notificações
def test_avancar_percorre_o_roteiro_ate_o_fim(b):
    numero = b.inscrever({"nome_crianca": "Ana"}, ["edi-leila-diniz"])
    tipos = []
    for _ in range(5):
        tipos.append(b.avancar(numero).etapa.tipo)
    assert "acao_no_chat" in tipos and "convocacao" in tipos
    assert tipos[-1] == "concluida"


def test_convocacao_sempre_tem_prazo_no_futuro(b):
    numero = b.inscrever({"nome_crianca": "Ana"}, ["edi-leila-diniz"])
    for _ in range(3):
        situacao = b.avancar(numero)
    assert situacao.etapa.tipo == "convocacao"
    assert situacao.etapa.prazo > date.today() - timedelta(days=1)


def test_marca_dagua_nao_reentrega(b):
    b.inscrever({"nome_crianca": "Ana"}, ["edi-leila-diniz"])
    mudancas, marca = b.mudancas_desde(None)
    assert len(mudancas) == 1
    assert b.mudancas_desde(marca)[0] == []
