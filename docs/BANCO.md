# Banco — Postgres no Supabase

O bot guarda CPF, nome de criança e telefone. Este documento é o caminho para deixar isso
num lugar que sobreviva ao restart sem virar um vazamento.

## 0. O projeto

| | |
|---|---|
| Projeto | `ze-matricula` |
| Ref | `frzkhffbpwmpjetcenfw` |
| Região | `sa-east-1` (São Paulo) — dado de criança sob LGPD fica em território nacional |
| Organização | CleanApps |
| Schema | `creche` (fora do alcance da Data API) |

## 1. Pegar a connection string

No dashboard do Supabase: **Connect** (topo da página) → aba **Connection string** →
**Transaction pooler**. Você recebe algo assim:

```
postgresql://postgres.<ref>:<SENHA>@aws-0-<regiao>.pooler.supabase.com:6543/postgres
```

Troque `<SENHA>` pela senha do banco (**Project Settings → Database → Reset password**, se
você não a tiver — a senha só aparece no momento em que é criada).

**Use o pooler, não a conexão direta.** O bot abre duas frentes que escrevem ao mesmo
tempo — o polling do Telegram e o worker de outbox — e o plano free do Supabase corta
conexão direta rápido. `RepositorioPostgres` já desliga prepared statement por causa do
modo transação; a porta 5432 (session pooler) também funciona sem mudar nada.

## 2. Colocar no `.env`

```bash
cp .env.example .env      # o .env é ignorado pelo git; o bot exige permissão 0600
```

```ini
DATABASE_URL=postgresql://postgres.<ref>:<SENHA>@aws-0-<regiao>.pooler.supabase.com:6543/postgres
```

`sslmode=require` é acrescentado sozinho se você não puser: sem TLS, CPF e nome de criança
atravessam a internet em texto claro.

A connection string carrega a senha do banco. Ela está em `segredos.SEGREDOS`, então o
formatador de log a redige de mensagem **e** de traceback — mas isso é a segunda linha de
defesa, não a primeira. Não cole a string em issue, PR ou print.

## 3. Aplicar o schema e provar que funciona

```bash
make banco
```

Cria o schema, roda um ciclo completo com um contato de mentira — identidade, sessão,
inscrição, outbox, marca d'água — e apaga tudo pelo mesmo caminho da LGPD art. 18. Se
sobrar órfão, o script acusa.

| Comando | O que faz |
|---|---|
| `make banco` | Aplica o schema e testa a porta inteira contra ele |
| `make esquema` | Só aplica o schema (idempotente) |
| `make dados` | A bateria de testes da persistência |
| `make limpar` | Derruba o schema `creche` inteiro (pede confirmação) |

`RepositorioPostgres` reaplica o schema no boot. É DDL idempotente (`IF NOT EXISTS`) e
custa menos que manter migração versionada enquanto o schema muda toda semana — Alembic
entra quando ele parar de mudar.

## 4. Por que schema `creche` e não `public`

No Supabase, o `public` é servido pela **Data API** (PostgREST) para quem tiver a chave
anônima — e essa chave costuma acabar no front. As tabelas daqui guardam nome de criança e
CPF: um schema fora da lista de exposição simplesmente **não é alcançável** pela API, e
isso não depende de ninguém lembrar de manter uma política de RLS restritiva.

RLS fica ligada em todas as tabelas mesmo assim, sem política nenhuma, e `anon`,
`authenticated` e `service_role` perdem o acesso ao schema. O bot conecta como dono das
tabelas, que é quem RLS não bloqueia.

Se um dia alguém precisar ler isso pela API, o caminho é uma **view específica em `public`,
com `security_invoker = true`, expondo só as colunas necessárias** — nunca expor o schema.

## 5. O que fica guardado

| Tabela | O que é | Some com o expurgo |
|---|---|---|
| `contato` | UUID interno da pessoa | sim (cascata) |
| `identidade_canal` | `(canal, id_externo)` → contato | sim |
| `consentimento` | versão do texto aceito, quando e por onde | sim |
| `sessao` | estado da conversa + contexto `jsonb` | sim |
| `inscricao` | protocolo, escola e etapa atual | sim |
| `outbox` | eventos a entregar | sim, **por protocolo, explicitamente** |
| `marca` | até onde o backend já foi lido | não (não tem dado pessoal) |

**Documento não é persistido.** A V1 extrai, guarda o resultado estruturado e descarta os
bytes (minimização, ARQUITETURA §2.2). Enquanto isso valer, não há o que vazar. Quando a
creche exigir o arquivo original, ele nasce cifrado, com `expira_em` e job de expurgo — ver
`creche_bot/dados/CLAUDE.md`.

**`outbox` não tem FK para `contato`, de propósito.** Um `ON DELETE CASCADE` escondido
tornaria fácil esquecer que a fila também guarda nome de criança. `apagar_tudo()` apaga por
protocolo, explicitamente, e há teste que falha se sobrar linha.

## 6. Rodar sem banco

```bash
make memoria      # REPOSITORIO=memoria: o bot inteiro, sem banco nenhum
```

É a válvula de escape: quem trabalha em canal e conversa não fica bloqueado por Postgres
fora do ar nem por migração em andamento. O estado some no restart, e é só isso.

## 7. Testes

Todo teste da persistência roda **duas vezes**: contra `RepositorioMemoria` e contra o
Postgres. A implementação em memória é a referência de comportamento — se as duas
divergirem em cópia de dict, ordem da fila ou órfão depois do expurgo, o teste acusa.

```bash
make test         # sem DATABASE_URL_TESTE, a metade Postgres é pulada
```

Os testes usam o schema **`creche_teste`**, nunca o `creche`: eles dão `TRUNCATE` em tudo
que enxergam, e apontar isso para inscrição real seria destruição silenciosa. Ao fim da
sessão o schema de teste é derrubado.

Contra o Supabase a suíte leva ~1min40 (era 0,3s só em memória): cada asserção é uma ida e
volta até São Paulo. Para o ciclo curto de quem está escrevendo código, `make memoria` ou
o Postgres local do `make up` respondem na hora; o banco remoto vale antes de abrir PR.

Para rodar contra um banco descartável em vez do Supabase:

```bash
make up           # docker compose: Postgres local na loopback
DATABASE_URL_TESTE=postgresql://creche:$POSTGRES_PASSWORD@127.0.0.1:5432/creche make test
```

## 8. Quando algo dá errado

| Sintoma | Causa provável |
|---|---|
| `password authentication failed` | Senha do banco ≠ senha da conta. Project Settings → Database → Reset password |
| `(ENOTFOUND) tenant/user ... not found` | Usuário do pooler é `postgres.<ref>`, não `postgres` — **ou o host está errado por um dígito**: é `aws-0-sa-east-1`, e `aws-1-...` resolve para um pooler de verdade que simplesmente não conhece este tenant. Copie o host do dashboard, não digite |
| `prepared statement ... does not exist` | Alguém tirou `prepare_threshold=None` do pool |
| `permission denied for schema creche` | Conectou com um papel que não é o dono das tabelas |
| Conexão cai depois de ociosa | O pooler derruba ociosa; o `check` do pool já trata — confira se ele continua lá |
