# Conversa — a máquina de estados

O roteiro do Zé Matrícula, do `/start` ao protocolo, mais o fluxo de consulta. A fonte de
verdade da conversa é [`docs/script-chatbot-ze-matricula.md`](../../docs/script-chatbot-ze-matricula.md);
o mapa dele contra os estados está em [`docs/ROTEIRO.md`](../../docs/ROTEIRO.md).

## Seus arquivos

`maquina.py` · `sessao.py` · `formulario.py` · `passos/*.py` · `tests/conversa/`

Só lê: `canal/tipos.py`, `backend/porta.py`, `dados/porta.py`, `ia/redacao.py`,
`ia/persona.py`. **Não toque** em `canal/telegram.py`, `dados/sqlite.py`,
`backend/mock.py`.

## Onde mexer no quê

| Quero mudar | Edito |
|---|---|
| O texto de uma mensagem | `ia/persona.py` |
| O emoji que acompanha uma mensagem | `ia/persona.py` — mapa `FIGURINHAS` |
| Uma pergunta do cadastro ou do contato, ou a ordem delas | `formulario.py` — é uma tupla de `Campo` |
| A ramificação de uma pergunta | `Campo.pular_se`, uma lambda |
| A forma de um turno da régua de prioridade | `passos/criterios.py` |
| **O conteúdo** da régua de prioridade | Nada aqui. Vem de `backend.criterios_do_processo()` |
| O fluxo entre blocos | `maquina.PASSOS` e o `passos/` correspondente |

**Cadastro e contato são dados, não código.** "Uma pergunta por mensagem" é literalmente
uma lista de perguntas — não escreva um handler por campo. Ver
[D8](../../docs/DECISOES.md).

**A régua é dado do backend.** Entre 2023 e 2024 só 3 das 13 perguntas de prioridade
sobreviveram e o teto caiu de 465 para 100 pontos. `criterios.py` define a **forma** do
turno (sim/não, checklist, número, anexo); o conteúdo chega em `p.dados["criterios"]`. Ver
[D15](../../docs/DECISOES.md).

## Regras que o código cobra

- **Máx. 3 botões, 10 itens de lista, rótulo de 20 chars.** `MensagemSaida.__post_init__`
  e `Campo.__post_init__` levantam `AssertionError`. Não contorne: quebre em duas telas,
  como o painel de escolas faz.
- **Uma pergunta por mensagem.** Exceção deliberada: os checklists dos blocos 8.3 e 8.4.
- **Texto puro.** Sem `*`, `_`, `` ` `` ou `#`: os dialetos de Telegram e WhatsApp divergem.
- **Sem consentimento, nada é alcançável.** `EXIGEM_CONSENTIMENTO` em `maquina.py`.
  LGPD art. 14 — guarda no código, não confiança no fluxo.
- **Dado sensível tem consentimento próprio, é opcional, e NUNCA é ecoado.**
  `Criterio.sensivel` dispara `CONSENTIMENTO_SENSIVEL` antes do bloco 8.4. O eco de
  confirmação vale para CPF, nome e telefone; não vale para violência doméstica nem
  situação prisional — o histórico fica no aparelho da família. Ver
  [D7](../../docs/DECISOES.md).
- **Nada bloqueia a inscrição** além do consentimento e da faixa etária. Documento que
  falta vira pendência com lembrete, nunca parede.
- **Nunca prometer vaga, pontuação nem posição na fila.** Sobre uma creche só distância,
  vaga aberta agora e concorrência do ano passado, rotulada como passado. Há teste
  varrendo o roteiro. Ver [D5](../../docs/DECISOES.md).
- **A consulta mostra o `Desfecho`, nunca a situação por opção.** Ver
  [D14](../../docs/DECISOES.md).
- **`ACOMPANHAR` despacha por `etapa.tipo`, nunca por `etapa.codigo`.** O código é
  vocabulário do backend e muda por município. Ver [D4](../../docs/DECISOES.md).
- **Trate `BackendIndisponivel` em toda chamada.** A conversa não morre porque um serviço
  externo tossiu: avise em linguagem de gente, guarde o que já tem, ofereça tentar de novo.
- **Estado persiste em `repo.salvar_sessao()`**, nunca em memória de processo. E
  `chave_idempotencia` nasce no primeiro turno: conversa que cai e recomeça não pode virar
  inscrição duplicada. Ver [D16](../../docs/DECISOES.md).

## As duas armadilhas que já morderam

**Entrar num bloco sem desenhar a tela.** Cada estado tem duas portas:
`PASSOS[estado]` **consome** a resposta que chegou, `ENTRADAS[estado]` **desenha** a tela
pela primeira vez. Correção e retomada usam `maquina.entrar()`, nunca `p.ir("CADASTRO")`
seco — senão a próxima mensagem da família é engolida como resposta de uma pergunta que
nunca foi feita. No formulário isso vira `perguntar` (que marca `dados["perguntou"]`)
contra `responder` (que só consome se houver pergunta no ar). Estado novo com tela própria
precisa de linha nos dois dicionários.

**Derivar o que a família não sabe responder.** Grupamento, bairro, logradouro,
coordenadas, polo, distância, "esperou na fila no ano passado" e "responsável menor de 18"
são todos derivados. Perguntar qualquer um deles é bug de desenho, não feature.

## Fora do roteiro, antes de qualquer passo

`maquina.processar()` resolve duas coisas antes do despacho:

1. **Áudio vira texto** (`ia/transcricao.py`). Nenhum passo sabe que existe voz.
2. **Toda mensagem digitada é classificada antes de virar resposta de campo**
   (`_fora_do_roteiro`). Botão e comando passam direto — já têm dono. Três saídas:

   - `duvida` → responde e **não** mexe no estado; perguntar não faz perder o lugar na
     fila. Com cota por contato. Ver [D17](../../docs/DECISOES.md).
   - `fora_de_contexto` → repete a pergunta com o texto `me_perdi`, sem consumir a
     mensagem e **sem contar erro no campo**. Nunca duas vezes seguidas, e só onde há
     `ENTRADAS[estado]`: redesenhar pelo `PASSOS` consumiria a mensagem. Ver
     [D18](../../docs/DECISOES.md).
   - qualquer outra → segue o roteiro.

   Para o modelo vai só a etapa e a pergunta **estática** do campo (`_etapa`) — nunca
   `pergunta_alt`, que interpola o nome da criança.

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

Os testes rodam contra `RepositorioMemoria` **e** `RepositorioSQLite`. Caminhos que
precisam continuar cobertos: cadastro anterior achado / não achado, criança fora da faixa,
CEP que não resolve, a régua inteira do bloco 8, recusa do consentimento sensível, ordem de
preferência, documento ilegível, os sete desfechos da consulta, e um teste que varre tudo
procurando tela com mais de 3 botões ou promessa de vaga.
