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

- `creche_bot/dados/porta.py` — 16 operações de persistência
- `creche_bot/backend/porta.py` — 8 operações do município

**Mudar um desses dois é PR próprio, revisado por todos os lados.** Enquanto eles não
mudarem, ninguém quebra ninguém — e `make fronteira` prova.

## Por que isso funciona na prática

`REPOSITORIO=memoria make bot` sobe o bot inteiro sem tocar em disco. Quem trabalha no
banco pode quebrar `dados/sqlite.py` à vontade que o chat continua rodando; só não pode
mexer em `porta.py`.

No sentido inverso: os 43 testes rodam **parametrizados contra as duas implementações**
de repositório, lado a lado. Se a versão Postgres divergir da de memória em qualquer
comportamento, o teste acusa antes de chegar em produção.

## Estado de cada módulo

| Módulo | Estado | O que falta |
|---|---|---|
| [Canal Telegram](../creche_bot/canal/CLAUDE.md) | ✅ roda | Figurinhas de verdade (hoje é emoji) |
| [Conversa](../creche_bot/conversa/CLAUDE.md) | ✅ roteiro completo | Mais casos de borda |
| [IA / persona](../creche_bot/ia/CLAUDE.md) | ✅ roda sem chave | `RedatorClaude` não foi testado com chave real |
| [Persistência](../creche_bot/dados/CLAUDE.md) | ✅ isolada | Postgres, Alembic, cofre — **outra pessoa** |
| [Backend do município](../creche_bot/backend/CLAUDE.md) | ⏸️ mock completo | `BackendHTTP` quando o outro time publicar |
| [Notificação](../creche_bot/notificacao/CLAUDE.md) | ✅ roda | Retry com backoff exponencial |

## Rodar

```bash
cp .env.example .env      # cole o token do @BotFather — veja TELEGRAM.md
make bot                  # sqlite: a conversa sobrevive ao restart
make memoria              # sem tocar em disco: não depende de dados/
```

Nenhuma dependência é necessária para rodar. `pip install -e ".[dev]"` só para os testes.

## Documentação

| Arquivo | Para quê |
|---|---|
| [ARQUITETURA.md](ARQUITETURA.md) | O desenho completo e por quê |
| [docs/DECISOES.md](DECISOES.md) | As 10 decisões que custariam caro reverter |
| [docs/ROTEIRO.md](ROTEIRO.md) | Mapa entre o roteiro de conversa e o código |
| [TELEGRAM.md](TELEGRAM.md) | Configurar o bot no @BotFather, 10 minutos |
| [CLAUDE.md](../CLAUDE.md) | Regras para qualquer agente neste repo |

## Como despachar um agente

```
Leia creche_bot/dados/CLAUDE.md e troque o sqlite por Postgres, mantendo a porta.
```

O `CLAUDE.md` da pasta diz o que é dela, o que não é, e como verificar. Não é preciso
passar o `ARQUITETURA.md` junto.

## Pendências que bloqueiam alguém

| Pendência | Bloqueia | Contorno |
|---|---|---|
| Token do `@BotFather` | testar no Telegram real | [TELEGRAM.md](TELEGRAM.md), 10 min |
| Contrato HTTP do backend | `BackendHTTP` | `BackendMock` implementa a porta inteira |
| Retorno CRAS → creche | notificação real dessa etapa | O bot já avisa que o trajeto existe — ver [D10](DECISOES.md) |
