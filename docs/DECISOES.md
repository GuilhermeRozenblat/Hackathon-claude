# Registro de decisões

Uma entrada por decisão que custaria caro reverter. Formato: o que foi decidido, por quê,
o que foi recusado, e o que faria a gente mudar de ideia.

Decisões pequenas ficam no código, como comentário `ponytail:` nomeando o teto e o
caminho de upgrade. `grep -rn "ponytail:" creche_bot/` lista todas.

---

## D1 · Os limites do WhatsApp valem em todo o código, desde o Telegram

**Decisão.** `MensagemSaida.__post_init__` recusa mais de 3 botões, mais de 10 itens de
lista, rótulo acima de 20 caracteres e markdown. Vale igual no código do Telegram, que
aceitaria muito mais.

**Por quê.** O flip Telegram → WhatsApp é requisito, não desejo. Se o fluxo for desenhado
com a folga do Telegram, o flip vira reescrita da conversa inteira. Com a trava, um fluxo
grande demais quebra no `pytest` local hoje.

**Já se pagou duas vezes.** Rejeitou `Creche Jardim das Flores` (24 caracteres) e forçou o
redesenho do painel de escolas, que queria 5 botões (§D6).

**Recusado.** Validar só no adapter do WhatsApp: erro apareceria três meses depois, com o
fluxo todo construído em cima da premissa errada.

**Mudaria se.** O produto abandonasse o WhatsApp.

---

## D2 · A extração e os dados do município ficam atrás de uma porta

**Decisão.** `creche_bot/backend/porta.py` define 17 operações, agrupadas em processo
(período, resultado, data de corte, régua), histórico, endereço, oferta (escolas próximas e
panorama da região), inscrição, consulta e notificação. `BackendMapa` roda hoje;
`BackendHTTP` entra quando o outro time publicar. Nada do JSON deles sai de `backend/`.

**Por quê.** O backend é construído por outro time, em outra máquina. Sem camada
anticorrupção, o nome de campo deles vira dependência de `conversa/`, e a primeira
renomeação quebra o bot.

**Recusado.** Chamar o HTTP direto dos passos. Economiza um arquivo e custa toda vez que
o contrato do outro lado muda.

**Mudaria se.** O backend passasse a orquestrar a própria conversa — aí a fronteira muda
de lugar, e vale conversar antes.

---

## D3 · A persistência fica atrás de outra porta, com dono próprio

**Decisão.** `creche_bot/dados/porta.py`, 21 operações, duas implementações
(`RepositorioMemoria` e `RepositorioPostgres` — ver [D18](#d18--postgres-no-supabase-em-schema-próprio-sem-orm)).
Fora dessa pasta não existe `sqlite3`, `psycopg`, `SELECT`, `cursor` nem `session` — e há
teste que varre o pacote e falha se aparecer.

**Por quê.** Essa pasta é trabalhada em paralelo por outra pessoa, que vai conectar o
Postgres. Sem a fronteira, uma refatoração no banco bloqueia quem mexe no chat.

**Consequência prática.** `REPOSITORIO=memoria make bot` roda o bot inteiro sem tocar em
disco. O trabalho de canal e conversa nunca depende do estado de `dados/`.

**Recusado.** Repositório por entidade, UnitOfWork, CRUD genérico. Uma porta, duas
implementações, e a bateria roda parametrizada contra as duas.

---

## D4 · Vocabulário aberto, comportamento fechado

**Decisão.** `Etapa.codigo` é `str` livre — o município define quais etapas existem.
`Etapa.tipo` é `Literal` de seis valores — nós definimos o que fazer com cada uma. A
tradução `codigo → tipo` mora numa tabela só, em `backend/http.py`, com default
`"aguardando"`.

**Por quê.** O vocabulário do município muda e varia por rede; o comportamento do bot é
pequeno e estável. Separar os dois faz etapa nova funcionar sem código novo.

**O default é `"aguardando"` de propósito.** Etapa desconhecida faz o bot avisar que
andou, sem inventar cobrança. Mandar a família à creche à toa é o erro caro.

---

## D5 · Nem nota de corte, nem pontuação, nem posição na fila

> **Revisto em 30/08/2026 — ver [D19](#d19--a-chance-estimada-entra-a-classificação-continua-fora).**
> A chance estimada por creche passou a aparecer. O resto desta decisão continua valendo
> inteiro: pontuação, nota de corte e posição na fila seguem fora do código.

**Decisão.** Sobre uma creche o bot mostra **distância**, **vaga ociosa agora** e
**concorrência do ano passado** (`Concorrencia.familias_por_vaga`, com `ano` obrigatório no
tipo). Não existe pontuação nem posição na fila em lugar nenhum do código.

**Por quê.** O sistema não seleciona quem entra — quem aloca é o município, por norma
(Resolução SME nº 542/2025), em SQL determinístico que roda **depois do fechamento das
inscrições**. No momento da conversa a classificação literalmente não existe.

**Por que caiu a nota de corte da v1.** Ela é a pontuação do último aprovado, e o teto da
régua foi 465 pontos em 2023 e 100 em 2024: histórico de pontuação não é comparável entre
anos. "5 famílias por vaga no ano passado" é fato verificável; "nota de corte 87" é um
número sem régua.

**Posição na fila também não.** A classificação é por critério, não por ordem de chegada,
e a posição muda conforme outras famílias comprovam documento. Prometer número é criar
expectativa que a SME não pode honrar.

**O que substitui.** Na consulta, o que aparece é o que é **acionável**: o que falta
comprovar. Ver [D14](#d14--a-família-vê-um-desfecho-nunca-a-situação-bruta-por-opção).

**Testado.** Um teste varre o roteiro inteiro e falha se "garantido", "com certeza" ou
"vai conseguir" aparecer em qualquer tela.

---

## D6 · Seleção múltipla ordenada, construída em três toques

**Decisão.** O roteiro pede "seleção múltipla ordenável". O WhatsApp não tem esse widget.
A ordem é montada incrementalmente: cada toque acrescenta uma preferência, o bot confirma
a posição e mostra o que sobrou. Toda tela cabe em 3 botões (restantes + "Pronto").

**Por quê.** É a única forma que funciona nas duas plataformas. E acabou ficando melhor:
a pessoa vê a ordem se formando, em vez de arrastar itens numa lista.

**Recusado.** Pedir a ordem por texto ("responda 1,3,2"): taxa de erro alta e péssimo no
celular.

---

## D7 · Dado sensível: consentimento separado, um turno só, e nunca ecoado

**Decisão.** Três regras para os critérios marcados `Criterio.sensivel`:

1. **Consentimento próprio** (`CONSENTIMENTO_SENSIVEL`), pedido no bloco 8.4, separado do
   consentimento geral do bloco 1 e só para quem chega lá. "Prefiro pular" é sempre uma
   opção.
2. **As cinco perguntas do 8.4 num turno só**, como checklist. É a exceção deliberada à
   regra de uma pergunta por mensagem.
3. **Nunca ecoar a resposta de volta.** O eco de confirmação vale para CPF, nome e
   telefone; não vale para isto.

**Por quê (1).** LGPD art. 5º II e art. 11: violência doméstica, doença crônica, uso de
substâncias e situação prisional são dado pessoal sensível e exigem consentimento
específico e destacado. Sem base legal isso não pode nem ser gravado.

**Por quê (2).** Individualmente essas perguntas disparam entre 1,6% e 5,3%; somadas,
13,6% marcam ao menos uma, com média de 0,18 marcações. Cinco turnos invasivos para esse
aproveitamento é péssimo desenho.

**Por quê (3).** O histórico do chat fica no aparelho da família, que pode ser o mesmo
aparelho do agressor. "Recebido: alguém de casa está preso ✅" é um risco que o eco não
compra nada para justificar.

**E nunca bloqueia.** `Criterio.documento_opcional` marca violência, substâncias e
situação prisional: exigir boletim de ocorrência de uma vítima dentro de um chat, como
condição para inscrever a criança, é violento.

---

## D8 · Os blocos de cadastro são dados, não código

**Decisão.** `conversa/formulario.py` é uma tupla de `Campo` por lista — `CADASTRO`
(blocos 3, 4 e 5), `CONTATO` (bloco 9) e `CONSULTA` (bloco C.1). A máquina caminha a
lista. Ramificação é `pular_se`, uma lambda por campo.

**Por quê.** "Uma pergunta por mensagem" é literalmente uma lista de perguntas. Como
código seriam 15 handlers quase idênticos. E produto vai reescrever esses textos toda
semana, sem tocar em lógica.

**Bônus.** `Campo.__post_init__` cobra o limite de 3 opções, então uma pergunta com 4
respostas fechadas quebra na importação — foi o que forçou dividir "qual a sua relação com
a criança?" em duas perguntas, porque `Relacao` tem cinco valores.

**O bloco 8 não entra aqui.** A régua do processo é dado do backend, não do repositório —
ver [D15](#d15--a-régua-do-processo-é-dado-do-backend-nunca-código).

---

## D9 · Rodar não exige dependência nenhuma

**Decisão.** `urllib` da stdlib no lugar de `python-telegram-bot`; `sqlite3` no lugar de
Postgres + Docker; e a V1 **não persiste documento** — extrai, guarda estruturado,
descarta os bytes.

**Por quê.** A meta imediata é validar o bot no Telegram. Docker, venv e `pip install`
são atrito que não compra nada hoje. `python -m creche_bot` funciona depois do `git clone`.

`python-telegram-bot` é async-first e contaminaria `conversa/`, `ia/` e `dados/` inteiras;
a Bot API que usamos são 6 métodos HTTP.

Não persistir documento não é preguiça: é a regra de minimização (§2.2 da arquitetura), e
de quebra elimina a dependência de criptografia.

**Marcado no código.** Cada uma tem comentário `ponytail:` nomeando o teto e o upgrade.

**Mudaria se.** Mais de um processo escrevendo (Postgres), webhook com concorrência real
(framework async), ou a creche exigir o documento original (cofre cifrado).

---

## D10 · A lacuna do CRAS é dita, não escondida

**Decisão.** Quando a família escolhe entregar no CRAS, o bot avisa explicitamente que os
documentos ainda seguem para a creche, que isso leva alguns dias, e que ele avisa quando a
creche confirmar.

**Por quê.** O processo hoje não tem esse retorno — foi apontado no próprio roteiro. Não
dá para inventar a integração, mas dá para não deixar a família no escuro depois de
entregar os documentos e não receber notícia nenhuma.

**Pendência real, não de código.** Fechar esse retorno com CRAS/Poupa Tempo é trabalho de
processo. A etapa já está modelada e o texto já é honesto; quando a confirmação existir,
ela entra como mais uma etapa do backend, sem código novo (§D4).

**Testado.** Um teste garante que o aviso continua no texto.

---

## D11 · Segredo não chega ao log, nem por traceback

**Decisão.** `creche_bot/segredos.py` instala um `FormatadorSeguro` que substitui o valor
de `TELEGRAM_TOKEN`, `ANTHROPIC_API_KEY`, `DATABASE_URL` e `FERNET_KEY` por `***` em
mensagem **e** em traceback. O `creche.db` nasce com permissão `600`.

**Por quê.** O token do Telegram viaja no **caminho da URL** da Bot API
(`api.telegram.org/bot<TOKEN>/getUpdates`). Um traceback de `urllib` traz a URL inteira —
basta ele cair no console, no CI ou num print colado no chat da equipe para o token vazar.
Quem tem o token controla o bot, e o bot conversa com famílias sobre documentos de
crianças.

O banco guarda CPF, nome de criança e telefone: `600` impede que outro usuário da mesma
máquina leia o arquivo.

**Detalhe que importa.** Segredo com menos de 12 caracteres é ignorado pelo formatador —
apagar toda ocorrência de uma string curta destruiria log legítimo.

**Recusado.** Confiar em "ninguém vai logar isso". Vazamento de segredo por log é o modo
de falha mais comum que existe, justamente porque ninguém o escreve de propósito.

---

## D12 · A conta começa no CPF do responsável, não no da criança

**Decisão.** A primeira pergunta depois do consentimento é o CPF do **adulto**, e é ele a
âncora da conta: `backend.buscar_por_responsavel(cpf)`. O documento da criança (CPF, DNV
ou NIS, nessa ordem de precedência) vem depois, no bloco 5, e **nenhum dos três é
obrigatório** — sem eles a inscrição segue, marcada para conferência.

**Por quê.** Exigir CPF de criança de 0 a 3 anos no primeiro turno derruba família na
porta. O CPF do adulto é mais confiável, é o que a pessoa tem na mão, e é o único que
reconhece reinscrição e irmãos.

**O que isso destrava.** 27,9% das crianças de 2025 já constavam em 2024: o histórico
preenche o cadastro inteiro num turno (bloco 2a) e ainda auto-valida o critério "esperou
na fila no ano anterior" — hoje 14,5% declaram e só 12,1% comprovam. E 1.738 responsáveis
inscreveram duas ou mais crianças: "É outra criança" reaproveita responsável e endereço.

**Recusado.** CPF da criança + data de nascimento como chave (era a v1). Trocava um
cadastro achado por um formulário inteiro, para a maioria das famílias.

---

## D13 · Endereço só por CEP + número. Bairro nunca é digitado

**Decisão.** `backend.resolver_cep(cep, numero)` devolve logradouro, bairro e coordenadas.
A família vê o bairro **uma vez, para confirmar**, e nunca digita nenhum dos dois.

**Por quê.** Na base histórica o campo livre gerou 1.608 grafias para ~925 bairros —
"Inhaúma" sozinho tem 13 variantes. O CEP é 100% preenchido e 100% válido desde 2024.

**Por que o número é obrigatório.** Sem ele a precisão cai para ~1,4 km, o suficiente para
errar a creche certa dentro do raio de 2 km que as famílias aceitam (72,8% dos confirmados
ficaram na 1ª opção; entre os que trocaram, 82,9% andaram até 2 km).

**Mudaria se.** Aparecesse CEP de logradouro único cobrindo área grande demais o
suficiente para virar problema — aí entra confirmação por mapa, não campo de texto.

---

## D14 · A família vê um desfecho, nunca a situação bruta por opção

**Decisão.** O banco grava **uma situação por opção de creche**. A consulta calcula
`desfecho_entre(estados)` — a melhor situação da lista, por `PRECEDENCIA` — e mostra só
ela. Sete estados possíveis, sete telas.

**Por quê.** 77,8% das linhas `Cancelado pelo sistema` pertencem a inscrições que **foram
atendidas**: é o cancelamento automático das outras opções quando uma é preenchida. Uma
família que conseguiu a vaga veria "cancelado" em 4 das 5 escolhas dela. Mostrar o valor
cru quebra a confiança na hora.

**Detalhe que quebra query.** O valor gravado é `Cancelado na confirmacao` — sem cedilha e
sem til. Filtrar pela grafia correta devolve zero linhas.

**Onde isso vive.** `dominio/tipos.py`: `EstadoInscricao`, `PRECEDENCIA`,
`desfecho_entre()` e `Desfecho`. A tradução do vocabulário do banco para esses sete
estados é do backend, como toda tradução (§D2).

---

## D15 · A régua do processo é dado do backend, nunca código

**Decisão.** `backend.criterios_do_processo()` devolve uma lista de `Criterio` —
código, rótulo, pontos, grupo, se é sensível e o que comprova. O bloco 8 da conversa é
montado caminhando essa lista. Não existe enum de critério em `dominio/`.

**Por quê.** Entre 2023 e 2024 só **3 das 13 perguntas sobreviveram** e o teto caiu de 465
para 100 pontos. Régua escrita à mão quebra na virada do ano, e a virada acontece no meio
do período de inscrição, que é o pior momento possível.

**O que fica nosso.** A **forma** da pergunta (`FormaCriterio`: sim/não, múltipla, número,
anexo) e o desenho do turno. O **conteúdo** é do processo vigente.

**Já se pagou.** Para 2026 vale a Resolução SME nº 542/2025, ainda não carregada. Quando
carregar, é dado novo no backend — zero código aqui.

---

## D16 · Retomada em 72h, e chave de idempotência desde o primeiro turno

**Decisão.** Sessão viva por 72h (`entrada.VALIDADE_SESSAO`). Sessão viva não recomeça: o
bot diz onde parou e oferece continuar. `dados["chave_idempotencia"]` nasce no primeiro
turno e viaja até `backend.inscrever()`.

**Por quê.** Conversa de WhatsApp cai — o app fecha, o celular descarrega, a pessoa
responde no dia seguinte. Sem retomada ela recomeça do zero e desiste. Sem chave de
idempotência ela **entra duas vezes no processo**, e duas inscrições para a mesma criança
se anulam: é um dos motivos por trás dos 9,5% de "nenhuma opção seguiu".

**Consequência no código.** `BackendMock.inscrever()` devolve o mesmo número para a mesma
chave, e o `BackendHTTP` terá que fazer igual. `inscrever()` é a única operação da porta
que **nunca** pode ter retry automático.

---

## D17 · Dúvida solta é respondida, mas com cota — e o texto do cidadão é dado

**Decisão.** Mensagem classificada como `duvida` no meio do cadastro é respondida pelo
modelo sem mudar o estado da sessão: perguntar não faz perder o lugar na fila. Com dois
limites: **8 perguntas por hora por contato** (janela deslizante em memória) e um system
prompt (`SISTEMA_DUVIDA`) que declara o texto do usuário como dado, não instrução.

**Por quê a cota.** Cada dúvida é uma chamada paga. Um chat aberto na internet é um botão
de gastar dinheiro dos outros. Estourada a cota, a mensagem volta a ser tratada como
resposta do roteiro — o cadastro continua, só a IA descansa.

**Por quê o prompt.** O campo é aberto e alguém vai tentar dobrar o prompt. A defesa é
delimitar (`<pergunta>`), declarar que ali dentro é dado, e não mandar nada da família
para o modelo: só o nome da etapa. Ninguém precisa do CPF da criança para explicar como
funciona a fila.

**ponytail assumido.** O contador é um dicionário em memória, de um processo só —
marcado no código, com o `clear` que impede virar vazamento no dia do pico.

---

## D18 · Postgres no Supabase, em schema próprio, sem ORM

**Decisão.** `creche_bot/dados/postgres.py` com psycopg 3 e `ConnectionPool`, contra o
Postgres do Supabase pelo pooler em modo transação. As tabelas ficam no schema **`creche`**,
não no `public`. O `sqlite.py` da validação foi removido: sobraram as duas implementações
que o contrato prevê — `RepositorioMemoria` e `RepositorioPostgres`.

**Por que schema próprio.** No Supabase o `public` é servido pela Data API (PostgREST) a
quem tiver a chave anônima, e essa chave costuma acabar no front. Estas tabelas guardam
nome de criança e CPF. Um schema fora da lista de exposição não é alcançável pela API,
ponto — e isso não depende de ninguém lembrar de manter RLS restritiva numa tabela nova.
RLS fica ligada mesmo assim, sem política, e `anon`, `authenticated` e `service_role`
perdem acesso ao schema: segunda linha, não a primeira.

**Por que sem SQLAlchemy e sem Alembic.** São 21 métodos sobre onze tabelas, num arquivo
só, com uma implementação. Um ORM aqui é exatamente a abstração especulativa que o
`CLAUDE.md` proíbe, e migração versionada só paga quando o schema para de mudar toda
semana — até lá, DDL idempotente no boot custa menos. O `pyproject` deixou de listar os
dois.

**Consequência prática.** O bot passou a ter uma dependência de runtime (`psycopg`), o que
D9 evitava. `REPOSITORIO=memoria` continua rodando o bot inteiro sem banco, então a válvula
de escape de D3 sobrevive; o que se perdeu foi o `python -m creche_bot` funcionando logo
depois do `git clone`, sem `pip install`.

**Detalhes que custaram teste.** `prepare_threshold=None`, porque o pooler em modo
transação troca a conexão de servidor embaixo do processo e o prepared statement some;
`check=check_connection`, porque o pooler derruba conexão ociosa e o worker de outbox
pegaria uma morta; nome de tabela qualificado em toda query, porque um `SET search_path`
não sobrevive à troca de sessão; e savepoint em `contato_de()`, porque duas threads
escrevem e um contato duplicado faz a pessoa perder a conversa no meio.

**Recusado.** Deixar as tabelas em `public` com RLS restritiva. Funciona até alguém
adicionar uma política permissiva para destravar um dashboard — e aí o vazamento é de nome
de criança.

**Mudaria se.** O schema estabilizar (aí entra Alembic), ou alguém precisar ler estes dados
pela API — nesse caso, uma view em `public` com `security_invoker = true` expondo só as
colunas necessárias, nunca o schema inteiro.

---

## D19 · A chance estimada entra. A classificação continua fora

**Decisão.** O painel do bloco 10 mostra, para cada creche, uma **chance estimada** —
`confirmados ÷ demanda de 1ª opção` naquela unidade, no processo de 2025. Vem de
`backend/mapa.py`, sobre os CSVs de `creche_bot/MapaFilaCreche/`. É uma revisão parcial de
[D5](#d5--nem-nota-de-corte-nem-pontuação-nem-posição-na-fila): pontuação, nota de corte e
posição na fila continuam não existindo no código.

**Por quê.** A família decide entre creches, e "1,4 km" não é suficiente para decidir. O
dado que responde a pergunta dela existe e é observado, não inventado: das 820 unidades com
demanda em 2025, sabemos quantas famílias pediram cada uma como 1ª opção e quantas foram
atendidas. Esconder isso não deixava a família mais informada — deixava só mais ansiosa.

**Por que não é a nota de corte que D5 recusou.** A nota de corte é a pontuação do último
aprovado, e o teto da régua foi 465 pontos em 2023 e 100 em 2024 — número sem régua
comparável. A chance aqui é uma razão entre duas contagens do mesmo ano, ambas na base.

**As três condições que fazem isso ser honesto.**

1. **O ano vai colado no número**, em toda tela. Sem ele a estimativa vira previsão sobre o
   processo de agora, que é o que o bot não pode dizer. Há teste.
2. **Nunca 0% e nunca 100%** (`CHANCE_MIN`/`CHANCE_MAX`). Vaga ociosa hoje não garante vaga
   em fevereiro, e fila cheia no ano passado não fecha a porta deste ano.
3. **A classificação não está dentro dela**, e o rodapé diz isso. Duas famílias que veem
   40% na mesma tela podem ter desfechos opostos por causa da régua de prioridade — que
   roda em SQL determinístico depois do fechamento das inscrições e não existe durante a
   conversa.

**O que mudou no filtro.** `ia/redacao.py` deixou de barrar "probabilidade" e "chance", e
passou a barrar "está na frente". O que a lista protege continua sendo o salto de
estimativa para promessa: "garantido", "com certeza", "vai conseguir", "sua pontuação",
"posição na fila".

**Limitação conhecida, e é real.** A chance é medida sobre quem pediu a unidade como **1ª
opção**, porque é o recorte que a base tem. Quem coloca a creche em 2ª ou 3ª opção enfrenta
condição diferente, e o número na tela não distingue. O texto diz "contando quem a pediu
como 1a opção" justamente por isso.

**Mudaria se.** O backend do município publicar a classificação real, ou a base passar a
trazer demanda por posição de preferência — aí a estimativa deixa de ser necessária, ou
fica bem melhor.
