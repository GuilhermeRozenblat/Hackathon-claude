# dominio/: vocabulário compartilhado

`tipos.py` é **CONGELADO**: mudança é PR próprio, revisado por todas as trilhas. Nada mais mora
aqui. Modelo de banco fica em `dados/`. Nenhum arquivo daqui importa `canal/`, `ia/`, `dados/`
ou `backend/`, e há teste que cobra.

Além de inscrição e etapa, moram aqui `DadosExtraidos` (o que a leitura de documento devolve) e
`Classificacao` (a classificação de mensagem): vocabulário compartilhado, não detalhe de quem
produz.

## Os quatro padrões que o arquivo carrega

**Vocabulário aberto, comportamento fechado.** `Etapa.codigo` é `str` (o município define as
etapas, e varia por rede); `Etapa.tipo` é `Literal` de 6 valores (nós definimos o que fazer com
cada um). Etapa nova que caia num tipo conhecido funciona sem código novo. A tradução mora numa
tabela só, hoje no `BackendMock` ([D4](../../docs/DECISOES.md)).

**Régua do processo é DADO, não código.** `Criterio` é lista que o backend devolve, nunca um
enum aqui, porque a régua muda de ano para ano ([D15](../../docs/DECISOES.md)).

**Duas visões da inscrição.** `Situacao`/`Etapa` é o que MUDA e dispara notificação. `Desfecho` é
o que a família VÊ: um estado só, calculado por `desfecho_entre()`. O banco grava uma situação
por opção de creche, e mostrar isso cru quebra a confiança ([D14](../../docs/DECISOES.md)).

**Pontuação e posição na fila não existem aqui.** Não há campo para elas, então nenhuma tela
pode mostrá-las por acidente. O que existe é `Concorrencia`, com `ano` **obrigatório**
([D5](../../docs/DECISOES.md)).

## As duas guardas em `__post_init__`

`Etapa` recusa `acao_presencial` sem endereço e `convocacao` sem prazo. Mandar a família à creche
sem dizer onde, e deixar um prazo vencer em silêncio, são os dois piores erros que este bot pode
cometer, e por isso viraram erro de tipo, não convenção.
