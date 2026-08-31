# O painel `creche-conectada.html`

Um arquivo. Abre com duplo clique, roda sem servidor, sem build e sem dependência: HTML,
CSS e JavaScript de navegador. É a **segunda cara do mesmo sistema**: o bot atende uma
família por vez no Telegram; o painel mostra a rede inteira por trás daquela conversa, e as
contas que decidem o que a família vê.

Ele existe por um motivo simples: quando o bot diz “chance estimada de 33% nesta creche,
com base em 2025”, alguém tem que poder abrir o número e ver de onde ele saiu. O painel é
esse lugar.

## De onde vem cada número

Três origens, e a tela sempre diz qual é qual.

**1. Os CSVs de `creche_bot/MapaFilaCreche/`**: 232 microáreas, 820 unidades de creche com
demanda em 2025, vagas ociosas por grupamento, distância até a vaga mais próxima. São os
**mesmos arquivos** que o `BackendMapa` lê quando o bot fala de uma creche. Servido por
HTTP, o painel busca os arquivos do disco; aberto com `file://`, cai nas cópias byte a byte
embutidas em `<script type="text/csv">` no fim do HTML. A barra lateral diz qual caminho
está valendo.

**2. O Postgres do bot (schema `creche`)**: só na vista *Banco*, e só em **contagem**. Ver
[Privacidade](#privacidade-o-que-o-painel-nunca-lê) abaixo.

**3. Oito casos de matrícula fictícios**: na vista *Casos*. As pessoas, as datas e os
documentos são inventados; a unidade, o bairro e a microárea de cada caso são ancorados nos
CSVs, para a ficha mostrar território verdadeiro. A tela diz isso em letra visível, duas
vezes.

## As cinco vistas

| Vista | O que responde | Origem |
|---|---|---|
| **Painel** | Quantos pediram, quantos entraram, quantos ficaram na fila, por CRE e por unidade | CSVs |
| **Mapa territorial** | Onde a fila e a sobra estão, por microárea, em bolhas no centroide real das unidades | CSVs |
| **Casos de matrícula** | Como um caso é acompanhado até a matrícula ou o CRAS | roteiro fictício + CSVs |
| **Cálculos do bot** | Como o CEP vira três creches na tela, com cada passo da conta aberto | CSVs |
| **Banco de dados** | O que a conversa grava, em que tabela, em que ponto do roteiro, e quantas linhas há agora | Postgres |

### Cálculos do bot

É a vista que fecha o ciclo. Escolha um ponto de partida (os três CEPs do roteiro, os mesmos
da demo e dos testes, ou o centroide de qualquer microárea) e um grupamento, e ela
refaz, no navegador, exatamente o que `creche_bot/backend/mapa.py` faz no servidor:

1. **O raio.** Começa em 2 km (82,9% de quem trocou de creche andou até 2 km) e só abre para
   3,5 e 5 km se não fechar as três vagas da tela. A tabela mostra quantas creches cabem em
   cada raio e qual venceu.
2. **As três creches.** Para cada uma: distância por haversine, vaga ociosa **no grupamento
   escolhido** (vaga sobrando no Maternal II não serve a quem precisa de Berçário), e a
   chance estimada com todos os passos à vista: razão crua, piso de vaga aberta, teto e
   piso. Termina com a frase exata que chegaria no celular da família.
3. **A região.** A microárea sai da **maioria entre as sete creches mais próximas**, não de
   ponto-em-polígono, porque o shapefile do IPP não viaja com o bot, e a vizinha mais próxima
   sozinha erra na divisa (em Curicica ela devolvia Camorim). A tela mostra as sete, os
   votos e a vencedora.
4. **A régua do estimador.** Onde a conta trava, nas 820 creches: quantas batem no teto de
   95%, quantas no piso de 3%, e as 214 (26%) em que `confirmados` passa a demanda de 1ª
   opção, porque `confirmados` conta toda matrícula efetivada na unidade, inclusive quem a
   pediu em 2ª ou 3ª opção e foi realocado. Numa delas a razão crua chega a 364%. O teto é o
   que impede isso de virar promessa na tela.

**Isto é um espelho, não a fonte.** A fonte é `backend/mapa.py`. Se aquele arquivo mudar e
este bloco não, o painel mente. É por isso que a vista mostra o **valor cru de cada
passo** em vez de só o resultado: a divergência fica visível em vez de silenciosa. A
verificação é comparar os três CEPs do roteiro nos dois lados; hoje batem casa decimal por
casa decimal.

### Banco de dados

As onze tabelas do schema `creche`, quem escreve em cada uma e em que bloco do roteiro. Com
o servidor no ar, os números vêm do Postgres na hora; sem ele, do último retrato gravado
dentro do HTML, com a data à vista.

O momento em que as duas metades do sistema se encontram é a tabela **“as creches
escolhidas”**: o `id_escola` que a conversa gravou em `preferencia_escola` é o `desig7` das
820 unidades do mapa. O nome e o bairro vêm dos CSVs; do banco vêm a distância, a vaga e **a
chance que a família leu**, congeladas no dia da escolha, com o `ano_referencia` colado.

A última coluna refaz a conta com os CSVs de **agora**, e as duas juntas são o ponto: se a
chance lida e a de hoje divergirem, o chão mudou desde a escolha — dado novo, recorte novo, ou
alguém mexeu em `backend/mapa.py`. Sem a chance congelada isso seria invisível, e não daria
para auditar com base em que a família decidiu.

O SQL aparece na própria tela, e não é cópia escrita à mão: é o texto que `scripts/painel.py`
executou, viajando junto com os números.

## Rodar

```bash
open creche-conectada.html      # duplo clique: usa as cópias embutidas dos CSVs
make painel                     # http://localhost:8000, CSVs do disco + banco ao vivo
make painel-snapshot            # congela o retrato do banco dentro do HTML
```

`make painel` sobe `scripts/painel.py`: um `http.server` da stdlib que serve o painel, os
CSVs e `/api/banco.json`. Sem `DATABASE_URL` no `.env` ele sobe igual, o endpoint responde
503 e a vista *Banco* cai no retrato embutido dizendo que caiu.

**Hospedado é o mesmo painel, pelo mesmo caminho.** `scripts/servidor.py` importa a
allowlist e o `/api/banco.json` daqui e acrescenta o webhook do Telegram, num processo só.
Ver [HOSPEDAGEM.md](HOSPEDAGEM.md). Ou seja: no ar, a vista *Banco* lê o Postgres ao vivo,
igual ao `make painel`.

O retrato embutido é a rede de segurança dos dois casos em que não há endpoint: o painel
aberto com duplo clique, e o banco fora do ar. Ele mora dentro do HTML pelo mesmo motivo dos
CSVs: o arquivo tem que fazer sentido sozinho. `make painel-snapshot` regrava esse bloco, e
vale rodar antes de mandar o arquivo para alguém sem acesso ao banco.

## Privacidade: o que o painel nunca lê

O banco guarda nome de criança, CPF, endereço e as respostas da régua de prioridade,
inclusive as sensíveis do art. 11 da LGPD. **Nada disso sai de lá para o painel.**

- Toda query em `scripts/painel.py` é `COUNT`, `SUM` ou `GROUP BY`, sobre conexão marcada
  `read_only`.
- De `cadastro` sai `count(coluna)`, quantas linhas têm cada campo preenchido, **nunca qual
  valor**. É essa contagem que vira o gráfico de preenchimento.
- Os únicos textos que atravessam são vocabulário do sistema (estado da conversa, código de
  critério, código de etapa) e nome de creche, que é público e já está nos CSVs.
- Das respostas sensíveis sai o **código** e o booleano, que é tudo o que o banco guarda: o
  texto da família nunca chegou lá.

**A raiz do repositório não é servida.** `scripts/painel.py` tem allowlist: o HTML e os seis
CSVs, ponto. Um `python3 -m http.server` solto nesta pasta entregaria `.env`, `creche.db` e
`.git/` para quem pedisse, e é justamente o comando que a pessoa digitaria sem pensar.

O servidor é diagnóstico e demonstração: sem autenticação, sem TLS, uma requisição por vez,
escutando só em `127.0.0.1`. Não é para expor.

## Por que o SQL mora em `scripts/`

A regra do projeto é que só `creche_bot/dados/` conhece banco, e há teste varrendo o pacote
(`make fronteira`). O painel precisa de agregado que a `Repositorio` não expõe, e não vale
alargar um contrato congelado, usado por quatro trilhas, por causa de uma tela de
demonstração. `scripts/verificar_banco.py` já fala com o Postgres pelo mesmo motivo.

## Honestidade: as mesmas regras do bot

O painel obedece às mesmas restrições que `CLAUDE.md` impõe à conversa, porque um número que
o bot não pode dizer também não pode aparecer no telão:

- **Nem pontuação, nem posição na fila, nem nota de corte.** A classificação é norma
  (Resolução SME nº 542/2025), roda em SQL determinístico depois do fechamento das
  inscrições, e no momento em que estes números são lidos ela não existe.
- **O ano vai colado em todo número derivado.** Sem ele, “5 famílias por vaga” vira promessa
  sobre o processo de agora.
- **É “chance estimada”, nunca “sua chance”.** O número é da creche, não da criança:
  idêntico para toda família que a olhar, e a régua de prioridade, que é o que de fato
  decide, não entra nele.
- **Três contagens de vaga ociosa ficam à vista.** Os CSVs trazem réguas diferentes (1.340
  no critério estrito, 2.915 por grupamento, 16.033 vagas livres por unidade). Escolher uma
  em silêncio mudaria a conclusão; o painel mostra as três e diz de onde cada uma vem.

## O que deliberadamente não tem

- **Mapa com tiles.** As bolhas são posicionadas no centroide real das unidades, em projeção
  equiretangular. Um mapa base pediria rede, chave de serviço e um arquivo que não abre com
  duplo clique.
- **Framework, build, dependência.** Um arquivo, sem passo de compilação. O que o painel faz
  cabe em `innerHTML` com delegação de evento, e é isso que deixa ele abrir daqui a dois
  anos sem `npm install`.
- **Escrita no banco.** O painel só lê. Marcar documento e avançar etapa na vista *Casos*
  mexem em estado da página, não em linha de tabela.
- **Login.** Não existe usuário. Se um dia mostrar dado por unidade escolar, passa a
  precisar, e aí não é mais um arquivo só.
