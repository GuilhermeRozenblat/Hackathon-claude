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

**Decisão.** `creche_bot/backend/porta.py` define 8 operações. `BackendMock` roda hoje;
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

**Decisão.** `creche_bot/dados/porta.py`, 16 operações, duas implementações
(`RepositorioMemoria` e `RepositorioSQLite`). Fora dessa pasta não existe `sqlite3`,
`SELECT`, `cursor` nem `session` — e há teste que varre o pacote e falha se aparecer.

**Por quê.** Essa pasta é trabalhada em paralelo por outra pessoa, que vai conectar o
Postgres. Sem a fronteira, uma refatoração no banco bloqueia quem mexe no chat.

**Consequência prática.** `REPOSITORIO=memoria make bot` roda o bot inteiro sem tocar em
disco. O trabalho de canal e conversa nunca depende do estado de `dados/`.

**Recusado.** Repositório por entidade, UnitOfWork, CRUD genérico. Uma porta, duas
implementações, e os 43 testes rodam parametrizados contra as duas.

---

## D4 · Vocabulário aberto, comportamento fechado

**Decisão.** `Etapa.codigo` é `str` livre — o município define quais etapas existem.
`Etapa.tipo` é `Literal` de cinco valores — nós definimos o que fazer com cada uma. A
tradução `codigo → tipo` mora numa tabela só, em `backend/http.py`, com default
`"aguardando"`.

**Por quê.** O vocabulário do município muda e varia por rede; o comportamento do bot é
pequeno e estável. Separar os dois faz etapa nova funcionar sem código novo.

**O default é `"aguardando"` de propósito.** Etapa desconhecida faz o bot avisar que
andou, sem inventar cobrança. Mandar a família à creche à toa é o erro caro.

---

## D5 · Concorrência virou nota de corte, e nenhuma vira probabilidade

**Decisão.** O painel mostra a nota de corte com o **ano** obrigatório no tipo
(`NotaCorte.ano`). Não existe "probabilidade de conseguir a vaga" em lugar nenhum.

**Por quê.** O sistema não seleciona quem entra — quem aloca é o município. Prever
admissão seria inventar um número com cara de modelo. E a nota de corte sozinha não diz a
chance da família, porque ela não conhece a própria pontuação: por isso o campo `ano` é
obrigatório e a UI é forçada a dizer de quando é o número.

**A faixa 💚/💛/🧡 é relativa à lista mostrada**, nunca absoluta. Ela ordena as três
opções entre si, não promete nada sobre nenhuma.

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

## D7 · Dado de saúde tem consentimento separado

**Decisão.** A pergunta sobre deficiência/TGD/TEA é precedida por um consentimento
específico (`CONSENTIMENTO_SENSIVEL`) e sempre oferece "Prefiro não dizer".

**Por quê.** LGPD art. 5º II e art. 11: dado de saúde é **dado pessoal sensível** e exige
consentimento específico e destacado. Não pode vir embutido no consentimento geral do
início da conversa.

**Também é UX.** A família entende por que a pergunta existe (a rede reserva atendimento
especializado) e sabe que pode não responder.

---

## D8 · Blocos 2, 3 e 4 são dados, não código

**Decisão.** `conversa/formulario.py` é uma tupla de `Campo`. A máquina caminha a lista.
Ramificação é `pular_se`, uma lambda por campo.

**Por quê.** "Uma pergunta por mensagem" é literalmente uma lista de perguntas. Como
código seriam 12 handlers quase idênticos. E produto vai reescrever esses textos toda
semana, sem tocar em lógica.

**Bônus.** `Campo.__post_init__` cobra o limite de 3 opções, então uma pergunta com 4
respostas fechadas quebra na importação — foi o que forçou dividir "já estuda em alguma
escola?" em duas perguntas.

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
