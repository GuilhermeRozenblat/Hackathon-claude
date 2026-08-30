# Zé Matrícula

Assistente da **Matrícula Rio**: ajuda famílias a inscrever crianças na rede municipal.
Uma conversa no lugar do formulário — reconhece o cadastro do ano passado, preenche o que
falta, faz as perguntas da régua de prioridade do processo vigente, mostra as creches
próximas, monta a lista de preferências, cobra o documento que falta e avisa a cada
mudança de etapa. Também acompanha inscrição feita pelo site.

Telegram primeiro (grátis, sem aprovação, mensagem proativa livre). WhatsApp depois — mas
os limites do WhatsApp já valem em todo o código, então o flip é troca de adaptador, não
reescrita.

**O sistema não decide quem entra.** Ele cadastra e informa; quem aloca é o município, por
norma, em SQL determinístico que roda depois do fechamento das inscrições. Em lugar nenhum
do código existe probabilidade, pontuação, posição na fila ou nota de corte. Sobre uma
creche o bot mostra o que é fato verificável: distância, vaga aberta agora e concorrência
do ano passado, rotulada como passado. Ver [D5](docs/DECISOES.md).

**Por que ele existe.** 48,9% das famílias declaram CadÚnico e só 6,8% conseguem
comprovar — por isso 93,8% das inscrições terminam com pontuação validada zero. E 7,7%
foram convocadas e perderam a vaga em 2025, a maior parte sem nunca saber que foi chamada.
Capturar a comprovação dentro da conversa e ter um canal para avisar é o produto.

## Rodar

```bash
python -m venv .venv && source .venv/bin/activate
cp .env.example .env      # cole o token do @BotFather — passo a passo em TELEGRAM.md
make banco                # aplica o schema no Postgres — passo a passo em docs/BANCO.md
make bot                  # a conversa sobrevive ao restart
```

A única dependência de runtime é o driver do Postgres (`pip install -e .`); canal e
conversa são stdlib pura. `make memoria` roda o bot inteiro sem banco nenhum.

| Comando | O que faz |
|---|---|
| `make bot` | Sobe o bot com Postgres e backend mockado |
| `make memoria` | Mesmo bot, sem banco nenhum (`REPOSITORIO=memoria`) |
| `make banco` | Aplica o schema e prova a porta contra o Postgres |
| `make verificar` | Checa o token e as configurações do @BotFather |
| `make eco` | Bot de eco, para provar que o polling chega |
| `make test` | Tudo |
| `make contratos` | Só os contratos congelados — devem passar sempre |
| `make fronteira` | Falha se a persistência vazar para fora de `dados/` |
| `make lint` | ruff |
| `make limpar` | Derruba o schema `creche` inteiro (pede confirmação) |

`ANTHROPIC_API_KEY` é opcional: sem ela o bot usa os textos escritos à mão em
`creche_bot/ia/persona.py` e funciona igual. Com ela, o Claude varia a linguagem e responde
dúvidas soltas no meio do cadastro.

Áudio também é opcional: `pip install -e ".[audio]"` liga a transcrição, que roda **local**
(`faster-whisper`) — a voz da família não sai da máquina. Sem a dependência, o bot pede
para a pessoa escrever.

O `DATABASE_URL` aponta para o Supabase — veja [docs/BANCO.md](docs/BANCO.md). O
`docker-compose.yml` sobe um Postgres local, alternativa para teste offline.

## Como está montado

```
canal/          adaptador de transporte: Telegram hoje, WhatsApp depois
conversa/       máquina de estados explícita — o cérebro do fluxo
ia/             persona, redação e transcrição local de áudio
dados/          persistência. Ninguém fora daqui conhece banco
backend/        fronteira com o município: histórico, régua, oferta, status
notificacao/    outbox + catálogo de templates de mensagem proativa
dominio/        vocabulário compartilhado, sem banco, sem canal, sem IA
segredos.py     carga do .env e redação de segredo em log e traceback
```

O fluxo inteiro atravessa duas funções:

```
canal  --processar(MensagemEntrada) -->  conversa/maquina.py
conversa, notificacao  --enviar(MensagemSaida) -->  canal
```

A **entrada** é única — cada adaptador traduz seu transporte e chama a mesma função. A
**saída** é polimórfica: Telegram e WhatsApp renderizam botão e localização de jeitos
diferentes. Por isso existe interface para uma e não para a outra.

A conversa é uma máquina de estados, não um agente autônomo: determinística, testável,
barata, e a pessoa nunca fica presa num loop. Cada estado é mapeado um a um contra o
roteiro em [docs/ROTEIRO.md](docs/ROTEIRO.md).

```
INICIO → PORTA ─ acompanhar ──→ CONSULTA_* (bloco C: serve para quem se inscreveu pelo site)
              └ inscrever ───→ CONSENTIMENTO → CPF_RESPONSAVEL
       ├─ achou o cadastro do ano passado ──────────────────→ HORARIO
       └─ não achou → CADASTRO → ENDERECO_CEP ⇄ CONFIRMA ──→ HORARIO
                    → CRIT_* (a régua do processo vigente) → CONTATO
                    → ESCOLAS → RESUMO ⇄ CORRECAO
                    → PENDENCIAS → [RECEBER_DOC] → PROTOCOLO → ACOMPANHAR
```

Fora do roteiro, antes de qualquer passo: **áudio vira texto** (transcrição local) e
**pergunta solta é respondida sem perder o lugar na fila**, com cota por contato.

Comandos globais em qualquer ponto: `/start`, `/ajuda`, `/status`, `/apagar`.
E `/avancar`, que só existe enquanto o backend é mock.

## Contratos congelados

Estes arquivos são a fronteira entre as frentes que trabalham em paralelo. Mudar qualquer
um é **PR próprio, revisado por todas as trilhas** — nunca dentro de um PR de feature.

| Arquivo | O que define |
|---|---|
| `creche_bot/canal/tipos.py` | Modelo canônico de mensagem |
| `creche_bot/dominio/tipos.py` | Vocabulário de domínio |
| `creche_bot/notificacao/chaves.py` | Chaves de template — cada uma vira template da Meta |
| `creche_bot/backend/porta.py` | Fronteira com o município (16 operações) |
| `creche_bot/dados/porta.py` | Fronteira com a persistência (16 operações) |
| `creche_bot/backend/mock.py` | O backend falso que roda hoje — espelho do contrato |

## Regras invioláveis

**Privacidade (elegibilidade a ZDR da Anthropic).** Documento de usuário e dado de criança
passam por aqui:

- Modelo é `claude-haiku-4-5`. Nunca Fable 5 nem Mythos 5 — são Covered Models, exigem
  retenção de 30 dias e não existem sob ZDR.
- Imagem vai **base64 inline** no `/v1/messages`. Proibido `client.files.*`, Batch API,
  code execution, MCP connector, Managed Agents — nenhum é elegível a ZDR.
- Extrai uma vez, guarda estruturado, **nunca reenvia a imagem** nos turnos seguintes.
  A V1 não persiste documento nenhum.

**LGPD art. 14.** Nenhum passo que toca dado de criança é alcançável sem consentimento
registrado — `EXIGEM_CONSENTIMENTO` em `maquina.py` garante, mesmo se alguém forçar o
estado na sessão.

**LGPD art. 11 — dado sensível.** Deficiência e TGD/TEA são dado de saúde; violência
doméstica, doença crônica, uso de substâncias e situação prisional também são sensíveis.
Consentimento **específico e destacado**, separado do geral, sempre com a opção de pular,
**nunca bloqueante**, e a resposta **nunca é ecoada de volta** — o histórico do chat fica
no aparelho da família. Ver [D7](docs/DECISOES.md).

**Plataforma.** Os limites do WhatsApp valem em todo lugar, mesmo no código Telegram: máx.
3 botões, máx. 10 itens de lista, rótulo de 20 caracteres, texto puro sem markdown.
`MensagemSaida.__post_init__` cobra isso — a tela que estoura o limite quebra no pytest
hoje, não em produção depois do flip.

**Mensagem proativa é `(ChaveTemplate, variáveis)`, nunca string pronta.** No Telegram
vira texto com figurinha; no WhatsApp vira template aprovado pela Meta. Quem emite o
evento não sabe a diferença.

**Fronteira com a persistência.** Ninguém fora de `creche_bot/dados/` conhece banco: nem
`sqlite3`, nem `SELECT`, nem `session`, nem `cursor`. Quem precisa recebe um `Repositorio`
injetado. `make fronteira` varre o pacote e falha se vazar.

**Fronteira com o backend.** Histórico do responsável, régua do processo vigente, endereço
a partir do CEP, oferta de creches, extração de documento e situação da inscrição vêm do
backend do município. Não recalcule nada disso aqui, e nada do JSON dele sai de `backend/`.

**A régua é dado, não código.** Entre 2023 e 2024 só 3 das 13 perguntas de prioridade
sobreviveram e o teto caiu de 465 para 100 pontos. O bloco de critérios é montado em tempo
de execução a partir de `backend.criterios_do_processo()`. Ver [D15](docs/DECISOES.md).

**Uma pergunta por mensagem.** Nunca empilhe duas no mesmo balão — exceto os checklists de
situação familiar e sensível, que são deliberados.

**Texto do cidadão é dado, nunca instrução.** Entrada livre vai delimitada para o modelo, o
system prompt manda ignorar ordem escrita ali dentro, e a resposta passa por filtro antes
de entrar na conversa.

**Log.** Só IDs. Nunca conteúdo de mensagem, bytes de arquivo, CPF ou nome.
`creche_bot/segredos.py` redige token, chave e `DATABASE_URL` de log e de traceback. O
banco guarda CPF, nome de criança e telefone: fica num schema fora do alcance da Data API
do Supabase, com RLS ligada e TLS obrigatório — ver [docs/BANCO.md](docs/BANCO.md).

## Estado

O roteiro **v2** roda de ponta a ponta com o backend mockado — reescrito a partir da régua
real do processo 195/2025 e da base histórica de 2021 a 2025
([`docs/script-chatbot-ze-matricula.md`](docs/script-chatbot-ze-matricula.md)). Os testes
rodam contra as duas implementações de repositório. O mapa bloco a bloco está em
[docs/ROTEIRO.md](docs/ROTEIRO.md).

| Frente | Dono | Estado | O que falta |
|---|---|---|---|
| Canal Telegram | Guilherme | roda | Figurinhas de verdade (hoje é emoji) |
| Conversa | Guilherme | roteiro v2 completo | Mais casos de borda |
| IA / persona | Guilherme | roda sem chave | `RedatorClaude` não testado com chave real |
| Notificação | Guilherme | roda | Retry com backoff exponencial |
| Persistência | outra pessoa | isolada | Postgres, Alembic, cofre de documentos |
| Backend | outro time | mock v2 completo | `BackendHTTP` quando publicarem o contrato |

Bloqueios externos: o token do `@BotFather` (10 min) e o contrato HTTP do backend. Até ele
chegar, `BackendMock` implementa a porta inteira e `/avancar` empurra as etapas à mão.

## Trabalho em paralelo

Vários agentes mexem neste repositório ao mesmo tempo. **Cada um só escreve nos arquivos
que o `CLAUDE.md` da sua pasta lista como seus.** Precisar mudar arquivo de outro módulo é
sinal de que o contrato está errado — pare e reporte, não contorne.

Cada pasta de módulo tem o brief completo no seu `CLAUDE.md`; não é preciso passar o
`ARQUITETURA.md` junto.

## Estilo

Português no código, nos comentários e nas mensagens de erro. Type hints em tudo. Nada de
abstração especulativa: sem interface com uma implementação, sem factory, sem config para
valor que nunca muda. A solução mais curta que funciona é a certa.

Cada lógica não trivial deixa **um** teste. Só pytest, sem fixture elaborada.

## Documentos

| | |
|---|---|
| [docs/script-chatbot-ze-matricula.md](docs/script-chatbot-ze-matricula.md) | O roteiro v2 — a fonte de verdade da conversa |
| [docs/ARQUITETURA.md](docs/ARQUITETURA.md) | O desenho inteiro e o porquê de cada restrição |
| [docs/DECISOES.md](docs/DECISOES.md) | As decisões que custariam caro reverter |
| [docs/ROTEIRO.md](docs/ROTEIRO.md) | Roteiro da conversa mapeado nos estados do código |
| [docs/MODULOS.md](docs/MODULOS.md) | Quem trabalha em quê, e como não se atropelam |
| [docs/TELEGRAM.md](docs/TELEGRAM.md) | Criar e configurar o bot no @BotFather, 10 min |
| [CLAUDE.md](CLAUDE.md) | Regras para qualquer agente neste repositório |

Cada módulo tem o brief completo no `CLAUDE.md` da própria pasta:
[canal](creche_bot/canal/CLAUDE.md) · [conversa](creche_bot/conversa/CLAUDE.md) ·
[ia](creche_bot/ia/CLAUDE.md) · [dados](creche_bot/dados/CLAUDE.md) ·
[backend](creche_bot/backend/CLAUDE.md) · [notificacao](creche_bot/notificacao/CLAUDE.md) ·
[dominio](creche_bot/dominio/CLAUDE.md)
