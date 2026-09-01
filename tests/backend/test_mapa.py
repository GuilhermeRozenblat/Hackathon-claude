"""`BackendMapa` sobre os CSVs reais de `MapaFilaCreche/`.

Sem rede e sem banco: os dados viajam com o pacote. O que estes testes protegem é a
fronteira entre o CSV bruto e o que a família lê: a conta da chance, os limites dela, e o
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
    candidatos_por_vaga,
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
                    demanda_1a=demanda, confirmados=confirmados)


def test_honra_o_contrato_do_backend(backend):
    assert isinstance(backend, BackendCreche)


def test_carrega_as_unidades_do_mapa():
    """820 é a contagem do LEIAME: unidades com demanda de creche em 2025."""
    assert len(_unidades()) == 820
    assert all(u.lat and u.lon for u in _unidades())


# ------------------------------------------------------------------- a chance
def test_chance_e_a_fracao_atendida_no_ano_base():
    assert chance_em(unidade(demanda=100, confirmados=25)) == pytest.approx(0.25)


def test_chance_nunca_e_zero_nem_um():
    """Vaga ociosa hoje não garante vaga em fevereiro, e fila cheia no ano passado não
    fecha a porta deste ano. Os dois extremos seriam promessa, em direções opostas."""
    assert chance_em(unidade(demanda=1000, confirmados=0)) == CHANCE_MIN
    assert chance_em(unidade(demanda=10, confirmados=10)) == CHANCE_MAX


def test_sem_demanda_no_ano_base_nao_ha_chance():
    """Creche que ninguém pediu não vale 0%, e sim "não dá para estimar"."""
    assert chance_em(unidade(demanda=0, confirmados=0)) is None


def test_vaga_ociosa_nao_entra_na_estimativa():
    """A chance é `confirmados ÷ demanda`, e só. Um piso por vaga aberta fazia uma
    unidade de razão real 14% sair como "chance estimada 80% (base 2025)": número que
    não é a fórmula, não tem ano próprio, e ainda suprimia a linha de concorrência que o
    contradizia. Vaga aberta agora continua na tela pelo 🟢, por conta própria."""
    assert chance_em(unidade(demanda=100, confirmados=5)) == pytest.approx(0.05)


def test_confirmados_de_outras_opcoes_nao_viram_chance():
    """`cf` soma quem entrou por 2ª/3ª opção: 214 das 820 unidades reais têm
    confirmados > demanda_1a (ex.: CM BETINHO, d1=3 cf=5). A razão deixa de ser "quem
    pediu aqui e conseguiu", então não sai número nenhum — a mesma guarda de
    `candidatos_por_vaga`. Antes, o teto travava em 95% e a tela lia quase-certeza."""
    assert chance_em(unidade(demanda=3, confirmados=5)) is None


# ------------------------------------------------------------- famílias por vaga
def test_candidatos_por_vaga_e_a_demanda_sobre_os_confirmados():
    concorrencia = candidatos_por_vaga(unidade(demanda=100, confirmados=25))
    assert concorrencia.familias_por_vaga == pytest.approx(4)
    assert concorrencia.ano == ANO_BASE


def test_confirmados_maior_que_demanda_nao_vira_menos_de_uma_familia_por_vaga():
    """CM BETINHO real: d1=3, cf=5 (recebeu quem pediu como 2ª/3ª opção). `3/5 = 0,6`
    "famílias por vaga" não existe: vira `None`, não um número menor que 1."""
    assert candidatos_por_vaga(unidade(demanda=3, confirmados=5)) is None


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
    """Creche com sobra no Maternal II e fila no Berçário é o caso comum, e uma flag por
    unidade mandaria a família pedir a turma errada."""
    por_id = {}
    for grupamento in ("bercario", "maternal_1", "maternal_2"):
        for v in backend.escolas_proximas(CATETE, grupamento, "integral", n=8):
            por_id.setdefault(v.id_escola, set()).add(v.vaga_ociosa)
    assert any(len(valores) > 1 for valores in por_id.values()), \
        "nenhuma unidade divergiu entre grupamentos, o filtro por grupamento sumiu"


# ------------------------------------------------------------- região e texto
def test_panorama_da_regiao_acha_a_microarea_certa(backend):
    """A vizinha única erra na divisa: em Curicica ela devolvia Camorim."""
    panorama = backend.panorama_da_regiao(CURICICA)
    assert panorama is not None
    assert panorama.bairro == "Curicica"
    assert panorama.ano == ANO_BASE
    assert panorama.demanda > 0


def test_atendidos_da_regiao_nunca_passa_da_demanda(backend):
    """13 das 232 microáreas têm `conf` > `demanda` no CSV bruto: a microárea 7.8
    (Jacarepaguá/Taquara) é `demanda=320 conf=349`. Sem o teto, "achei_creches" diria
    que mais famílias conseguiram vaga do que pediram, contradizendo o próprio texto.
    A coordenada é de uma das 5 unidades da 7.8, para o voto de vizinhas cair nela."""
    jacarepagua = Endereco(cep="22753130", numero="10", logradouro="teste",
                           bairro="Jacarepaguá", lat=-22.93863, lng=-43.39598)
    panorama = backend.panorama_da_regiao(jacarepagua)
    assert panorama is not None
    assert panorama.microarea == "7.8"
    assert panorama.demanda == 320
    assert panorama.atendidos == 320   # 349 no CSV bruto, travado em 320 pelo clamp


def test_bairro_sai_legivel():
    assert bairro_legivel("Camorim- Jacarepaguá") == "Camorim / Jacarepaguá"
    assert bairro_legivel("Curicica") == "Curicica"


def test_nome_real_da_escola_chega_na_inscricao(backend):
    """`BackendMock.inscrever` não conhece os ids do mapa e gravava "creche", que era o
    que a família lia no /status."""
    sugestoes = backend.escolas_proximas(CURICICA, "maternal_2", "integral")
    numero = backend.inscrever({"nome_crianca": "Ana"}, [sugestoes[0].id_escola])
    assert backend.situacao(numero).nome_escola == sugestoes[0].nome


def test_km_entre_bate_com_a_distancia_conhecida():
    """Curicica -> Catete são ~22 km em linha reta."""
    assert km_entre(-22.9601, -43.4048, -22.9262, -43.1776) == pytest.approx(23.6, abs=1.0)
