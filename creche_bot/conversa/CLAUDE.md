# Conversa: a máquina de estados

O roteiro do `/start` ao protocolo, mais o fluxo de consulta. Fonte da conversa:
[`docs/script-chatbot-ze-matricula.md`](../../docs/script-chatbot-ze-matricula.md); mapa contra
os estados: [`docs/ROTEIRO.md`](../../docs/ROTEIRO.md).

**Seus arquivos:** `maquina.py` · `sessao.py` · `formulario.py` · `projecao.py` · `passos/*.py`
· `tests/conversa/`.
**Só lê:** `canal/tipos.py`, `backend/porta.py`, `dados/porta.py`, `ia/redacao.py`,
`ia/persona.py`.
**Não toque:** `canal/telegram.py`, `dados/postgres.py`, `backend/mock.py`, `backend/mapa.py`.

## Onde mexer no quê

| Quero mudar | Edito |
|---|---|
| O texto de uma mensagem, ou o emoji | `ia/persona.py` (`TEXTOS`, `FIGURINHAS`) |
| Uma pergunta do cadastro/contato, ou a ordem | `formulario.py`, uma tupla de `Campo` |
| Marcar uma pergunta como dado de saúde | `Campo.sensivel=True`, e o gate do art. 11 vem sozinho antes dela |
| A ramificação de uma pergunta | `Campo.pular_se`, uma lambda |
| A forma de um turno da régua | `passos/criterios.py` |
| **O conteúdo** da régua | Nada aqui: vem de `backend.criterios_do_processo()` ([D15](../../docs/DECISOES.md)) |
| A tela de IA (bloco 0.0) | `passos/ia.py`, que não passa pelo redator, de propósito |
| O fluxo entre blocos | `maquina.PASSOS` e o `passos/` correspondente |

**Cadastro e contato são dados, não código:** "uma pergunta por mensagem" é literalmente uma
lista de perguntas. Não escreva um handler por campo ([D8](../../docs/DECISOES.md)).

## Regras que o código cobra

- **Máx. 3 botões, 10 itens, rótulo de 20 chars, texto puro.** `MensagemSaida.__post_init__` e
  `Campo.__post_init__` levantam `AssertionError`. Não contorne: quebre em duas telas.
- **Uma pergunta por mensagem.** Exceção deliberada: os checklists de 8.3 e 8.4.
- **Sem consentimento, nada é alcançável** (`EXIGEM_CONSENTIMENTO`). LGPD art. 14.
- **Dado sensível tem consentimento próprio, é opcional e NUNCA é ecoado.** `Campo.sensivel` e
  `Criterio.sensivel` disparam `CONSENTIMENTO_SENSIVEL` uma vez na conversa; recusar pula todas
  elas sem interromper o cadastro ([D7](../../docs/DECISOES.md)).
- **Nada bloqueia** além do consentimento e da faixa etária. Documento que falta vira pendência
  com lembrete, nunca parede.
- **Nunca prometer vaga, pontuação nem posição na fila**: a regra inteira está no `CLAUDE.md`
  da raiz, e há teste que varre o roteiro ([D5](../../docs/DECISOES.md),
  [D19](../../docs/DECISOES.md)).
- **A consulta mostra o `Desfecho`**, nunca a situação por opção ([D14](../../docs/DECISOES.md)).
- **`ACOMPANHAR` despacha por `etapa.tipo`**, nunca por `codigo` ([D4](../../docs/DECISOES.md)).
- **Trate `BackendIndisponivel` em toda chamada.** A conversa não morre porque um serviço
  externo tossiu: avise em linguagem de gente, guarde o que já tem, ofereça tentar de novo.
- **Estado persiste em `repo.salvar_sessao()`**, nunca em memória de processo. E
  `chave_idempotencia` nasce no primeiro turno ([D16](../../docs/DECISOES.md)).

## As duas armadilhas que já morderam

**Entrar num bloco sem desenhar a tela.** `PASSOS[estado]` **consome** a resposta;
`ENTRADAS[estado]` **desenha** a tela. Correção, retomada, o gate do sensível e a volta do
cadastro anterior usam `maquina.entrar()`, nunca `p.ir("CADASTRO")` seco, senão a próxima
mensagem é engolida como resposta de uma pergunta que nunca foi feita. No formulário isso é
`perguntar` (marca `dados["perguntou"]`) contra `responder`. Estado novo com tela própria
precisa de linha nos dois dicionários.

**Derivar o que a família não sabe responder.** Grupamento, bairro, logradouro, coordenadas,
polo, distância, "esperou na fila" e "responsável menor de 18" são todos derivados. Perguntar
qualquer um é bug de desenho, não feature.

## Antes de qualquer passo

`maquina.processar()` resolve duas coisas antes do despacho, sem salvar estado:

1. **Áudio vira texto** (`ia/transcricao.py`). Nenhum passo sabe que existe voz.
2. **Toda mensagem digitada é classificada** (`_fora_do_roteiro`); botão e comando passam
   direto. `duvida` → responde e não mexe no estado, com cota por contato
   ([D17](../../docs/DECISOES.md)). `fora_de_contexto` → repete a pergunta com `me_perdi`, sem
   consumir a mensagem e sem contar erro; nunca duas vezes seguidas, e só onde há
   `ENTRADAS[estado]` ([D18](../../docs/DECISOES.md)).

Para o modelo vai só a etapa e a pergunta **estática** do campo, nunca `pergunta_alt`, que
interpola o nome da criança.

## Rodar e verificar

```python
Maquina(BackendMock(), RedatorEstatico(), RepositorioMemoria())   # sem rede, banco ou chave
```

```bash
make contratos && make conversa
```

Injete tipado pelas portas (`BackendCreche`, `Repositorio`), nunca pelas classes concretas. Os
testes rodam contra `RepositorioMemoria` **e** `RepositorioPostgres`. Precisam continuar
cobertos: cadastro anterior achado/não achado, fora da faixa, CEP que não resolve, a régua
inteira, recusa do consentimento sensível, ordem de preferência, documento ilegível, os sete
desfechos, e a varredura que procura tela com mais de 3 botões ou promessa de vaga.
