# Conversa — a máquina de estados

O roteiro do Zé Matrícula, do `/start` ao protocolo. Mapa completo entre roteiro e
código: [`docs/ROTEIRO.md`](../../docs/ROTEIRO.md).

## Seus arquivos

`maquina.py` · `sessao.py` · `formulario.py` · `passos/*.py` · `tests/conversa/`

Só lê: `canal/tipos.py`, `backend/porta.py`, `dados/porta.py`, `ia/redacao.py`.
**Não toque** em `canal/telegram.py`, `dados/sqlite.py`, `backend/mock.py`.

## Onde mexer no quê

| Quero mudar | Edito |
|---|---|
| O texto de uma mensagem | `ia/persona.py` |
| Uma pergunta do cadastro, ou a ordem delas | `formulario.py` — é uma tupla de `Campo` |
| A ramificação de uma pergunta | `Campo.pular_se`, uma lambda |
| O fluxo entre blocos | `maquina.PASSOS` e o `passos/` correspondente |

**Blocos 2, 3 e 4 são dados, não código.** "Uma pergunta por mensagem" é literalmente uma
lista de perguntas — não escreva um handler por campo. Ver [D8](../../docs/DECISOES.md).

## Regras que o código cobra

- **Máx. 3 botões, 10 itens de lista, rótulo de 20 chars.** `MensagemSaida.__post_init__`
  e `Campo.__post_init__` levantam `AssertionError`. Não contorne: quebre em duas telas,
  como o painel de escolas faz.
- **Uma pergunta por mensagem.** Nunca empilhe duas no mesmo balão.
- **Texto puro.** Sem `*`, `_`, `` ` `` ou `#`: os dialetos de Telegram e WhatsApp divergem.
- **Sem consentimento, nada é alcançável.** `EXIGEM_CONSENTIMENTO` em `maquina.py`.
  LGPD art. 14 — guarda no código, não confiança no fluxo.
- **Dado de saúde tem consentimento próprio.** `Campo.aviso = "sensivel"` dispara o texto
  de LGPD art. 11 antes da pergunta, e "Prefiro não dizer" é sempre uma opção.
- **Nunca prometer vaga.** Nota de corte é referência do ano passado, com o ano dito.
  Proibido "garantido", "com certeza", "vai conseguir". Há teste varrendo o roteiro.
- **`ACOMPANHAMENTO` despacha por `etapa.tipo`, nunca por `etapa.codigo`.** O código é
  vocabulário do backend e muda por município. Ver [D4](../../docs/DECISOES.md).
- **Trate `BackendIndisponivel` em toda chamada.** A conversa não morre porque um serviço
  externo tossiu: avise em linguagem de gente, guarde o que já tem, ofereça tentar de novo.
- **Estado persiste em `repo.salvar_sessao()`**, nunca em memória de processo.

## A armadilha que já mordeu

Quando outro passo entrega o controle ao formulário, ele precisa **já fazer a pergunta**
— senão a próxima mensagem da pessoa é engolida como se fosse resposta de uma pergunta
que nunca foi feita. Use `perguntar_proximo(p, prefixo=...)`, não `p.ir("FORMULARIO")`
seco.

## Rodar sozinho

```python
from creche_bot.backend.mock import BackendMock
from creche_bot.dados.memoria import RepositorioMemoria
from creche_bot.ia.redacao import RedatorEstatico

bot = Maquina(BackendMock(), RedatorEstatico(), RepositorioMemoria())
```

Sem rede, sem banco, sem chave de API. Injete tipado pelas portas
(`BackendCreche`, `Repositorio`), nunca pelas classes concretas.

## Verificar

```bash
make contratos && make conversa
```

Os testes rodam contra `RepositorioMemoria` **e** `RepositorioSQLite`. Caminhos cobertos:
data lake achou / não achou / CPF certo com data errada, ordem de preferência,
documento ilegível, correção de campo, consentimento sensível, e um que varre tudo
procurando tela com mais de 3 botões.
