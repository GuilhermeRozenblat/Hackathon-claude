# Registro de decisões

Uma entrada por decisão que custaria caro reverter: o que foi decidido, por quê, e o que
faria a gente mudar de ideia. Decisões pequenas ficam no código, como comentário
`ponytail:`. Um `grep -rn "ponytail:" creche_bot/` lista todas.

| | |
|---|---|
| **Plataforma** | [D1](#d1--os-limites-do-whatsapp-valem-desde-o-telegram) limites do WhatsApp · [D6](#d6--seleção-ordenada-em-três-toques) seleção em toques |
| **Fronteiras** | [D2](#d2--os-dados-do-município-ficam-atrás-de-uma-porta) backend · [D3](#d3--a-persistência-fica-atrás-de-outra-porta) persistência · [D4](#d4--vocabulário-aberto-comportamento-fechado) vocabulário · [D21](#d21--postgres-no-supabase-em-schema-próprio-sem-orm) Postgres |
| **Honestidade** | [D5](#d5--nem-nota-de-corte-nem-pontuação-nem-posição-na-fila) o que não mostramos · [D14](#d14--a-família-vê-um-desfecho-nunca-a-situação-bruta) desfecho · [D19](#d19--a-chance-estimada-entra-a-classificação-continua-fora) chance estimada |
| **Privacidade** | [D7](#d7--dado-sensível-consentimento-separado-um-turno-só-nunca-ecoado) dado sensível · [D11](#d11--segredo-não-chega-ao-log-nem-por-traceback) segredo em log · [D17](#d17--dúvida-solta-é-respondida-mas-com-cota) texto do cidadão é dado |
| **Conversa** | [D8](#d8--os-blocos-de-cadastro-são-dados-não-código) perguntas como dados · [D23](#d23--as-colunas-do-espelho-consultável-seguem-as-perguntas-do-roteiro) o espelho consultável · [D12](#d12--a-conta-começa-no-cpf-do-responsável) CPF do responsável · [D13](#d13--endereço-só-por-cep--número) CEP · [D15](#d15--a-régua-do-processo-é-dado-do-backend) régua · [D16](#d16--retomada-em-72h-e-idempotência-desde-o-primeiro-turno) retomada · [D18](#d18--quem-classifica-a-mensagem-é-o-modelo) classificação · [D22](#d22--o-roteiro-do-cliente-é-a-fonte) o roteiro |
| **Escopo** | [D9](#d9--rodar-quase-não-exige-dependência) dependências · [D10](#d10--a-lacuna-do-cras-é-dita-não-escondida) CRAS · [D20](#d20--a-ia-é-da-pessoa-que-conversa) a IA é de quem conversa |

---

## D1 · Os limites do WhatsApp valem desde o Telegram

`MensagemSaida.__post_init__` recusa mais de 3 botões, mais de 10 itens de lista, rótulo
acima de 20 caracteres e markdown, mesmo no código do Telegram, que aceitaria muito mais.

**Por quê.** O flip é requisito. Desenhar com a folga do Telegram transforma o flip em
reescrita da conversa inteira; com a trava, um fluxo grande demais quebra no `pytest` hoje.

**Já se pagou duas vezes:** rejeitou `Creche Jardim das Flores` (24 caracteres) e forçou o
redesenho do painel de escolas, que queria 5 botões (D6).

**Mudaria se** o produto abandonasse o WhatsApp.

---

## D2 · Os dados do município ficam atrás de uma porta

`backend/porta.py`, 17 operações. `BackendMapa` roda hoje sobre os CSVs reais, com
`BackendMock` por baixo; `BackendHTTP` entra quando o outro time publicar. **Nada do JSON
deles sai de `backend/`.**

**Por quê.** O backend é de outro time, em outra máquina. Sem camada anticorrupção, o nome
de campo deles vira dependência de `conversa/` e a primeira renomeação quebra o bot.

**Mudaria se** o backend passasse a orquestrar a própria conversa.

---

## D3 · A persistência fica atrás de outra porta

`dados/porta.py`, 21 operações, duas implementações (`RepositorioMemoria` e
`RepositorioPostgres`, [D21](#d21--postgres-no-supabase-em-schema-próprio-sem-orm)). Fora
dessa pasta não existe `psycopg`, `SELECT`, `cursor` nem `session`, e há teste que varre o
pacote.

**Por quê.** A pasta é trabalhada em paralelo por outra pessoa. Sem a fronteira, uma
refatoração no banco bloqueia quem mexe no chat, e `REPOSITORIO=memoria` roda o bot inteiro
sem tocar em disco.

**Recusado.** Repositório por entidade, UnitOfWork, CRUD genérico. Uma porta, duas
implementações, e a bateria roda parametrizada contra as duas.

---

## D4 · Vocabulário aberto, comportamento fechado

`Etapa.codigo` é `str` livre, porque o município define quais etapas existem. `Etapa.tipo` é
`Literal` de seis valores, porque nós definimos o que fazer com cada uma. A tradução mora numa
tabela só, com default `"aguardando"`.

**Por quê.** O vocabulário do município muda e varia por rede; o comportamento do bot é
pequeno e estável. Etapa nova que caia num tipo conhecido funciona sem código novo.

**O default é `"aguardando"` de propósito:** etapa desconhecida faz o bot avisar que andou,
sem inventar cobrança. Mandar a família à creche à toa é o erro caro.

---

## D5 · Nem nota de corte, nem pontuação, nem posição na fila

> **Revisto. Ver [D19](#d19--a-chance-estimada-entra-a-classificação-continua-fora).** A
> chance estimada por creche passou a aparecer. O resto vale inteiro.

Não existe pontuação nem posição na fila em lugar nenhum do código. Sobre uma creche vão
distância, vaga ociosa agora e concorrência do ano passado (`Concorrencia` tem `ano`
obrigatório no tipo).

**Por quê.** O sistema não seleciona quem entra: quem aloca é o município, por norma
(Resolução SME nº 542/2025), em SQL determinístico que roda **depois do fechamento das
inscrições**. Durante a conversa a classificação não existe.

**Por que caiu a nota de corte.** É a pontuação do último aprovado, e o teto da régua foi 465
pontos em 2023 e 100 em 2024: pontuação não é comparável entre anos. "5 famílias por vaga no
ano passado" é fato; "nota de corte 87" é número sem régua. Posição na fila também não: a
classificação é por critério, não por ordem de chegada.

**Testado.** Um teste varre o roteiro e falha se "garantido", "com certeza" ou "vai
conseguir" aparecer em qualquer tela.

---

## D6 · Seleção ordenada, em três toques

O roteiro pede "seleção múltipla ordenável" e o WhatsApp não tem esse widget. Cada toque
acrescenta uma preferência, o bot confirma a posição e mostra o que sobrou, e toda tela cabe
em 3 botões.

**Por quê.** É a única forma que funciona nas duas plataformas, e ficou melhor: a pessoa vê a
ordem se formando em vez de arrastar itens.

**Recusado.** Pedir a ordem por texto ("responda 1,3,2"): erro alto e péssimo no celular.

---

## D7 · Dado sensível: consentimento separado, um turno só, nunca ecoado

Três regras para os critérios `Criterio.sensivel`:

1. **Consentimento próprio** (`CONSENTIMENTO_SENSIVEL`), separado do geral, com "Prefiro
   pular" sempre disponível. LGPD art. 5º II e art. 11: violência doméstica, doença crônica,
   uso de substâncias e situação prisional exigem consentimento específico e destacado.
2. **As cinco perguntas num turno só**, como checklist, a exceção deliberada à regra de uma
   pergunta por mensagem. Individualmente disparam entre 1,6% e 5,3%; somadas, 13,6% marcam
   ao menos uma. Cinco turnos invasivos para esse aproveitamento é péssimo desenho.
3. **Nunca ecoar a resposta.** O histórico do chat fica no aparelho da família, que pode ser
   o mesmo aparelho do agressor. "Recebido: alguém de casa está preso ✅" é um risco que o eco
   não compra nada para justificar.

**E nunca bloqueia.** `Criterio.documento_opcional` marca violência, substâncias e situação
prisional: exigir boletim de ocorrência de uma vítima, dentro de um chat, como condição para
inscrever a criança, é violento.

---

## D8 · Os blocos de cadastro são dados, não código

`conversa/formulario.py` é uma tupla de `Campo` por lista: `CADASTRO` (blocos 1 a 3),
`CONTATO` (bloco 4) e `CONSULTA` (bloco C.1). Ramificação é `pular_se`, uma lambda por campo.

**Por quê.** "Uma pergunta por mensagem" é literalmente uma lista de perguntas; como código
seriam 15 handlers quase idênticos. E produto reescreve esses textos toda semana, sem tocar
em lógica.

**Bônus.** `Campo.__post_init__` cobra o limite de 3 opções, então uma pergunta com 4
respostas fechadas quebra na importação.

**O bloco da régua não entra aqui**: é dado do backend ([D15](#d15--a-régua-do-processo-é-dado-do-backend)).

---

## D9 · Rodar quase não exige dependência

> **Revisto. Ver [D21](#d21--postgres-no-supabase-em-schema-próprio-sem-orm).** O SQLite
> saiu e entrou o Postgres, então existe **uma** dependência de runtime (`psycopg`).

`urllib` da stdlib no lugar de `python-telegram-bot`, e a V1 **não persiste documento**:
extrai, guarda estruturado, descarta os bytes.

**Por quê.** `python-telegram-bot` é async-first e contaminaria `conversa/`, `ia/` e `dados/`
inteiras; a Bot API que usamos são 6 métodos HTTP. Não persistir documento é a regra de
minimização, e de quebra elimina a dependência de criptografia.

**Mudaria se** houvesse webhook com concorrência real (framework async) ou a creche exigisse
o documento original (cofre cifrado).

---

## D10 · A lacuna do CRAS é dita, não escondida

Quando a família escolhe entregar no CRAS, o bot avisa que os documentos ainda seguem para a
creche, que isso leva alguns dias, e que ele avisa quando a creche confirmar.

**Por quê.** O processo hoje não tem esse retorno, o que foi apontado no próprio roteiro. Não
dá para inventar a integração; dá para não deixar a família no escuro.

**Pendência de processo, não de código.** Quando a confirmação existir, entra como mais uma
etapa do backend, sem código novo ([D4](#d4--vocabulário-aberto-comportamento-fechado)). Há
teste garantindo que o aviso não some do texto.

---

## D11 · Segredo não chega ao log, nem por traceback

`segredos.py` instala um `FormatadorSeguro` que substitui `TELEGRAM_TOKEN`,
`ANTHROPIC_API_KEY`, `DATABASE_URL` e `FERNET_KEY` por `***` em mensagem **e** em traceback.

**Por quê.** O token do Telegram viaja no **caminho da URL** da Bot API. Um traceback de
`urllib` traz a URL inteira, e basta cair no console, no CI ou num print colado no chat da
equipe. Quem tem o token controla o bot, e o bot conversa com famílias sobre documentos de
crianças.

**Dois detalhes.** Segredo com menos de 12 caracteres é ignorado (apagar toda ocorrência de
uma string curta destruiria log legítimo). E como a chave da Anthropic agora vem do chat e
não do ambiente ([D20](#d20--a-ia-é-da-pessoa-que-conversa)), não há valor para comparar,
por isso o formatador também redige por formato (`sk-ant-…`).

---

## D12 · A conta começa no CPF do responsável

A âncora é o CPF do **adulto**: `backend.buscar_por_responsavel(cpf)`. O documento da criança
(CPF, DNV ou NIS) vem depois e **nenhum dos três é obrigatório**.

**Por quê.** Exigir CPF de criança de 0 a 3 anos no primeiro turno derruba família na porta.
O CPF do adulto é mais confiável, é o que a pessoa tem na mão, e é o único que reconhece
reinscrição e irmãos.

**O que destrava.** 27,9% das crianças de 2025 já constavam em 2024: o histórico preenche o
cadastro num turno e auto-valida "esperou na fila no ano anterior" (14,5% declaram, 12,1%
comprovam). E 1.738 responsáveis inscreveram duas ou mais crianças, e "É outra criança"
reaproveita responsável e endereço.

---

## D13 · Endereço só por CEP + número

`backend.resolver_cep(cep, numero)` devolve logradouro, bairro e coordenadas. A família vê o
bairro uma vez, para confirmar, e nunca digita nenhum dos dois.

**Por quê.** Campo livre gerou 1.608 grafias para ~925 bairros: "Inhaúma" sozinho tem 13
variantes. O CEP é 100% preenchido e 100% válido desde 2024.

**O número é obrigatório** porque sem ele a precisão cai para ~1,4 km, o suficiente para
errar a creche certa dentro do raio de 2 km que as famílias aceitam (82,9% dos que trocaram
andaram até 2 km).

---

## D14 · A família vê um desfecho, nunca a situação bruta

O banco grava **uma situação por opção de creche**. A consulta calcula `desfecho_entre()`, a
melhor situação da lista, por `PRECEDENCIA`, e mostra só ela. Sete estados, sete telas.

**Por quê.** 77,8% das linhas `Cancelado pelo sistema` pertencem a inscrições que **foram
atendidas**: é o cancelamento automático das outras opções. Uma família que conseguiu a vaga
veria "cancelado" em 4 das 5 escolhas dela.

**Detalhe que quebra query.** O valor gravado é `Cancelado na confirmacao`, sem cedilha e
sem til. Filtrar pela grafia correta devolve zero linhas.

---

## D15 · A régua do processo é dado do backend

`backend.criterios_do_processo()` devolve uma lista de `Criterio`: código, rótulo, pontos,
grupo, se é sensível e o que comprova. O bloco da régua é montado caminhando essa lista. Não
existe enum de critério em `dominio/`.

**Por quê.** Entre 2023 e 2024 só **3 das 13 perguntas sobreviveram** e o teto caiu de 465
para 100 pontos. Régua escrita à mão quebra na virada do ano, que acontece no meio do
período de inscrição, o pior momento possível.

**O que fica nosso.** A **forma** da pergunta (`FormaCriterio`: sim/não, múltipla, número,
anexo) e o desenho do turno. O conteúdo é do processo vigente.

---

## D16 · Retomada em 72h, e idempotência desde o primeiro turno

Sessão viva por 72h não recomeça: o bot diz onde parou e oferece continuar.
`dados["chave_idempotencia"]` nasce no primeiro turno e viaja até `backend.inscrever()`.

**Por quê.** Conversa de WhatsApp cai: o app fecha, o celular descarrega, a pessoa responde
no dia seguinte. Sem retomada ela recomeça do zero e desiste. Sem chave de idempotência ela
entra duas vezes, e duas inscrições para a mesma criança se anulam, um dos motivos por trás
dos 9,5% de "nenhuma opção seguiu".

**Consequência.** `inscrever()` é a única operação da porta que **nunca** pode ter retry
automático.

---

## D17 · Dúvida solta é respondida, mas com cota

Mensagem classificada como `duvida` é respondida sem mudar o estado da sessão: perguntar não
faz perder o lugar na fila. Com dois limites: **8 perguntas por hora por contato** e um system
prompt (`SISTEMA_DUVIDA`) que declara o texto do usuário como dado, não instrução.

**A cota** existe porque cada dúvida é uma chamada paga, e um chat aberto na internet é um
botão de gastar dinheiro dos outros. Estourada, a mensagem volta a ser tratada como resposta
do roteiro. O cadastro continua, só a IA descansa.

**O prompt** delimita (`<pergunta>`), declara que ali dentro é dado, e não manda nada da
família para o modelo: só a etapa e a pergunta estática no ar. Ninguém precisa do CPF da
criança para explicar como funciona a fila.

**ponytail assumido.** O contador é um dicionário em memória, de um processo só, com o
`clear` que impede virar vazamento no dia do pico.

---

## D18 · Quem classifica a mensagem é o modelo

Toda mensagem **digitada**, e não botão nem comando, passa por `Redator.classificar()`, que
no `RedatorClaude` é uma chamada ao Haiku. A saída é o vocabulário fechado de `Intencao`, e a
máquina age em duas: `duvida` responde e mantém o estado (D17), `fora_de_contexto` repete a
pergunta.

**O que isso reverteu.** Antes era `endswith("?")` mais uma lista de palavras. A heurística
acerta "como funciona a fila?" e erra tudo que importa: "meu marido perdeu o emprego mês
passado" não termina em "?", não é resposta de CPF nenhum, e ia direto para o validador virar
"esse CPF não confere".

**`fora_de_contexto` não bloqueia.** O prompt manda escolher `responder` no empate, o
reconhecimento não conta erro no campo, e reorientar duas vezes seguidas é proibido: na
segunda a mensagem passa e o `_errar` do formulário assume. Classificador que erra pode
custar um turno; não pode prender a família fora do próprio cadastro.

**Custo e privacidade.** Uma chamada de Haiku por mensagem digitada, system de ~250 tokens,
saída de uma palavra; botão e comando não gastam nada. Para o modelo vai
`ESTADO: pergunta estática` mais a mensagem delimitada, nunca `pergunta_alt`, que interpola
o nome da criança. Há teste que dirige o cadastro e falha se um dado da família aparecer no
contexto.

---

## D19 · A chance estimada entra. A classificação continua fora

O painel de escolas mostra, para cada creche, uma **chance estimada**, que é `confirmados ÷
demanda de 1ª opção` naquela unidade, em 2025, de `backend/mapa.py` sobre os CSVs de
`MapaFilaCreche/`. Revisão parcial de
[D5](#d5--nem-nota-de-corte-nem-pontuação-nem-posição-na-fila).

**Por quê.** A família decide entre creches, e "1,4 km" não basta para decidir. O dado que
responde a pergunta dela existe e é observado: das 820 unidades com demanda em 2025, sabemos
quantas famílias pediram cada uma como 1ª opção e quantas foram atendidas. Esconder isso não
deixava a família mais informada, só mais ansiosa.

**As três condições que fazem isso ser honesto.**

1. **O ano vai colado no número**, em toda tela. Há teste.
2. **Nunca 0% e nunca 100%** (`CHANCE_MIN`/`CHANCE_MAX`). Vaga ociosa hoje não garante vaga
   em fevereiro, e fila cheia no ano passado não fecha a porta deste ano.
3. **A classificação não está dentro dela**, e o rodapé diz isso. Duas famílias que veem 40%
   na mesma tela podem ter desfechos opostos por causa da régua de prioridade.

**Limitação conhecida.** A chance é medida sobre quem pediu a unidade como **1ª opção**,
porque é o recorte que a base tem, e `confirmados` conta toda matrícula efetivada ali,
inclusive quem foi realocado de 2ª ou 3ª opção. Em 214 das 820 unidades isso passa de 100% na
razão crua; o teto é o que impede aparecer na tela.

**O filtro mudou junto.** `ia/redacao.py` deixou de barrar "probabilidade" e "chance", e
passou a barrar "está na frente". O que a lista protege é o salto de estimativa para promessa.

**Mudaria se** o backend publicar a classificação real, ou a base trouxer demanda por posição
de preferência.

---

## D20 · A IA é da pessoa que conversa

A `ANTHROPIC_API_KEY` do ambiente deixou de ser lida. Quem quer IA cadastra a própria chave
pelo chat, e a conversa começa perguntando isso, num bloco 0.0 com duas saídas: **Ligar a IA**
ou **Seguir sem IA**. A chave fica na sessão daquele contato, sobrevive ao `/start` e some no
`/apagar`. Tudo em `conversa/passos/ia.py`.

**Por quê.** Chat aberto na internet com o modelo pendurado na chave de quem hospeda é um
botão de gastar dinheiro dos outros. A cota de
[D17](#d17--dúvida-solta-é-respondida-mas-com-cota) limita o estrago, não a origem dele.

**O que não muda.** O cadastro inteiro funciona sem IA: `RedatorEstatico`, textos à mão,
classificação por heurística. Sem chave só a **pergunta solta** muda de resposta: em vez de
cair calada no roteiro, ela diz como ligar a IA.

**As quatro coisas que a implementação cobra.**

1. **A chave é testada antes de ser salva** (`diagnosticar()`, uma chamada de um token).
   Guardar sem testar seria a pior falha silenciosa: o bot fica idêntico ao de antes e quem
   colou a chave nunca descobre.
2. **Falha vira frase, não código HTTP.** `MOTIVOS` traduz 401, 403, 404, 429, 5xx, rede fora
   e crédito insuficiente. O corpo da resposta da API **nunca** é ecoado: vem em inglês, muda
   sem aviso e carrega detalhe da conta de quem cadastrou.
3. **Falha no meio da conversa também é dita**, uma vez por queda, não a cada mensagem. O
   cadastro segue com os textos prontos; o que não pode é a pessoa achar que a IA está de pé.
4. **A chave não pode virar resposta de campo nem aparecer em log.** Toda mensagem que contém
   `sk-ant-…` é interceptada antes do roteiro: seguir adiante gravaria a chave como se fosse
   um nome e a ecoaria na tela.

**Ninguém fica preso na tela 0.0:** qualquer outra resposta segue o roteiro com uma nota de
uma linha. A exceção é quem acabou de pedir para ligar.

**Limitação conhecida.** A chave fica em texto claro no `contexto` jsonb da sessão, porque
`dados/porta.py` é contrato congelado. Aceitável enquanto a chave é da própria pessoa e o
`/apagar` a elimina.

**Mudaria se** o bot virar serviço para famílias de verdade. Aí a chave passa a ser de quem
opera, com coluna própria e cifrada, e o bloco 0.0 sai da tela do cidadão.

---

## D21 · Postgres no Supabase, em schema próprio, sem ORM

`dados/postgres.py` com psycopg 3 e `ConnectionPool`, pelo pooler em modo transação. As
tabelas ficam no schema **`creche`**, não no `public`. O `sqlite.py` da validação foi
removido.

**Por que schema próprio.** No Supabase o `public` é servido pela Data API a quem tiver a
chave anônima, e essa chave costuma acabar no front. Estas tabelas guardam nome de criança e
CPF. Um schema fora da lista de exposição não é alcançável, e isso não depende de ninguém
lembrar de manter RLS restritiva numa tabela nova. RLS fica ligada mesmo assim, sem política.

**Sem SQLAlchemy e sem Alembic.** São 21 métodos sobre onze tabelas, num arquivo só, com uma
implementação. DDL idempotente no boot custa menos que migração versionada enquanto o schema
muda toda semana.

**Custo assumido.** O bot passou a ter uma dependência de runtime, o que
[D9](#d9--rodar-quase-não-exige-dependência) evitava. `REPOSITORIO=memoria` continua rodando
sem banco.

**Detalhes que custaram teste.** `prepare_threshold=None` (o pooler troca a conexão de
servidor embaixo do processo); `check=check_connection` (o pooler derruba conexão ociosa e o
worker pegaria uma morta); nome de tabela qualificado em toda query (um `SET search_path` não
sobrevive à troca de sessão); e savepoint em `contato_de()`, porque duas threads escrevem e
um contato duplicado faz a pessoa perder a conversa no meio.

**Mudaria se** o schema estabilizar (aí entra Alembic), ou alguém precisar ler estes dados
pela API. Aí entra uma view em `public` com `security_invoker = true`, nunca o schema inteiro.

---

## D22 · O roteiro do cliente é a fonte

[`script-chatbot-ze-matricula.md`](script-chatbot-ze-matricula.md) é o roteiro de fluxo
enxuto, como veio de produto, e a conversa segue a ordem dele. Houve uma reescrita
intermediária ("v2") sobre a régua do processo 195/2025; ela foi revertida como documento no
commit `f03b275`, e o que sobreviveu está **no código e neste registro**, não num segundo
roteiro.

**Por quê.** Dois roteiros lado a lado é o mesmo problema de dois esquemas de banco: um dos
dois mente, e não dá para saber qual sem abrir os dois.

**O que a "v2" deixou:** CPF do responsável (D12), CEP + número (D13), régua como dado (D15),
bloco C de acompanhamento (D14) e a recusa da nota de corte (D5).

**Onde o código diverge, de propósito:** cinco desvios e duas perguntas a mais, listados em
[ROTEIRO.md](ROTEIRO.md#onde-o-código-não-segue-o-roteiro-e-por-quê).

**Mudaria se** produto reescrever o roteiro. Aí o documento muda primeiro e o código
persegue, nunca o contrário.

---

## D23 · As colunas do espelho consultável seguem as perguntas do roteiro

**Decisão.** `Cadastro` (em `dados/porta.py`, contrato congelado) tem uma coluna por dado que
alguma pergunta do roteiro preenche, e nenhuma a mais. Quando o roteiro voltou ao fluxo enxuto
([D22](#d22--o-roteiro-do-cliente-é-a-fonte)), saíram `sexo` e `relacao`, entrou `origem`, e
`documento_crianca` passou a receber o CPF que o bloco 1 pede — antes esse dado era coletado e
descartado na projeção. `PreferenciaEscola` ganhou `chance`.

**Por quê.** Coluna que nenhuma pergunta preenche vira barra em zero no painel: parece abandono
da família e é desalinhamento nosso. O contrário é pior — o bot perguntava o CPF da criança, a
pessoa respondia, e o dado não chegava a lugar nenhum consultável.

**Por que a chance vai junto.** `preferencia_escola` existe para guardar **o fato que estava na
tela** no momento da escolha, e a chance estimada é o número que mais pesa na decisão. Era o
único da tela que não sobrevivia ao turno: distância e concorrência ficavam congeladas, a chance
seria recalculada com os CSVs do ano seguinte. O painel agora mostra as duas lado a lado — a que
a família leu e a de hoje — e a divergência entre elas é o sinal de que o chão mudou. Ver
[D19](#d19--a-chance-estimada-entra-a-classificação-continua-fora).

**O que continua fora, e não é esquecimento.** Dado de saúde (`tem_especial`,
`deficiencia_responsavel`) nunca vira coluna: vai para `resposta_criterio` como código +
booleano, com a marca de sensível ([D7](#d7--dado-sensível-consentimento-separado-um-turno-só-nunca-ecoado)).
Número de matrícula, data de nascimento do responsável e segundo telefone também ficam fora —
são PII sem pergunta analítica que os justifique, e minimização vale para o espelho como vale
para o resto.

**Testado.** Um teste anda o cadastro inteiro pelo bot e falha se sobrar coluna vazia: é ele
que impede o desalinhamento de voltar na próxima mudança de roteiro.

**Custo.** Mudança em contrato congelado, e um `ALTER TABLE` idempotente no bloco de schema
para alcançar banco que já existe — o preço de não ter Alembic ([D21](#d21--postgres-no-supabase-em-schema-próprio-sem-orm)).
