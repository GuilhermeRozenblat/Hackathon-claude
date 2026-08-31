# Divisão do trabalho

O repositório é dividido por **fronteiras de código**, não por combinação verbal: cada frente
tem pasta própria, `CLAUDE.md` próprio, e um teste que falha se alguém atravessar.

| Frente | Pasta | Dono | Roda com |
|---|---|---|---|
| **Chat e conversa** | `canal/` · `conversa/` · `ia/` · `notificacao/` | Guilherme | `make memoria`, **não depende de `dados/`** |
| **Banco e persistência** | só `dados/` | outra pessoa | `make dados` |
| **Dados do município** | `backend/` | outro time, outra máquina | `BackendMapa` sobre os CSVs reais, `BackendMock` por baixo |

As três se encontram em dois arquivos congelados: `dados/porta.py` (21 operações) e
`backend/porta.py` (17). **Mudar um deles é PR próprio, revisado por todos os lados**, e
`make fronteira` prova que ninguém atravessou.

## Estado de cada módulo

| Módulo | Estado | O que falta |
|---|---|---|
| [Canal](../creche_bot/canal/CLAUDE.md) | ✅ roda | Figurinhas de verdade (hoje é emoji) |
| [Conversa](../creche_bot/conversa/CLAUDE.md) | ✅ roteiro completo, do `/start` ao protocolo | Mais casos de borda |
| [IA](../creche_bot/ia/CLAUDE.md) | ✅ roda sem chave; a chave é de quem conversa ([D20](DECISOES.md)) | `RedatorClaude` não foi testado com chave real |
| [Persistência](../creche_bot/dados/CLAUDE.md) | ✅ Postgres no Supabase, isolado ([D21](DECISOES.md)) | Alembic, cofre, e a suíte Postgres contra o pooler |
| [Backend](../creche_bot/backend/CLAUDE.md) | ✅ 820 creches reais; mock implementa a porta inteira | `BackendHTTP` quando o outro time publicar |
| [Notificação](../creche_bot/notificacao/CLAUDE.md) | ✅ roda | Retry com backoff exponencial |

## O desenho por baixo do roteiro

O roteiro é o de produto e a conversa segue a ordem dele ([D22](DECISOES.md)). O que a base
histórica de 2021 a 2025 mudou foi o desenho:

| Mudança | Motivo |
|---|---|
| Busca pelo CPF do **responsável** | 27,9% das crianças já constavam no ano anterior; e criança de 0 a 3 anos muitas vezes não tem CPF |
| Endereço só por **CEP + número** | Campo livre gerou 1.608 grafias para ~925 bairros |
| Régua de prioridade virou **dado do backend** | Entre 2023 e 2024, 3 das 13 perguntas sobreviveram |
| A consulta mostra um **desfecho calculado** | 77,8% dos "cancelado pelo sistema" são de quem foi atendido |
| Saiu a nota de corte, entrou **concorrência + chance estimada** | Pontuação não é comparável entre anos; concorrência é fato |
| Entrou o **bloco C**, de acompanhamento | Alcança as ~62 mil famílias que se inscreveram pelo portal |
| Entraram **voz** e **dúvida solta** | A família fala; e perguntar não pode fazer perder o lugar na fila |

## Por que funciona na prática

`REPOSITORIO=memoria make bot` sobe o bot sem tocar em disco: quem trabalha no banco pode
quebrar `postgres.py` à vontade que o chat continua rodando, só não pode mexer em `porta.py`.
No sentido inverso, os testes rodam **parametrizados contra as duas implementações**: se o
Postgres divergir da memória em qualquer comportamento, o teste acusa.

**Ressalva de hoje:** a metade em memória passa inteira; a metade Postgres não
sobrevive à bateria completa contra o pooler do Supabase: deadlock no `TRUNCATE` entre
arquivos de teste e prepared statement na conexão administrativa do `conftest`. Por trilha
(`make dados`) funciona. Detalhe em [BANCO.md](BANCO.md#4-testes).

## Como despachar um agente

```
Leia creche_bot/dados/CLAUDE.md e docs/BANCO.md: o Postgres do Supabase já está atrás da porta.
```

O `CLAUDE.md` da pasta diz o que é dela, o que não é, e como verificar. Não é preciso passar a
`ARQUITETURA.md` junto.

## Pendências que bloqueiam alguém

| Pendência | Bloqueia | Contorno |
|---|---|---|
| Token do `@BotFather` | testar no Telegram real | [TELEGRAM.md](TELEGRAM.md), 10 min |
| Contrato HTTP do backend | `BackendHTTP` | `BackendMock` implementa a porta inteira |
| Retorno CRAS → creche | notificação real dessa etapa | O bot já avisa que o trajeto existe ([D10](DECISOES.md)) |
