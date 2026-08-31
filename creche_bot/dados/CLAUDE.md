# Persistência: módulo isolado

**Esta pasta é sua e ninguém mais mexe nela.** Em troca, você não mexe em nenhuma outra: o
resto do projeto conhece só `porta.py`.

| Arquivo | Dono | Regra |
|---|---|---|
| `porta.py` | Fase 0 | **CONGELADO.** É o contrato; todo mundo depende |
| `memoria.py` | Fase 0 | **Não mexa.** É a válvula de escape de quem trabalha no canal |
| `postgres.py` | você | Supabase. O único arquivo do projeto que escreve SQL |

**A fronteira, em uma frase.** Fora desta pasta não existe `psycopg`, `SELECT`, `session`,
`connection` nem `cursor`, e há teste que varre `creche_bot/` e falha se aparecer. Quem consome
recebe um `Repositorio` injetado e chama 21 métodos, que devolvem só as dataclasses de
`porta.py`: `Inscricao`, `EventoPendente`, `Cadastro`, `RespostaCriterio`, `PreferenciaEscola`,
`EventoInscricao`. Nunca `Row`, dict de coluna ou objeto de ORM.

## Estado

`postgres.py` roda contra o Supabase, schema `creche` (`make up` sobe um Postgres local
equivalente, se preferir). **Sem SQLAlchemy e sem Alembic, de propósito:** são 21 métodos sobre
onze tabelas num arquivo só, e DDL idempotente no boot custa menos que migração versionada
enquanto o schema muda toda semana ([D21](../../docs/DECISOES.md)). Modelo em
[MODELO_DADOS.md](../../docs/MODELO_DADOS.md), setup em [BANCO.md](../../docs/BANCO.md).

```python
@pytest.fixture(params=["memoria", "postgres"])   # tests/conftest.py
def repo(request): ...
```

`RepositorioMemoria` é a referência de comportamento: se as duas divergirem em cópia de dict,
ordem da fila ou órfão depois do expurgo, o teste acusa. Sem `DATABASE_URL`, a metade Postgres
é pulada, e quem isola é o schema `creche_teste`, não uma variável de teste separada.

**A bateria contra o banco é só a sua:** `tests/conversa` roda em memória, porque lá o objeto
de teste é o roteiro. Em troca, `tests/dados` tem que exercitar a porta **inteira** — inclusive
`salvar_cadastro`/`cadastro_de` com régua e preferências, que é onde as quatro tabelas do
espelho consultável são cobradas.

Duas armadilhas do pooler já estão resolvidas no `conftest` e voltam se alguém desfizer: a
conexão administrativa precisa de `prepare_threshold=None` como o pool (senão a limpeza morre
em `prepared statement "_pg3_0" does not exist`, e o erro aparece no teste seguinte), e a
limpeza é um `TRUNCATE` da lista inteira **sem `CASCADE`** — com ele o lock alcançava tabela
fora da lista, em ordem imprevisível, e a bateria morria em `DeadlockDetected`.

## Armadilhas

- **`contato_de()` é idempotente.** Chamada a cada mensagem. Contato duplicado = a pessoa perde
  a conversa no meio. Duas threads escrevem (polling e worker), por isso o `ConnectionPool` e o
  savepoint.
- **`id_externo` NUNCA é chave primária.** É o UUID do `contato` que faz a mesma pessoa migrar
  para o WhatsApp sem recomeçar.
- **`apagar_tudo()` não pode deixar órfão.** `outbox` e `evento_inscricao` não têm FK, então
  apague por protocolo, explicitamente. LGPD art. 18, e há teste.
- **`carregar_sessao()` devolve cópia.** O chamador muta o dict; devolver a referência interna
  faria o estado mudar sem passar por `salvar_sessao()`.
- **`sessao.contexto` é `jsonb`.** O formato muda toda semana e não vale uma migração por vez.
- **Nada de PII em log.** Só IDs.

**Adiado de propósito:** cofre de documentos (a V1 extrai, guarda estruturado e descarta os
bytes, e enquanto valer não há o que vazar) e Alembic (quando o schema parar de mudar). Não
comece nenhum dos dois sem a creche exigir o original.

## Verificar

```bash
make banco     # aplica o schema e prova a porta inteira contra o Supabase
make dados     # sua bateria
make fronteira # falha se SQL vazar para fora desta pasta
```

Quem trabalha no canal roda `REPOSITORIO=memoria make bot` e não é bloqueado por nada que
aconteça aqui: você pode quebrar o `postgres.py` à vontade, só não quebre `porta.py`.
