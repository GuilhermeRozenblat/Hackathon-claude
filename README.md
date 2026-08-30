# Zé Matrícula

Assistente da **Matrícula Rio**: ajuda famílias a inscrever crianças na rede municipal.
Uma conversa no lugar do formulário — consulta o cadastro que já existe, preenche o que
falta, mostra as creches próximas com a nota de corte de cada uma, monta a lista de
preferências e avisa a cada mudança de etapa.

Telegram primeiro (grátis, sem aprovação, mensagem proativa livre). WhatsApp depois — mas
os limites do WhatsApp já valem em todo o código, então o flip é troca de adaptador, não
reescrita.

**O sistema não decide quem entra.** Ele cadastra e informa; quem aloca é o município. Em
lugar nenhum do código existe "probabilidade de conseguir a vaga" — só a **nota de corte**
do ano passado, sempre acompanhada do ano, porque a família não conhece a própria
pontuação. Ver [D5](docs/DECISOES.md).

## Rodar

```bash
python -m venv .venv && source .venv/bin/activate
cp .env.example .env      # cole o token do @BotFather — passo a passo em TELEGRAM.md
make bot                  # sqlite: a conversa sobrevive ao restart
```

Subir o bot **não exige nenhuma dependência**: canal, banco e conversa usam só a stdlib.
`pip install -e ".[dev]"` só para rodar os testes.

| Comando | O que faz |
|---|---|
| `make bot` | Sobe o bot com sqlite (`creche.db`) e backend mockado |
| `make memoria` | Mesmo bot, sem tocar em disco (`REPOSITORIO=memoria`) |
| `make verificar` | Checa o token e as configurações do @BotFather |
| `make eco` | Bot de eco, para provar que o polling chega |
| `make test` | Tudo |
| `make contratos` | Só os contratos congelados — devem passar sempre |
| `make fronteira` | Falha se a persistência vazar para fora de `dados/` |
| `make lint` | ruff |
| `make limpar` | Apaga o `creche.db` |

`ANTHROPIC_API_KEY` é opcional: sem ela o bot usa os textos escritos à mão em
`creche_bot/ia/persona.py` e funciona igual. Com ela, o Claude varia a linguagem.

O `docker-compose.yml` sobe um Postgres para quem está migrando a persistência; o bot do
dia a dia não precisa dele.

## Como está montado

```
canal/          adaptador de transporte: Telegram hoje, WhatsApp depois
conversa/       máquina de estados explícita — o cérebro do fluxo
ia/             persona e redação (Claude opcional, ou texto fixo)
dados/          persistência. Ninguém fora daqui conhece banco
backend/        fronteira com o município: data lake, escolas, extração, status
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
barata, e a pessoa nunca fica presa num loop. São 13 estados, mapeados um a um contra o
roteiro em [docs/ROTEIRO.md](docs/ROTEIRO.md).

```
INICIO → CONSENTIMENTO → BUSCA_CPF → BUSCA_NASCIMENTO
       ├─ data lake achou ──────────────────────────→ RESUMO
       └─ não achou → FORMULARIO (blocos 2, 3 e 4) ──→ RESUMO ⇄ CORRECAO
                                    → LOCALIZACAO → ESCOLHA ⇄ CONFIRMA_ESCOLAS
                                    → ENTREGA → [RECEBER_DOCUMENTOS] → ACOMPANHAMENTO
```

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
| `creche_bot/backend/porta.py` | Fronteira com o município (8 operações) |
| `creche_bot/dados/porta.py` | Fronteira com a persistência (16 operações) |

## Regras invioláveis

**Privacidade (elegibilidade a ZDR da Anthropic).** Documento de usuário e dado de criança
passam por aqui:

- Modelo é `claude-opus-5`. Nunca Fable 5 nem Mythos 5 — são Covered Models, exigem
  retenção de 30 dias e não existem sob ZDR.
- Imagem vai **base64 inline** no `/v1/messages`. Proibido `client.files.*`, Batch API,
  code execution, MCP connector, Managed Agents — nenhum é elegível a ZDR.
- Extrai uma vez, guarda estruturado, **nunca reenvia a imagem** nos turnos seguintes.
  A V1 não persiste documento nenhum.

**LGPD art. 14.** Nenhum passo que toca dado de criança é alcançável sem consentimento
registrado — `EXIGEM_CONSENTIMENTO` em `maquina.py` garante, mesmo se alguém forçar o
estado na sessão.

**LGPD art. 11 — dado sensível.** Deficiência, TGD/TEA e altas habilidades são dado de
saúde: consentimento **específico e destacado**, separado do geral, e sempre com a opção
"Prefiro não dizer". Ver [D7](docs/DECISOES.md).

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

**Fronteira com o backend.** Data lake, escolas com nota de corte, extração de documento e
situação da inscrição vêm do backend do município. Não recalcule nada disso aqui, e nada
do JSON dele sai de `backend/`.

**Uma pergunta por mensagem.** Nunca empilhe duas no mesmo balão.

**Log.** Só IDs. Nunca conteúdo de mensagem, bytes de arquivo, CPF ou nome.
`creche_bot/segredos.py` redige token e chave de log e de traceback, e o `creche.db` nasce
com permissão `600` porque guarda CPF, nome de criança e telefone.

## Estado

O esqueleto roda de ponta a ponta com o backend mockado.

O roteiro inteiro roda de ponta a ponta com o backend mockado — 47 testes, contra as duas
implementações de repositório.

| Frente | Dono | Estado | O que falta |
|---|---|---|---|
| Canal Telegram | Guilherme | roda | Figurinhas de verdade (hoje é emoji) |
| Conversa | Guilherme | roteiro completo | Mais casos de borda |
| IA / persona | Guilherme | roda sem chave | `RedatorClaude` não testado com chave real |
| Notificação | Guilherme | roda | Retry com backoff exponencial |
| Persistência | outra pessoa | isolada | Postgres, Alembic, cofre de documentos |
| Backend | outro time | mock completo | `BackendHTTP` quando publicarem o contrato |

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
| [docs/ARQUITETURA.md](docs/ARQUITETURA.md) | O desenho inteiro e o porquê de cada restrição |
| [docs/DECISOES.md](docs/DECISOES.md) | As 10 decisões que custariam caro reverter |
| [docs/ROTEIRO.md](docs/ROTEIRO.md) | Roteiro da conversa mapeado nos 13 estados |
| [docs/MODULOS.md](docs/MODULOS.md) | Quem trabalha em quê, e como não se atropelam |
| [docs/TELEGRAM.md](docs/TELEGRAM.md) | Criar e configurar o bot no @BotFather, 10 min |
| [CLAUDE.md](CLAUDE.md) | Regras para qualquer agente neste repositório |

Cada módulo tem o brief completo no `CLAUDE.md` da própria pasta:
[canal](creche_bot/canal/CLAUDE.md) · [conversa](creche_bot/conversa/CLAUDE.md) ·
[ia](creche_bot/ia/CLAUDE.md) · [dados](creche_bot/dados/CLAUDE.md) ·
[backend](creche_bot/backend/CLAUDE.md) · [notificacao](creche_bot/notificacao/CLAUDE.md) ·
[dominio](creche_bot/dominio/CLAUDE.md)
