# Persistência — módulo isolado

**Esta pasta é sua e ninguém mais mexe nela.** Em troca, você não mexe em nenhuma outra:
o resto do projeto conhece só `porta.py`.

## Os arquivos

| Arquivo | Dono | Regra |
|---|---|---|
| `porta.py` | Fase 0 | **CONGELADO.** É o contrato. Mudança = PR próprio; todo mundo depende |
| `memoria.py` | Fase 0 | **Não mexa.** É a válvula de escape de quem trabalha no canal |
| `sqlite.py` | você | Substitua à vontade. É o único arquivo do projeto que escreve SQL |

## A fronteira, em uma frase

Fora desta pasta não existe `sqlite3`, `SELECT`, `session`, `connection` nem `cursor`.
Há um teste que varre `creche_bot/` e falha se aparecer.

Quem consome recebe um `Repositorio` injetado no construtor e chama 16 métodos. Nenhum
deles devolve `Row`, `dict` de coluna ou objeto de ORM — só `Inscricao` e `EventoPendente`,
que são dataclasses de `porta.py`.

## Seu trabalho: trocar a implementação, não escrever do zero

`sqlite.py` **já funciona**. Ele foi escrito com a stdlib para o bot rodar sem docker e sem
`pip install` durante a validação. A meta é Postgres + SQLAlchemy 2.0 + Alembic.

Mantenha as assinaturas de `porta.py` e **a bateria continua passando** — eles rodam
parametrizados contra `RepositorioMemoria` e a sua implementação, lado a lado. Se as duas
divergirem em qualquer comportamento, o teste acusa antes de chegar em produção.

```python
@pytest.fixture(params=["memoria", "postgres"])
def repo(request): ...
```

## O que ainda não existe e é seu

**`cofre.py` — documentos cifrados.** Hoje a V1 **não persiste documento**: extrai, guarda
o resultado estruturado e descarta os bytes. Isso não é preguiça, é a regra de minimização
da arquitetura (§2.2) — e enquanto valer, não há o que vazar.

Quando a creche exigir o arquivo original, ele precisa nascer:
- cifrado em repouso (`cryptography.Fernet`, chave em env — nunca no código);
- com `expira_em` e job de expurgo;
- e **nunca** em log, nem o nome do arquivo.

**Migrações.** Alembic quando o schema parar de mudar toda semana. Antes disso,
`create_all` custa menos que manter migração de schema instável.

## Armadilhas

- **`contato_de()` é idempotente.** Chamada a cada mensagem que chega. Se criar contato
  duplicado, a pessoa perde a conversa no meio.
- **`id_externo` NUNCA é chave primária.** `contato` tem UUID próprio e
  `identidade_canal` liga aos canais. É isso que faz a mesma pessoa migrar do Telegram
  para o WhatsApp sem recomeçar o cadastro.
- **`apagar_tudo()` não pode deixar órfão.** LGPD art. 18. `outbox` não tem FK para
  `contato` — apague por protocolo, explicitamente. Há teste.
- **`carregar_sessao()` devolve cópia.** O chamador muta o dict que recebe; se você
  devolver a referência interna, o estado muda sem passar por `salvar_sessao()`.
- **Duas threads escrevem.** Polling do Telegram e worker de outbox. No sqlite isso é
  `check_same_thread=False` + WAL; no Postgres, pool de conexões.
- **`sessao.contexto` é JSON.** O formato muda toda semana durante o desenvolvimento e
  não vale uma migração por vez. Deixe como `jsonb`.
- **Nada de PII em log.** Só IDs.

## Como verificar

```bash
make dados        # sua bateria
make test         # os 29, contra as duas implementações
make fronteira    # falha se SQL vazar para fora desta pasta
```

## Enquanto você refatora

Quem trabalha no canal roda `REPOSITORIO=memoria make bot` e não é bloqueado por nada que
aconteça aqui. Você pode quebrar o `sqlite.py` à vontade — só não quebre `porta.py`.
