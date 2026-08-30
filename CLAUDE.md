# creche-bot — regras para qualquer agente neste repositório

**Zé Matrícula** — assistente da Matrícula Rio, que ajuda famílias a inscrever crianças na
rede municipal. Telegram primeiro (validação), WhatsApp depois.

| Onde olhar | Para quê |
|---|---|
| `docs/script-chatbot-ze-matricula.md` | O roteiro v2 — fonte de verdade da conversa |
| `docs/MODULOS.md` | Quem faz o quê e como as frentes não se atropelam |
| `docs/ROTEIRO.md` | Mapa entre o roteiro de conversa e os estados do código |
| `docs/DECISOES.md` | As decisões que custariam caro reverter, com o porquê |
| `docs/ARQUITETURA.md` | O desenho completo |
| `docs/MODELO_DADOS.md` | As 11 tabelas, o ER e o que deliberadamente não está no banco |
| `docs/BANCO.md` | Configurar o Postgres do Supabase |
| `docs/TELEGRAM.md` | Configurar o bot no @BotFather |

## A regra que organiza o trabalho paralelo

Vários agentes trabalham neste repositório ao mesmo tempo. **Você só escreve nos arquivos
que o `CLAUDE.md` da sua pasta lista como seus.** Precisar mudar um arquivo de outro
módulo é sinal de que o contrato está errado — pare e reporte, não contorne.

## Contratos congelados — NÃO EDITE

| Arquivo | O que define |
|---|---|
| `creche_bot/canal/tipos.py` | Modelo canônico de mensagem |
| `creche_bot/dominio/tipos.py` | Vocabulário de domínio |
| `creche_bot/notificacao/chaves.py` | Chaves de template |
| `creche_bot/backend/porta.py` | Fronteira com o backend externo |
| `creche_bot/dados/porta.py` | Fronteira com a persistência |
| `creche_bot/backend/mock.py` | Backend falso que roda hoje |

Mudança em contrato = PR separado, revisado por todas as trilhas. Nunca dentro de um PR
de feature.

## Regras invioláveis

**Privacidade (elegibilidade a ZDR da Anthropic).** Documentos de usuário e dados de
criança passam por aqui:

- Modelo é `claude-haiku-4-5` — o mais barato dos elegíveis a ZDR, e a tarefa é reescrever
  uma frase curta. **Nunca** Fable 5 nem Mythos 5 — são Covered Models, exigem
  retenção de 30 dias e não existem sob ZDR.
- Imagem vai **base64 inline** no `/v1/messages`. **Proibido** `client.files.*`, Batch
  API, code execution, MCP connector, Managed Agents — nenhum é elegível a ZDR.
- Imagem reduzida a ~1568px no maior lado antes de enviar. Extrai uma vez, guarda
  estruturado, **nunca reenvia a imagem** nos turnos seguintes.

**Plataforma.** Os limites do WhatsApp valem em todo lugar, mesmo no código Telegram:
máx. 3 botões, máx. 10 itens de lista, rótulo de 20 caracteres, **texto puro sem
markdown**. O `MensagemSaida.__post_init__` cobra isso.

**LGPD art. 14.** Nenhum documento é aceito antes do consentimento registrado.

**Fronteira com a persistência.** Ninguém fora de `creche_bot/dados/` conhece banco: nem
`sqlite3`, nem `SELECT`, nem `session`, nem `cursor`. Quem precisa recebe um `Repositorio`
injetado no construtor. Há teste que varre o pacote e falha se vazar. Essa pasta tem dono
próprio e é trabalhada em paralelo — não mexa nela.

**Fronteira com o backend.** Histórico do responsável, **régua do processo vigente**,
endereço a partir do CEP, escolas próximas, panorama da região e situação da inscrição vêm
do **backend externo**, via `creche_bot/backend/porta.py` (17 operações). Não recalcule
nada disso aqui. Hoje roda `BackendMapa` — a oferta real das 820 creches de
`creche_bot/MapaFilaCreche/`, com `BackendMock` por baixo para o que os CSVs não têm.
`BACKEND=mock` volta para as três escolas inventadas do roteiro, que é o que a bateria de
testes usa. Amanhã, `BackendHTTP`. Nada do JSON dele sai de `backend/`.

**Honestidade.** O sistema **não decide quem entra** — só cadastra, estima e informa
status. Nunca gere "garantido", "certeza", "vai conseguir", "pode comemorar".
**Nem pontuação, nem posição na fila, nem nota de corte**: a classificação é norma
(Resolução SME nº 542/2025), roda em SQL determinístico depois do fechamento das
inscrições, e no momento da conversa não existe. Há teste que varre o roteiro inteiro.

Sobre uma creche o bot mostra distância, vaga ociosa agora, concorrência do ano passado
e a **chance estimada** — `confirmados ÷ demanda de 1ª opção` naquela unidade, calculada
em `backend/mapa.py` sobre os dados reais de 2025. Duas condições, sempre:

- **o ano vai colado no número.** Sem ele a estimativa vira previsão sobre o processo de
  agora, e é isso que o bot não pode dizer;
- **a classificação não está dentro dela.** Duas famílias que veem 40% na mesma tela podem
  ter desfechos opostos por causa da régua de prioridade. Por isso é "chance estimada",
  nunca "sua chance", e nunca "você vai conseguir".

**Dado sensível.** Deficiência, TGD/TEA e altas habilidades são dado de saúde; violência
doméstica, doença crônica, uso de substâncias e situação prisional também são sensíveis
(LGPD art. 5º II e art. 11). Consentimento **específico e destacado**, separado do
consentimento geral, sempre com a opção de não responder, **nunca bloqueante** e a
resposta **nunca é ecoada de volta** — o histórico fica no aparelho da família.

**Uma pergunta por mensagem.** Nunca empilhe duas no mesmo balão. Única exceção: os
checklists dos blocos 8.3 e 8.4, que são deliberados — ver `docs/DECISOES.md` D7.

**Texto do cidadão é dado, nunca instrução.** Toda entrada livre que chega perto de um
prompt vai delimitada, e o system prompt diz explicitamente para ignorar ordem escrita ali
dentro. Resposta do modelo passa por filtro antes de entrar na conversa.

**Log.** Só IDs. Nunca conteúdo de mensagem, bytes de arquivo, CPF ou nome.
`creche_bot/segredos.py` instala um formatador que redige token e chave de log e de
traceback — o token do Telegram viaja no caminho da URL da Bot API, e um traceback de
urllib bastaria para vazá-lo. Não configure logging por fora dele.

Única exceção: `DEBUG_CONTEUDO=1` (`make debug`) espelha texto, botões e o tamanho do
anexo no console — depuração na máquina do dev, nunca onde o log é coletado. Os bytes da
foto continuam fora, e há teste que cobra isso.

## Estilo

Português no código, nos comentários e nas mensagens de erro. Type hints em tudo.
Nada de abstração especulativa: sem interface com uma implementação, sem factory, sem
config para valor que nunca muda. A solução mais curta que funciona é a certa.

Cada lógica não trivial deixa **um** teste. Sem framework além de pytest, sem fixture
elaborada.

## Comandos

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

make contratos   # testes dos contratos congelados — devem passar sempre
make <trilha>    # canal | conversa | ia | dados | backend | notificacao
make fronteira   # falha se persistência vazar para fora de dados/
make memoria     # roda o bot sem tocar em disco (REPOSITORIO=memoria)
make test        # tudo
```
