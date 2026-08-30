# Zé Matrícula

Assistente da **Matrícula Rio**: uma conversa no lugar do formulário de inscrição em creche
municipal. Reconhece o cadastro do ano passado, preenche o que falta, faz as perguntas da
régua de prioridade do processo vigente, mostra as creches próximas, monta a lista de
preferências, cobra o documento que falta e avisa a cada mudança de etapa. Também acompanha
inscrição feita pelo site.

Telegram primeiro (grátis, sem aprovação, mensagem proativa livre). WhatsApp depois — os
limites dele já valem em todo o código, então o flip é troca de adaptador, não reescrita.

**O sistema não decide quem entra.** Ele cadastra e informa; quem aloca é o município, por
norma, em SQL determinístico que roda depois do fechamento das inscrições. Em lugar nenhum
do código existe probabilidade, pontuação, posição na fila ou nota de corte. Sobre uma
creche o bot mostra o que é fato verificável: distância, vaga aberta agora e concorrência
do ano passado, rotulada como passado. Ver [D5](docs/DECISOES.md).

**Por que ele existe.** 48,9% das famílias declaram CadÚnico e só 6,8% conseguem comprovar
— por isso 93,8% das inscrições terminam com pontuação validada zero. E 7,7% foram
convocadas e perderam a vaga em 2025, a maior parte sem nunca saber que foi chamada.
Capturar a comprovação dentro da conversa e ter um canal para avisar é o produto.

## Rodar

```bash
python -m venv .venv && source .venv/bin/activate
cp .env.example .env      # cole o token do @BotFather — passo a passo em docs/TELEGRAM.md
make bot                  # sqlite: a conversa sobrevive ao restart
```

Subir o bot **não exige nenhuma dependência**: canal, banco e conversa usam só a stdlib.
`pip install -e ".[dev]"` é só para rodar os testes.

| Comando | O que faz |
|---|---|
| `make bot` · `make memoria` | Sobe o bot com sqlite (`creche.db`) · sem tocar em disco |
| `make debug` | Espelha a conversa no console — máquina de dev, nunca onde o log é coletado |
| `make verificar` · `make eco` | Confere o @BotFather · prova que o polling chega |
| `make test` · `make <trilha>` | Tudo · só `canal`, `conversa`, `ia`, `dados`, `backend` ou `notificacao` |
| `make contratos` | Os contratos congelados — devem passar sempre |
| `make fronteira` | Falha se a persistência vazar para fora de `dados/` |
| `make lint` · `make limpar` | ruff · apaga o `creche.db` |

Dois opcionais, e o bot roda inteiro sem os dois. **`ANTHROPIC_API_KEY`**: sem ela valem os
textos escritos à mão em `ia/persona.py` e a classificação por heurística; com ela o Claude
varia a linguagem, classifica cada mensagem digitada e responde dúvida solta.
**`pip install -e ".[audio]"`**: liga a transcrição, que roda **local** (`faster-whisper`) —
a voz da família não sai da máquina; sem ela o bot pede para a pessoa escrever.

O `docker-compose.yml` sobe um Postgres para quem está migrando a persistência; o bot do
dia a dia não precisa dele.

## Como está montado

```
canal/          adaptador de transporte: Telegram hoje, WhatsApp depois
conversa/       máquina de estados explícita — o cérebro do fluxo
ia/             persona, classificação e transcrição local de áudio
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

A entrada é única: cada adaptador traduz seu transporte e chama a mesma função. A saída é
polimórfica, porque Telegram e WhatsApp renderizam botão e localização diferente — por isso
existe interface para uma e não para a outra.

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

Antes de qualquer passo, e sem salvar estado: **áudio vira texto** (transcrição local) e
**toda mensagem digitada é classificada**. Dúvida é respondida sem perder o lugar na fila,
com cota por contato; mensagem que não responde a pergunta redesenha a tela em vez de
contar erro; o resto segue o roteiro. Ver [D17 e D18](docs/DECISOES.md).

Comandos globais em qualquer ponto: `/start`, `/ajuda`, `/status`, `/apagar`. E `/avancar`,
que só existe enquanto o backend é mock.

## Contratos congelados

A fronteira entre as frentes que trabalham em paralelo. Mudar qualquer um é **PR próprio,
revisado por todas as trilhas** — nunca dentro de um PR de feature.

| Arquivo | O que define |
|---|---|
| `canal/tipos.py` | Modelo canônico de mensagem |
| `dominio/tipos.py` | Vocabulário de domínio |
| `notificacao/chaves.py` | Chaves de template — cada uma vira template da Meta |
| `backend/porta.py` | Fronteira com o município (16 operações) |
| `dados/porta.py` | Fronteira com a persistência (16 operações) |
| `backend/mock.py` | O backend falso que roda hoje — espelho do contrato |

## Regras invioláveis

O texto completo, com o porquê de cada uma, está em [CLAUDE.md](CLAUDE.md).

- **Privacidade (elegibilidade a ZDR).** `claude-haiku-4-5`, nunca um Covered Model. Imagem
  base64 inline no `/v1/messages`; extrai uma vez, guarda estruturado, nunca reenvia — e a
  V1 não persiste documento. Proibido `client.files.*`, Batch API, code execution, MCP
  connector, Managed Agents.
- **Consentimento (LGPD art. 14).** Nenhum estado que toca dado de criança é alcançável sem
  ele: `EXIGEM_CONSENTIMENTO` cobra no código, não na confiança no fluxo.
- **Dado sensível (art. 11).** Consentimento próprio e destacado, sempre opcional, nunca
  bloqueante, e a resposta nunca é ecoada de volta. Ver [D7](docs/DECISOES.md).
- **Plataforma.** O limite do WhatsApp vale em todo lugar — 3 botões, 10 itens, rótulo de 20
  caracteres, texto puro. A tela que estoura quebra no pytest hoje, não em produção depois
  do flip.
- **Mensagem proativa é `(ChaveTemplate, variáveis)`,** nunca string pronta: no Telegram
  vira texto com figurinha, no WhatsApp vira template aprovado pela Meta.
- **Persistência isolada.** Fora de `dados/` ninguém conhece banco; quem precisa recebe um
  `Repositorio` injetado, e `make fronteira` varre e falha se vazar.
- **O backend é a fonte** de histórico, régua vigente, endereço a partir do CEP, oferta,
  extração de documento e status. Não recalcule aqui, e nada do JSON dele sai de `backend/`.
- **A régua é dado, não código.** De 2023 para 2024 sobraram 3 das 13 perguntas e o teto
  caiu de 465 para 100 pontos. Ver [D15](docs/DECISOES.md).
- **Uma pergunta por mensagem**, texto do cidadão é dado e nunca instrução, e no log só ID —
  nunca conteúdo, bytes, CPF ou nome.

## Estado

O roteiro **v2** roda de ponta a ponta com o backend mockado — reescrito a partir da régua
real do processo 195/2025 e da base histórica de 2021 a 2025
([`docs/script-chatbot-ze-matricula.md`](docs/script-chatbot-ze-matricula.md)). Os testes
rodam contra as duas implementações de repositório.

| Frente | Dono | Estado | O que falta |
|---|---|---|---|
| Canal Telegram | Guilherme | roda | Figurinhas de verdade (hoje é emoji) |
| Conversa | Guilherme | roteiro v2 completo | Mais casos de borda |
| IA / persona | Guilherme | roda sem chave | Afinar classificação e persona com chave real |
| Notificação | Guilherme | roda | Retry com backoff exponencial |
| Persistência | outra pessoa | isolada | Postgres, Alembic, cofre de documentos |
| Backend | outro time | mock v2 completo | `BackendHTTP` quando publicarem o contrato |

Bloqueio externo: o contrato HTTP do backend. Até ele chegar, `BackendMock` implementa a
porta inteira e `/avancar` empurra as etapas à mão.

## Trabalhar aqui

Vários agentes mexem neste repositório ao mesmo tempo. **Cada um só escreve nos arquivos
que o `CLAUDE.md` da sua pasta lista como seus.** Precisar mudar arquivo de outro módulo é
sinal de que o contrato está errado — pare e reporte, não contorne.

Português no código, nos comentários e nas mensagens de erro. Type hints em tudo. Nada de
abstração especulativa. Cada lógica não trivial deixa **um** teste, só pytest.

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
