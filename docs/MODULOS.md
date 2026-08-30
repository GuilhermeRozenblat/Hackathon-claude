# Divisão do trabalho

Este repositório é dividido por **fronteiras de código**, não por combinação verbal. Cada
frente tem pasta própria, `CLAUDE.md` próprio e um teste que falha se alguém atravessar.

## Quem faz o quê

| Frente | Pasta | Dono | Roda com |
|---|---|---|---|
| **Chat e conversa** | `canal/` · `conversa/` · `ia/` · `notificacao/` | Guilherme | `make memoria` — **não depende de `dados/`** |
| **Banco e persistência** | `dados/` — e só | outra pessoa | `make dados` e `make test` |
| **Dados do município** | `backend/` | outro time, outra máquina | `BackendMock` cobre tudo hoje |

As três se encontram em dois arquivos congelados:

- `creche_bot/dados/porta.py` — 21 operações de persistência
- `creche_bot/backend/porta.py` — 17 operações do município

**Mudar um desses dois é PR próprio, revisado por todos os lados.** Enquanto eles não
mudarem, ninguém quebra ninguém — e `make fronteira` prova.

## A reescrita v2

O roteiro foi reescrito a partir da régua real do processo 195/2025 e da base histórica de
2021 a 2025 ([`script-chatbot-ze-matricula.md`](script-chatbot-ze-matricula.md)), e o
código acompanhou: contratos, `BackendMock`, notificação e a conversa inteira estão em v2.

O que a v2 mudou de estrutural, e por quê:

| Mudança | Motivo |
|---|---|
| A busca começa pelo CPF do **responsável** | 27,9% das crianças já constavam no ano anterior; e criança de 0 a 3 anos muitas vezes não tem CPF |
| Endereço só por **CEP + número** | Campo livre gerou 1.608 grafias para ~925 bairros |
| A régua de prioridade virou **dado do backend** | Entre 2023 e 2024, 3 das 13 perguntas sobreviveram |
| A consulta mostra um **desfecho calculado** | 77,8% dos "cancelado pelo sistema" são de quem foi atendido |
| Saiu a nota de corte, entrou **concorrência do ano passado** | Pontuação não é comparável entre anos; concorrência é fato |
| Entrou o **bloco C**, de acompanhamento | Alcança as ~62 mil famílias que se inscreveram pelo portal |
| Entrou **voz** e **dúvida solta** | A família fala; e perguntar não pode fazer perder o lugar na fila |

Os estados, um a um, estão em [ROTEIRO.md](ROTEIRO.md); o porquê de cada decisão, em
[DECISOES.md](DECISOES.md).

## Por que isso funciona na prática

`REPOSITORIO=memoria make bot` sobe o bot inteiro sem tocar em disco. Quem trabalha no
banco pode quebrar `dados/postgres.py` à vontade que o chat continua rodando; só não pode
mexer em `porta.py`.

No sentido inverso: os testes rodam **parametrizados contra as duas implementações** de
repositório, lado a lado. Se a versão Postgres divergir da de memória em qualquer
comportamento, o teste acusa antes de chegar em produção.

## Estado de cada módulo

| Módulo | Estado | O que falta |
|---|---|---|
| [Canal Telegram](../creche_bot/canal/CLAUDE.md) | ✅ roda | Figurinhas de verdade (hoje é emoji) |
| [Conversa](../creche_bot/conversa/CLAUDE.md) | ✅ roteiro v2 completo | Mais casos de borda |
| [IA / persona](../creche_bot/ia/CLAUDE.md) | ✅ roda sem chave | `RedatorClaude` não foi testado com chave real |
| [Persistência](../creche_bot/dados/CLAUDE.md) | ✅ isolada | Postgres, Alembic, cofre — **outra pessoa** |
| [Backend do município](../creche_bot/backend/CLAUDE.md) | ⏸️ mock v2 completo | `BackendHTTP` quando o outro time publicar |
| [Notificação](../creche_bot/notificacao/CLAUDE.md) | ✅ roda | Retry com backoff exponencial |

## Rodar

```bash
cp .env.example .env      # cole o token do @BotFather — veja TELEGRAM.md
make bot                  # Postgres: a conversa sobrevive ao restart
make memoria              # sem tocar em disco: não depende de dados/
```

Nenhuma dependência é necessária para rodar. `pip install -e ".[dev]"` só para os testes.

## Documentação

| Arquivo | Para quê |
|---|---|
| [script-chatbot-ze-matricula.md](script-chatbot-ze-matricula.md) | O roteiro v2 — a fonte de verdade da conversa |
| [ARQUITETURA.md](ARQUITETURA.md) | O desenho completo e por quê |
| [DECISOES.md](DECISOES.md) | As decisões que custariam caro reverter |
| [ROTEIRO.md](ROTEIRO.md) | Mapa entre o roteiro e os estados do código |
| [TELEGRAM.md](TELEGRAM.md) | Configurar o bot no @BotFather, 10 minutos |
| [CLAUDE.md](../CLAUDE.md) | Regras para qualquer agente neste repo |

## Como despachar um agente

```
Leia creche_bot/dados/CLAUDE.md e docs/BANCO.md: o Postgres do Supabase já está atrás da porta.
```

O `CLAUDE.md` da pasta diz o que é dela, o que não é, e como verificar. Não é preciso
passar o `ARQUITETURA.md` junto.

## Pendências que bloqueiam alguém

| Pendência | Bloqueia | Contorno |
|---|---|---|
| Token do `@BotFather` | testar no Telegram real | [TELEGRAM.md](TELEGRAM.md), 10 min |
| Contrato HTTP do backend | `BackendHTTP` | `BackendMock` implementa a porta inteira |
| Retorno CRAS → creche | notificação real dessa etapa | O bot já avisa que o trajeto existe — ver [D10](DECISOES.md) |
