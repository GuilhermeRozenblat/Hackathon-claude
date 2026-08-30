# dominio/ — vocabulário compartilhado

| Arquivo | Dono | Regra |
|---|---|---|
| `tipos.py` | Fase 0 | **CONGELADO.** Mudança = PR próprio, revisado por todas as trilhas |
| — | — | Nada mais mora aqui. Modelos de banco ficam em `dados/` |

Nenhum arquivo aqui importa `canal/`, `ia/`, `dados/` ou `backend/`. Domínio não conhece
infraestrutura — há teste que cobra isso.

Além dos tipos de inscrição e etapa, mora aqui o que a leitura de documento devolve
(`DadosExtraidos`) e a classificação de mensagem fora do roteiro (`Classificacao`) — são
vocabulário compartilhado, não detalhe de quem produz.

## Os quatro padrões que este arquivo carrega

**Vocabulário aberto, comportamento fechado.** `Etapa.codigo` é `str` (o backend define
quais etapas existem, e isso muda por município). `Etapa.tipo` é `Literal` de 6 valores
(nós definimos o que fazer com cada uma). Etapa nova que caia num tipo conhecido funciona
sem código novo. A tradução mora em `backend/http.py`, numa tabela só.
Ver [D4](../../docs/DECISOES.md).

**Régua do processo é DADO, não código.** Pesos, ordem e texto dos critérios mudam todo
ano — entre 2023 e 2024 só 3 das 13 perguntas sobreviveram e o teto caiu de 465 para 100
pontos. Por isso `Criterio` é uma lista que o backend devolve, nunca um enum aqui dentro.
Ver [D15](../../docs/DECISOES.md).

**Duas visões da inscrição, de propósito.** `Situacao`/`Etapa` é o que MUDA e dispara
notificação. `Desfecho` é o que a família VÊ ao consultar: um estado só, calculado por
`desfecho_entre()` como a melhor situação entre as opções dela. O banco grava uma situação
por opção de creche, e mostrar isso cru quebra a confiança na hora — 77,8% das linhas
"Cancelado pelo sistema" pertencem a inscrições que foram ATENDIDAS.
Ver [D14](../../docs/DECISOES.md).

**O que não existe aqui: pontuação e posição na fila.** Não há campo para elas, então
nenhuma tela pode mostrá-las por acidente. A classificação é norma (Resolução SME nº
542/2025), roda depois do fechamento das inscrições, e não existe no momento da conversa.
O que existe é `Concorrencia`, com `ano` obrigatório — quantas famílias disputaram cada
vaga no processo passado é fato verificável. Ver [D5](../../docs/DECISOES.md).

## Duas guardas em `__post_init__` que valem ouro

`Etapa` recusa `acao_presencial` sem endereço e `convocacao` sem prazo. Mandar a família à
creche sem dizer onde, e deixar um prazo vencer em silêncio, são os dois piores erros que
este bot pode cometer — então viraram erro de tipo. O segundo é a causa direta dos 7,7%
que perderam a vaga já convocados em 2025.
