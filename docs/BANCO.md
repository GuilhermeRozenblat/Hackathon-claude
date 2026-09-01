# Banco: Postgres no Supabase

O bot guarda CPF, nome de criança e telefone. Este é o caminho para deixar isso num lugar que
sobreviva ao restart sem virar vazamento. O modelo está em [MODELO_DADOS.md](MODELO_DADOS.md);
o porquê das escolhas, em [D21](DECISOES.md).

| Projeto | `ze-matricula` · ref `frzkhffbpwmpjetcenfw` · `sa-east-1` (São Paulo) · schema `creche` |
|---|---|

Região brasileira porque dado de criança sob LGPD fica em território nacional.

## 1. Connection string

Dashboard do Supabase → Connect → Connection string → Transaction pooler:

```
postgresql://postgres.<ref>:<SENHA>@aws-0-<regiao>.pooler.supabase.com:6543/postgres
```

A senha é a do banco. Se você não a tiver: Project Settings → Database → Reset password.

> Os sinais `<` e `>` saem junto: eles marcam o buraco e não fazem parte do valor. Deixar
> `:<minhasenha>@` manda os dois sinais para o Postgres, e a resposta é `password
> authentication failed`, que manda procurar a senha errada. Se a senha tiver `@`, `/`, `?`,
> `#` ou `%`, aí sim precisa de percent-encoding.

Use o pooler, e não a conexão direta. Duas frentes escrevem ao mesmo tempo, o polling e o
worker de outbox, e o plano free corta conexão direta rápido. A porta 5432, do session
pooler, também funciona sem mudar nada.

## 2. `.env` e schema

```bash
cp .env.example .env      # o .env é ignorado pelo git; o bot exige permissão 0600
# DATABASE_URL=postgresql://postgres.<ref>:<SENHA>@aws-0-<regiao>.pooler.supabase.com:6543/postgres
make banco                # aplica o schema e testa a porta inteira contra ele
```

`sslmode=require` é acrescentado sozinho: sem TLS, CPF e nome de criança atravessam a internet
em texto claro. A senha está em `segredos.SEGREDOS`, então o formatador de log a redige de
mensagem e de traceback, segunda linha de defesa, não a primeira. Não cole a string em issue,
PR ou print.

| Comando | O que faz |
|---|---|
| `make banco` | Aplica o schema e roda um ciclo completo com um contato de mentira, apagando tudo pelo caminho da LGPD art. 18. Se sobrar órfão, acusa |
| `make esquema` | Só aplica o schema (idempotente) |
| `make dados` | A bateria de testes da persistência |
| `make limpar` | Derruba o schema `creche` inteiro (pede confirmação) |
| `make memoria` | Roda o bot sem banco nenhum |

`RepositorioPostgres` reaplica o schema no boot: DDL idempotente custa menos que migração
versionada enquanto o schema muda toda semana. Alembic entra quando ele parar de mudar.

## 3. Por que schema `creche` e não `public`

No Supabase o `public` é servido pela Data API (PostgREST) a quem tiver a chave anônima, e
essa chave costuma acabar no front. Um schema fora da lista de exposição não é alcançável pela
API, e isso não depende de ninguém lembrar de manter RLS restritiva numa tabela nova.

RLS fica ligada em todas mesmo assim, sem política, e `anon`, `authenticated` e `service_role`
perdem acesso ao schema. O bot conecta como dono das tabelas, que é quem RLS não bloqueia. Se
um dia alguém precisar ler pela API, o caminho é uma view em `public` com
`security_invoker = true`, expondo só as colunas necessárias, nunca o schema.

Documento não é persistido. A V1 extrai, guarda estruturado e descarta os bytes, e enquanto
isso valer não há o que vazar.

## 4. Testes

Todo teste da persistência roda duas vezes: contra `RepositorioMemoria` (a referência de
comportamento) e contra o Postgres. Os testes usam o schema `creche_teste`, nunca o `creche`:
eles dão `TRUNCATE` em tudo que enxergam, e apontar isso para inscrição real seria destruição
silenciosa.

```bash
make test                        # sem DATABASE_URL, roda só a implementação em memória
make up                          # Postgres local no Docker, alternativa ao Supabase
DATABASE_URL=postgresql://creche:$POSTGRES_PASSWORD@127.0.0.1:5432/creche make test
```

Não existe variável de banco de teste. A suíte usa o mesmo `DATABASE_URL` do bot, e quem
isola é o schema `creche_teste`. Quem estiver com o bot no ar contra aquele projeto divide o
pooler com a suíte; para não dividir, aponte `DATABASE_URL` para o Postgres local do `make up`.

Quem roda contra o banco é só `tests/dados`. É lá que a paridade entre as duas implementações
é cobrada, e a bateria exercita a porta inteira, cadastro e preferências incluídos.
`tests/conversa` roda em memória, porque lá o objeto de teste é o roteiro. São 351 testes em
~35s no total.

Duas armadilhas do pooler estão resolvidas no `conftest`, e voltam se alguém desfizer. A
conexão administrativa precisa de `prepare_threshold=None` como o pool, senão a limpeza morre
em `prepared statement "_pg3_0" does not exist` e o erro aparece no teste seguinte. E a limpeza
é um `TRUNCATE` da lista inteira sem `CASCADE`: com ele, o lock alcançava tabela fora da lista
em ordem imprevisível e a bateria travava em `DeadlockDetected`.

O `conftest` também dropa o schema `creche_teste` no teardown, e ele é fixo. Duas baterias
simultâneas contra o mesmo projeto Supabase, de dois terminais ou de duas sessões, derrubam o
schema debaixo uma da outra: o sintoma é um bloco de falhas `[postgres]` que some quando você
roda o arquivo sozinho.

## 5. Quando algo dá errado

| Sintoma | Causa provável |
|---|---|
| `password authentication failed` | Senha do banco ≠ senha da conta, ou os `<>` do exemplo ficaram na string |
| `tenant or user not found` | Usuário do pooler é `postgres.<ref>`, não `postgres`, ou o host está errado por um dígito (`aws-0-sa-east-1`; `aws-1-…` resolve para um pooler que não conhece este tenant). Copie do dashboard |
| `prepared statement ... does not exist` | Alguém tirou `prepare_threshold=None` do pool |
| `permission denied for schema creche` | Conectou com um papel que não é o dono das tabelas |
| Conexão cai depois de ociosa | O pooler derruba ociosa; o `check` do pool trata, confira se continua lá |
