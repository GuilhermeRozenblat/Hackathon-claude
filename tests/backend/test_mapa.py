"""`BackendMapa` sobre os CSVs reais de `MapaFilaCreche/`.

Sem rede e sem banco: os dados viajam com o pacote. O que estes testes protegem é a
fronteira entre o CSV bruto e o que a família lê — a conta da chance, os limites dela, e o
fato de que nenhum número sai daqui sem o ano colado.
"""

from __future__ import annotations

import pytest

from creche_bot.backend.mapa import (
    ANO_BASE,
    CHANCE_MAX,
    CHANCE_MIN,
    BackendMapa,
    _Unidade,
    _unidades,
    bairro_legivel,
    chance_em,
    km_entre,
)
from creche_bot.backend.porta import BackendCreche
from creche_bot.dominio.tipos import Endereco

CURICICA = Endereco(cep="22710560", numero="100", logradouro="Rua Franz Weissmann",
                    bairro="Curicica", lat=-22.9601, lng=-43.4048)
CATETE = Endereco(cep="20220030", numero="50", logradouro="Rua do Catete",
                  bairro="Catete", lat=-22.9262, lng=-43.1776)


@pytest.fixture(scope="module")
def backend() -> BackendMapa:
    return BackendMapa()


def unidade(demanda: int, confirmados: int) -> _Unidade:
    return _Unidade(desig7="0000001", nome="CRECHE X", tipo="Creche", microarea="7.9",
                    bairro="Curicica", rua="Rua X", lat=-22.9, lon=-43.4,
                    demanda_1a=demanda, confirmados=confirmados, ociosas=0)


def test_honra_o_contrato_do_backend(backend):
    assert isinstance(backend, BackendCreche)


def test_carrega_as_unidades_do_mapa():
    """820 é a contagem do LEIAME: unidades com demanda de creche em 2025."""
    assert len(_unidades()) == 820
    assert all(u.lat and u.lon for u in _unidades())


# ------------------------------------------------------------------- a chance
def test_chance_e_a_fracao_atendida_no_ano_base():
    assert chance_em(unidade(demanda=100, confirmados=25), False) == pytest.approx(0.25)


def test_chance_nunca_e_zero_nem_um():
    """Vaga ociosa hoje não garante vaga em fevereiro, e fila cheia no ano passado não
    fecha a porta deste ano. Os dois extremos seriam promessa, em direções opostas."""
    assert chance_em(unidade(demanda=1000, confirmados=0), False) == CHANCE_MIN
    assert chance_em(unidade(demanda=10, confirmados=500), False) == CHANCE_MAX


def test_sem_demanda_no_ano_base_nao_ha_chance():
    """Creche que ninguém pediu não vale 0% — vale "não dá para estimar"."""
    assert chance_em(unidade(demanda=0, confirmados=0), False) is None


def test_vaga_aberta_agora_levanta_o_piso():
    """Fato do presente vale mais que a média do ano passado, e mesmo assim não vira 100%."""
    sem_vaga = chance_em(unidade(demanda=100, confirmados=5), False)
    com_vaga = chance_em(unidade(demanda=100, confirmados=5), True)
    assert com_vaga > sem_vaga
    assert com_vaga <= CHANCE_MAX


# -------------------------------------------------------------- escolas perto
def test_escolas_vem_ordenadas_por_distancia(backend):
    sugestoes = backend.escolas_proximas(CURICICA, "maternal_2", "integral", n=3)
    assert len(sugestoes) == 3
    assert [v.distancia_km for v in sugestoes] == sorted(v.distancia_km for v in sugestoes)


def test_cep_diferente_devolve_creche_diferente(backend):
    """O CEP é o que particiona a oferta. Se Curicica e Catete devolvessem a mesma lista,
    a distância na tela seria decoração."""
    perto_de_casa = {v.id_escola for v in
                     backend.escolas_proximas(CURICICA, "maternal_2", "integral")}
    do_outro_lado = {v.id_escola for v in
                     backend.escolas_proximas(CATETE, "maternal_2", "integral")}
    assert not (perto_de_casa & do_outro_lado)


def test_todo_numero_sai_com_o_ano(backend):
    """A regra que impede estimativa de virar previsão: sem ano, "33%" vira promessa
    sobre o processo de agora."""
    for v in backend.escolas_proximas(CURICICA, "bercario", "integral"):
        if v.concorrencia is not None:
            assert v.concorrencia.ano == ANO_BASE


def test_vaga_ociosa_e_por_grupamento(backend):
    """Creche com sobra no Maternal II e fila no Berçário é o caso comum — uma flag por
    unidade mandaria a família pedir a turma errada."""
    por_id = {}
    for grupamento in ("bercario", "maternal_1", "maternal_2"):
        for v in backend.escolas_proximas(CATETE, grupamento, "integral", n=8):
            por_id.setdefault(v.id_escola, set()).add(v.vaga_ociosa)
    assert any(len(valores) > 1 for valores in por_id.values()), \
        "nenhuma unidade divergiu entre grupamentos — o filtro por grupamento sumiu"


# ------------------------------------------------------------- região e texto
def test_panorama_da_regiao_acha_a_microarea_certa(backend):
    """A vizinha única erra na divisa: em Curicica ela devolvia Camorim."""
    panorama = backend.panorama_da_regiao(CURICICA)
    assert panorama is not None
    assert panorama.bairro == "Curicica"
    assert panorama.ano == ANO_BASE
    assert panorama.demanda > 0


def test_bairro_sai_legivel():
    assert bairro_legivel("Camorim- Jacarepaguá") == "Camorim / Jacarepaguá"
    assert bairro_legivel("Curicica") == "Curicica"


def test_nome_real_da_escola_chega_na_inscricao(backend):
    """`BackendMock.inscrever` não conhece os ids do mapa e gravava "creche" — que era o
    que a família lia no /status."""
    sugestoes = backend.escolas_proximas(CURICICA, "maternal_2", "integral")
    numero = backend.inscrever({"nome_crianca": "Ana"}, [sugestoes[0].id_escola])
    assert backend.situacao(numero).nome_escola == sugestoes[0].nome


def test_km_entre_bate_com_a_distancia_conhecida():
    """Curicica -> Catete são ~22 km em linha reta."""
    assert km_entre(-22.9601, -43.4048, -22.9262, -43.1776) == pytest.approx(23.6, abs=1.0)
