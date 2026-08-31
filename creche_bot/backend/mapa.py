"""Backend sobre os dados reais da fila de creche do Rio, de `MapaFilaCreche/`.

Substitui a oferta inventada do `BackendMock` pelas **820 unidades de creche com demanda
em 2025**, geocodificadas e alocadas a microárea por point-in-polygon no shapefile do IPP.
O CEP da família vira coordenada, e a coordenada vira a lista de creches mais próximas,
com distância real, vaga ociosa por grupamento e a chance estimada em cada uma.

## O que é real aqui e o que ainda não é

Real: unidade, endereço, coordenada, microárea, demanda de 1ª opção, confirmados, vagas
ociosas por grupamento, e as métricas de região. Tudo de `MapaFilaCreche/`, recorte de
2025.

Ainda do mock, por herança: régua do processo, histórico do responsável, extração de
documento e situação da inscrição. Nada disso está nos CSVs, e inventar seria pior que
herdar: quando o `BackendHTTP` do município subir, ele substitui as duas metades de uma
vez. Herdar de `BackendMock` é o que deixa isso explícito em vez de espalhado.

## A conta da chance, e o que ela não é

`chance = confirmados ÷ demanda_de_1ª_opção`, na própria unidade, em 2025. É uma
aproximação da fração de quem pediu aquela creche como primeira opção e acabou atendido.
não é exata porque `confirmados` (`cf`) conta toda matrícula efetivada na unidade, **não
só quem a pediu em 1ª opção**: em 214 das 820 unidades (26%) esse número é maior que
`demanda_1a`, porque a unidade também recebeu quem a pediu como 2ª ou 3ª opção e foi
realocado para lá. Nessas unidades a fração passa de 100%, e em uma chega a 364%. O
teto abaixo é o que impede isso de aparecer na tela como número.

O que ela **não** é: a classificação. Essa é norma (Resolução SME nº 542/2025), roda em
SQL determinístico depois do fechamento das inscrições, e não existe no momento da
conversa. Pontuação de prioridade, critério de desempate e ordem de convocação não entram
nesta conta: duas famílias com a mesma chance na tela podem ter desfechos opostos por
causa da régua. Quem renderiza é obrigado a dizer que é estimativa e de que ano.

Os limites são deliberados: nunca 0% e nunca 100%. Vaga ociosa hoje não garante vaga em
fevereiro, e fila cheia no ano passado não fecha a porta deste ano. É também a rede de
segurança para as 214 unidades acima: sem o teto, uma "chance" de 364% chegaria a sair
daqui.
"""

from __future__ import annotations

import csv
import logging
from collections import Counter
from dataclasses import dataclass, replace
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

from creche_bot.backend.mock import BackendMock
from creche_bot.dominio.tipos import (
    Concorrencia,
    Endereco,
    Grupamento,
    Horario,
    PanoramaRegiao,
    VagaSugerida,
)

log = logging.getLogger(__name__)

DADOS = Path(__file__).resolve().parent.parent / "MapaFilaCreche"

# O recorte da base. Vai junto em todo número que sai daqui: sem o ano, "5 famílias por
# vaga" vira promessa sobre o processo de agora.
ANO_BASE = 2025

# O vocabulário interno da rede, como aparece na coluna `grupamento` de
# `vagas_ociosas_geo.csv`. A família nunca vê nenhum dos dois lados.
_GRUPAMENTO_CSV: dict[Grupamento, str] = {
    "bercario": "Berçário",
    "maternal_1": "Maternal I",
    "maternal_2": "Maternal II",
}

# Começa no raio que as famílias aceitam de fato, já que 82,9% dos que trocaram de creche
# andaram até 2 km, e só abre a mão se não houver nada ali. Parar em 2 km numa região
# vazia devolveria lista em branco para quem tem creche a 2,3 km.
RAIOS_KM = (2.0, 3.5, 5.0)

# Chance nunca é 0 nem 1. Vaga ociosa hoje não garante vaga em fevereiro, e fila cheia no
# ano passado não fecha a porta deste ano.
CHANCE_MIN = 0.03
CHANCE_MAX = 0.95

# Vaga aberta agora no grupamento certo é fato do presente, e vale mais que a média do ano
# passado: o piso reconhece isso sem prometer o teto.
CHANCE_COM_VAGA_OCIOSA = 0.80

# Quantas creches vizinhas votam na microárea da família. Uma só erra na divisa.
VIZINHAS_DA_REGIAO = 7


@dataclass(frozen=True)
class _Unidade:
    desig7: str
    nome: str
    tipo: str
    microarea: str
    bairro: str
    rua: str
    lat: float
    lon: float
    demanda_1a: int      # inscritos que pediram esta unidade como 1ª opção em 2025
    confirmados: int     # os que foram atendidos nela


def _num(valor: str, padrao: float = 0.0) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return padrao


def bairro_legivel(bruto: str) -> str:
    """"Camorim- Jacarepaguá" -> "Camorim / Jacarepaguá".

    A base traz o separador de bairro em três grafias (`-`, `- `, ` / `), e a família lê
    isso na tela. Normalizar na fronteira é mais barato que ensinar cada tela a formatar.
    """
    partes = [p.strip() for p in bruto.replace("/", "-").split("-") if p.strip()]
    return " / ".join(partes)


def _linhas(arquivo: str) -> list[dict[str, str]]:
    """Lê um CSV do pacote. `csv` e não `split(",")`: há nome de creche com vírgula
    dentro de aspas, e a versão ingênua parte a linha no lugar errado."""
    caminho = DADOS / arquivo
    with caminho.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def km_entre(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine, em quilômetros. Distância em linha reta, não a pé, e é assim que a
    tela apresenta: "uns X min a pé" já é aproximação declarada."""
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = (sin(dlat / 2) ** 2
         + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2)
    return 2 * 6371.0 * asin(sqrt(a))


@lru_cache(maxsize=1)
def _unidades() -> tuple[_Unidade, ...]:
    """As 820 unidades do mapa, já com a rua vinda do catálogo por CRE.

    `mapa_unidades.csv` tem a demanda e as coordenadas mas não o logradouro;
    `unidades_por_cre.csv` tem o logradouro. `desig7` casa os dois.
    """
    ruas = {linha["desig7"]: linha["rua"] for linha in _linhas("unidades_por_cre.csv")}

    unidades = []
    for linha in _linhas("mapa_unidades.csv"):
        lat, lon = _num(linha["lat"]), _num(linha["lon"])
        if not (lat and lon):
            continue        # sem coordenada não há distância, e distância é o eixo da tela
        desig7 = linha["desig7"]
        unidades.append(_Unidade(
            desig7=desig7, nome=linha["nm"], tipo=linha["Tipo"], microarea=linha["micro"],
            bairro=bairro_legivel(linha["bairro"]), rua=ruas.get(desig7, ""), lat=lat, lon=lon,
            demanda_1a=int(_num(linha["d1"])), confirmados=int(_num(linha["cf"]))))
    log.info("mapa da fila carregado: %d unidades", len(unidades))
    return tuple(unidades)


@lru_cache(maxsize=1)
def _ociosas_por_unidade() -> dict[str, dict[str, int]]:
    """{desig7: {"Berçário": 3, ...}}. Vaga ociosa é por GRUPAMENTO, não por unidade:
    creche com sobra no Maternal II e fila no Berçário é o caso comum."""
    saida: dict[str, dict[str, int]] = {}
    for linha in _linhas("vagas_ociosas_geo.csv"):
        vagas = int(_num(linha["vagas"]))
        if vagas > 0:
            saida.setdefault(linha["desig7"], {})[linha["grupamento"]] = vagas
    return saida


@lru_cache(maxsize=1)
def _microareas() -> dict[str, dict[str, str]]:
    return {linha["cod"]: linha for linha in _linhas("mapa_microareas.csv")}


def chance_em(unidade: _Unidade, tem_vaga_ociosa: bool) -> float | None:
    """Aproximação da fração de quem pediu esta creche como 1ª opção em 2025 e foi
    atendido, aproximação porque `confirmados` também soma quem entrou por 2ª ou 3ª
    opção, então a razão passa de 100% em ~1 a cada 4 unidades. É por isso que o
    resultado é sempre travado abaixo do teto: o número cru não é confiável acima dele.

    `None` quando a unidade não teve demanda no ano-base: sem denominador não há
    estimativa, e 0% seria mentira sobre uma creche que simplesmente não foi disputada.
    """
    if unidade.demanda_1a <= 0:
        return None
    bruta = unidade.confirmados / unidade.demanda_1a
    if tem_vaga_ociosa:
        bruta = max(bruta, CHANCE_COM_VAGA_OCIOSA)
    return min(CHANCE_MAX, max(CHANCE_MIN, bruta))


def candidatos_por_vaga(unidade: _Unidade) -> Concorrencia | None:
    """Quantas famílias disputaram cada vaga preenchida em 2025. Fato consumado.

    `None` também quando `confirmados` supera `demanda_1a`: a unidade recebeu criança
    que pediu outra creche em 1º lugar e foi realocada para cá, e "famílias por vaga"
    daria menos de 1, o que não existe. Sem essa guarda o número vazava até a tela via
    `escolas.py` (que só o esconde acima de 1,5) e sempre até o banco via `projecao.py`,
    que grava `familias_por_vaga` sem esse filtro.
    """
    if unidade.demanda_1a <= 0 or unidade.confirmados <= 0:
        return None
    if unidade.confirmados > unidade.demanda_1a:
        return None
    return Concorrencia(unidade.demanda_1a / unidade.confirmados, ANO_BASE)


class BackendMapa(BackendMock):
    """A oferta vem dos CSVs; o resto ainda é o mock. Ver o cabeçalho do módulo."""

    def escolas_proximas(self, endereco: Endereco, grupamento: Grupamento,
                         horario: Horario, n: int = 3) -> list[VagaSugerida]:
        """As `n` creches mais próximas do endereço, com chance estimada em cada uma.

        Não filtra por horário: `MapaFilaCreche/` não traz turno por unidade, e inventar
        esse recorte esconderia da família creche que ela poderia pedir. O horário
        continua indo na inscrição, que é onde ele é decidido de verdade.
        """
        alvo = _GRUPAMENTO_CSV.get(grupamento)
        if alvo is None:                 # fora_da_faixa não chega aqui pelo roteiro
            return []

        ociosas = _ociosas_por_unidade()
        perto: list[tuple[float, _Unidade]] = []
        for raio in RAIOS_KM:
            perto = [(km, u) for u in _unidades()
                     if (km := km_entre(endereco.lat, endereco.lng, u.lat, u.lon)) <= raio]
            if len(perto) >= n:
                break

        perto.sort(key=lambda par: par[0])
        sugestoes = []
        for km, u in perto[:n]:
            tem_vaga = ociosas.get(u.desig7, {}).get(alvo, 0) > 0
            sugestoes.append(VagaSugerida(
                id_escola=u.desig7, nome=u.nome,
                endereco=u.rua or f"{u.bairro}, {u.tipo}",
                lat=u.lat, lng=u.lon, grupamento=grupamento, horario=horario,
                distancia_km=round(km, 2), vaga_ociosa=tem_vaga,
                concorrencia=candidatos_por_vaga(u),
                chance=chance_em(u, tem_vaga),
                referencia=u.bairro, polo=u.microarea,
                horario_atendimento="Confirme na unidade"))
        return sugestoes

    def inscrever(self, dados: dict, preferencias: list[str]) -> str:
        numero = super().inscrever(dados, preferencias)
        # `BackendMock.inscrever` procura o nome da escola nas três unidades inventadas do
        # roteiro. Com os `desig7` reais do mapa ele não acha nenhuma e grava "creche",
        # que é literalmente o que a família lia no /status: "🏫 creche".
        nomes = {u.desig7: u.nome for u in _unidades()}
        escolhida = next((nomes[p] for p in preferencias if p in nomes), None)
        if escolhida:
            self._situacoes[numero] = replace(
                self._situacoes[numero], nome_escola=escolhida)
        return numero

    def panorama_da_regiao(self, endereco: Endereco) -> PanoramaRegiao | None:
        """As métricas da microárea onde o endereço cai.

        A microárea sai da MAIORIA entre as vizinhas mais próximas, não de
        point-in-polygon: o shapefile do IPP não viaja com o bot. E não sai da vizinha
        única porque uma creche isolada logo depois da divisa arrastaria a família
        inteira para a microárea errada: em Curicica isso devolvia Camorim. É por isso
        também que o texto fala em região, nunca em setor.
        """
        unidades = _unidades()
        if not unidades:
            return None
        vizinhas = sorted(
            unidades, key=lambda u: km_entre(endereco.lat, endereco.lng, u.lat, u.lon)
        )[:VIZINHAS_DA_REGIAO]
        codigos = Counter(u.microarea for u in vizinhas if u.microarea)
        if not codigos:
            return None

        linha = _microareas().get(codigos.most_common(1)[0][0])
        if linha is None:
            return None
        demanda = int(_num(linha["demanda"]))
        # `conf` soma quem foi confirmado nas unidades da microárea mesmo tendo pedido
        # outra como 1ª opção, e em 13 das 232 microáreas isso deixa `conf` maior que
        # `demanda`. Sem o teto, "achei_creches" lê "18 famílias pediram vaga de 1a
        # opção e 36 conseguiram" para a família, um número que contradiz o outro.
        atendidos = min(demanda, int(_num(linha["conf"])))
        # Microárea sem bairro na base existe (7.20, 7.21). Cai no bairro da creche mais
        # próxima em vez de escrever "Na região , em 2025".
        return PanoramaRegiao(
            microarea=linha["cod"],
            bairro=bairro_legivel(linha["bairro"]) or vizinhas[0].bairro,
            demanda=demanda, atendidos=atendidos,
            espera=int(_num(linha["espera"])), vagas_ociosas=int(_num(linha["ociosas"])),
            ano=ANO_BASE)
