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

## Os dois padrões que este arquivo carrega

**Vocabulário aberto, comportamento fechado.** `Etapa.codigo` é `str` (o backend define
quais etapas existem, e isso muda por município). `Etapa.tipo` é `Literal` de 5 valores
(nós definimos o que fazer com cada uma). Etapa nova que caia num tipo conhecido funciona
sem código novo. A tradução mora em `backend/http.py`, numa tabela só.

**Nota de corte, não probabilidade.** O sistema não decide quem entra. Não existe
"probabilidade de conseguir a vaga" neste código — só a nota de corte do ano passado, e
`NotaCorte.ano` é obrigatório justamente para a UI ser forçada a dizer de quando é o
número. Ver [D5](../../docs/DECISOES.md).
