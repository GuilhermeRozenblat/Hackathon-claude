# CSVs por trás do mapa "Fila de creche do Rio: mapa territorial por microárea"

Recorte: inscrições de **2025** (ano da base), unidades com lat/long geocodificadas e
alocadas à microárea por point-in-polygon no shapefile do IPP.

## Arquivos

### mapa_microareas.csv (232 linhas): camada de polígonos do mapa
É exatamente o que o mapa pinta. Uma linha por microárea.

| coluna | significado |
|---|---|
| cod | código da microárea (ex. `7.28`) |
| cre / cre_nome | Coordenadoria Regional de Educação |
| bairro | bairro(s) predominante(s) da microárea |
| unidades | nº de unidades de creche na microárea |
| demanda | inscritos de 1ª opção na microárea |
| conf | confirmados/atendidos |
| espera | ainda na fila |
| perdeu | perderam a convocação |
| ociosas | vagas ociosas nas unidades da microárea |
| pressao | demanda ÷ capacidade → cor do polígono |

### mapa_unidades.csv (820 linhas): camada de pontos do mapa
Uma linha por unidade. `d1` = demanda de 1ª opção, `cf` = confirmados,
`le` = vagas ociosas (livres), `lat`/`lon` = coordenadas do ponto.

### unidades_por_cre.csv (1.941 linhas): catálogo de unidades por CRE
Todas as unidades do município, ordenadas por CRE e tipo: `cre`, `cre_nome`,
`desig7` (designação com 7 dígitos), `nome`, `tipo` (Escola, EDI, Creche,
Creche Parceira, CIEP…), `microarea`, `bairro`, `rua`, `lat`, `lon`.
`no_mapa` = `sim` nas 820 que aparecem no mapa (as que têm demanda de creche em 2025);
nessas, `demanda_1a`, `confirmados` e `vagas_ociosas` vêm preenchidos.

Contagem por CRE: 1 Centro/Sta Teresa 105 · 2 Zona Sul/Tijuca 204 · 3 Méier 179 ·
4 Ilha/Penha 215 · 5 Irajá/Pavuna 147 · 6 Madureira/Anchieta 128 · 7 Jacarepaguá/Barra 213 ·
8 Bangu/Realengo 219 · 9 Campo Grande 213 · 10 Santa Cruz/Sepetiba 267 ·
11 Ilha do Governador 51.

### microareas_metricas.csv (232 linhas): tabela-mãe das métricas
Saída bruta do `geoprep.py`, antes de virar mapa. Traz colunas extras não plotadas:
`meta_parceiras`, `n_parceiras`, `deficit`, `perdeu_convocacao`, `vagas_ociosas`.

### microareas_distancia.csv (211 linhas)
Distância entre quem espera e a vaga mais próxima.
`km_mediana` = mediana da distância até a unidade com vaga;
`espera_ancorada` = fila com endereço geocodificado;
`espera_com_vaga_ate3km` = quantos desses têm vaga ociosa a ≤3 km.

### vagas_ociosas_geo.csv (367 linhas)
Vagas ociosas por unidade e grupamento (Berçário, Maternal…), com endereço e
coordenadas. `sobra_3km` = vagas que sobram mesmo servindo toda a fila num raio de 3 km.

## Fontes brutas, **fora** deste repositório

Os seis CSVs acima são o produto final; as fontes de onde eles saíram não viajam com o
código (são centenas de MB, e uma delas é um shapefile). Ficam registradas aqui para quem
precisar regerar:

- `Bases IC_ ClassificadoseFila/01_QueryA_InscricoesPorAno.csv.gz`: fila/inscrições
- `OferecimentosEvagas/Unidades_Unificadas_com_Localizacao.xlsx`: unidades + lat/long
- `OferecimentosEvagas/totalalunoscreche2025.xlsx`, `Parceiras2025.xlsx`: matrícula e vagas
- `Microáreas_SME_revisãoIPP/Microareas_SME_revisao.shp`: polígonos (EPSG:31983 → WGS84)

Quem lê os CSVs no código é `creche_bot/backend/mapa.py`; quem os desenha é
`creche-conectada.html` (ver [docs/PAINEL.md](../../docs/PAINEL.md)).
