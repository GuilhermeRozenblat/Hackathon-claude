# Roteiro: estados e telas

Mapa entre [`script-chatbot-ze-matricula.md`](script-chatbot-ze-matricula.md) e o código.
Texto de mensagem mora em `ia/persona.py` e `conversa/formulario.py`; fluxo, em
`conversa/passos/`.

```mermaid
stateDiagram-v2
    [*] --> IA_CONFIG
    [*] --> RETOMADA: sessão viva < 72h
    IA_CONFIG --> INICIO: ligou, dispensou ou ignorou
    INICIO --> PORTA
    PORTA --> CONSULTA_COMO: acompanhar
    PORTA --> FORA_DO_PERIODO: processo fechado
    PORTA --> CONSENTIMENTO: inscrever
    RETOMADA --> INICIO: começar de novo
    CONSENTIMENTO --> CADASTRO: autorizo
    CADASTRO --> FORA_DA_FAIXA: 4 anos ou mais
    CADASTRO --> CRIT_GATE: 1ª pergunta de saúde
    CRIT_GATE --> CADASTRO
    CADASTRO --> CADASTRO_ANTERIOR: CPF do responsável no histórico
    CADASTRO_ANTERIOR --> CADASTRO
    CADASTRO --> CONTATO --> RESUMO
    RESUMO --> CORRECAO: quero corrigir
    CORRECAO --> CADASTRO
    RESUMO --> ENDERECO_CEP: está tudo certo
    RESUMO --> HORARIO: endereço veio do histórico
    ENDERECO_CEP --> ENDERECO_CONFIRMA
    ENDERECO_CONFIRMA --> ENDERECO_CEP: não é esse
    ENDERECO_CONFIRMA --> HORARIO --> ESCOLAS
    ESCOLAS --> ESCOLAS: mais uma preferência
    ESCOLAS --> CONFIRMA_ESCOLAS: pronto
    CONFIRMA_ESCOLAS --> ESCOLAS: quero alterar
    CONFIRMA_ESCOLAS --> CRIT_CADUNICO: confirmar
    CRIT_CADUNICO --> CRIT_NIS: sim ou não sei
    CRIT_NIS --> CRIT_ESPECIAL
    CRIT_CADUNICO --> CRIT_ESPECIAL: não
    CRIT_ESPECIAL --> CRIT_FAMILIA
    CRIT_FAMILIA --> CRIT_IRMAO: marcou irmão
    CRIT_IRMAO --> CRIT_SENSIVEL
    CRIT_FAMILIA --> CRIT_SENSIVEL
    CRIT_SENSIVEL --> CRIT_ANEXO --> PENDENCIAS
    PENDENCIAS --> RECEBER_DOC: mandar foto aqui
    RECEBER_DOC --> PROTOCOLO
    PENDENCIAS --> PROTOCOLO: creche ou CRAS
    PROTOCOLO --> CADASTRO: outra criança
    PROTOCOLO --> ACOMPANHAR
```

## Bloco a bloco

| Roteiro | Estado | Arquivo | O que importa |
|---|---|---|---|
| 0.0 · IA opcional | `IA_CONFIG` | `passos/ia.py` | Fora do roteiro. Uma tela: ligar a IA com a chave da pessoa, ou seguir sem. Ninguém fica preso ([D20](DECISOES.md)) |
| 0 · Boas-vindas | `INICIO`, `PORTA` | `passos/entrada.py` | Três portas: inscrever, acompanhar, dúvida |
| 0.1 · Retomada | `RETOMADA` | `passos/entrada.py` | Sessão viva por 72h não recomeça: diz onde parou |
| extra · Fora do período | `FORA_DO_PERIODO` | `passos/entrada.py` | Fora da janela, oferece o aviso de abertura |
| extra · Consentimento | `CONSENTIMENTO` | `passos/entrada.py` | Gate, LGPD art. 14. Sem ele nada é gravado |
| 1-3 · Cadastro | `CADASTRO` | `formulario.py::CADASTRO` | CPF e nascimento da criança, origem escolar, matrícula, saúde, filiação, responsável. Uma pergunta por mensagem |
| extra · Cadastro anterior | `CADASTRO_ANTERIOR` | `passos/responsavel.py` | Dispara em 27,9% no CPF do responsável. Aproveita endereço e auto-valida "esperou na fila" |
| extra · Dado sensível | `CRIT_GATE` | `passos/criterios.py` | Consentimento do art. 11, uma vez, válido para o resto |
| extra · Fora da faixa | `FORA_DA_FAIXA` | `passos/formulario_passo.py` | Creche vai até 3 anos e 11 meses. Único bloqueio além do consentimento |
| 4 · Contato | `CONTATO` | `formulario.py::CONTATO` | O canal de convocação, a correção dos 7,7% que perdem a vaga |
| 5 · Resumo | `RESUMO`, `CORRECAO` | `passos/resumo.py` | Repete o declarado. Nunca pontuação, nunca resposta sensível |
| 6 · Escolas | `ENDERECO_*`, `HORARIO`, `ESCOLAS` | `passos/endereco.py`, `escolas.py` | CEP + número, nunca bairro digitado. Ordem montada em toques |
| 7 · Confirmação | `CONFIRMA_ESCOLAS` | `passos/escolas.py` | A lista final, na ordem, antes de valer |
| extra · Régua | `CRIT_*` | `passos/criterios.py` | Fora do roteiro, e é o que captura o NIS. Roda depois do bloco 7 porque gera a pendência do 8 |
| 8 · Documentação | `PENDENCIAS`, `RECEBER_DOC` | `passos/pendencias.py` | Lista condicional ao declarado. Chat, creche ou CRAS |
| 8 · Protocolo | `PROTOCOLO` | `passos/pendencias.py` | Oferece a segunda criança: 1.738 responsáveis fizeram isso em 2025 |
| C · Acompanhar | `CONSULTA_*` | `passos/consulta.py` | Ver abaixo |
| extra · Pós-inscrição | `ACOMPANHAR` | `passos/consulta.py` | Entrada do `/status`. Despacha por `etapa.tipo`, nunca por `codigo` |

## Onde o código não segue o roteiro, e por quê

| Roteiro pede | O que o bot faz | Por quê |
|---|---|---|
| Bloco 1 busca pelo CPF da **criança** | Busca pelo CPF do **responsável**, perguntado no bloco 3 | `backend/porta.py` é congelado e só tem `buscar_por_responsavel` ([D12](DECISOES.md)) |
| Bloco 6 aceita "CEP **ou bairro**" | Só CEP + número | Bairro digitado gerou 1.608 grafias para ~925 bairros ([D13](DECISOES.md)) |
| Bloco 6 mostra "nota de corte: X pontos" | Distância, vaga ociosa, concorrência e chance estimada de 2025 | A classificação não existe antes do fechamento ([D5](DECISOES.md), [D19](DECISOES.md)) |
| Bloco 5 exibe "necessidades especiais" no resumo | Guarda, mas não repete | Dado de saúde ecoado num histórico que fica no aparelho da família |
| Bloco 8 sempre pergunta como entregar | Só quando há documento pendente | Sem pendência, mandar a família procurar papel é fazê-la voltar sem resolver |
| Nada | Pergunta o horário da vaga | `escolas_proximas()` filtra por horário; sem ele a oferta não sai |
| Nada | Pergunta antes se a pessoa quer IA | A chave é dela; seguir sem avisar seria decidir por ela ([D20](DECISOES.md)) |

## O bloco C: acompanhar

Leitura pura, não toca no fluxo de inscrição, e alcança as ~62 mil famílias que se
inscreveram pelo portal.

| Roteiro | Estado |
|---|---|
| C.1 · Identificação | `CONSULTA_COMO` → `CONSULTA_NUMERO` (número + nascimento) ou `CONSULTA_NOME` (nome + nascimento + filiação) |
| C.2 · Mais de uma criança | `CONSULTA_ESCOLHER`, 2,8% dos casos |
| C.3 · Situação | Sete telas, uma por `EstadoInscricao`; `CONSULTA_CONFIRMAR` quando é convocação |
| C.3b · Pendência na espera | `CONSULTA_PENDENCIA` → `CONSULTA_NIS` |
| C.4 · O que fazer daqui | `CONSULTA_ACOES` → `CONSULTA_DOC`, `CONSULTA_TELEFONE` |
| C.5 · Ativar avisos | `CONSULTA_AVISOS`, o turno mais valioso do fluxo |
| C.6 · Não encontrou | `CONSULTA_NAO_ACHOU`, três tentativas, depois atendente |

Os **dois caminhos de busca são obrigatórios**: são as rotas `/ConsultaInscricao` e
`/ConsultaCreche` do portal, porque nem todo mundo guarda o número, e há criança sem filiação
na certidão. **A regra crítica:** o que aparece é o `Desfecho`, nunca o status bruto por opção
([D14](DECISOES.md)).

## A régua é montada em tempo de execução

O conteúdo vem de `backend.criterios_do_processo()`, agrupado por `Criterio.grupo` (`8.1` a
`8.4`); `criterios.py` define só a **forma** de cada turno ([D15](DECISOES.md)). A pergunta de
educação especial do grupo `8.2` não é refeita, porque o bloco 2 já perguntou.

**Duas perguntas da régua o bot nunca faz**, porque já sabe: "esperou na fila no ano anterior"
(vem de `CadastroAnterior`, e sai **validada**) e "responsável menor de 18" (da data de
nascimento). As duas são perguntadas no portal hoje e a comprovação falha em ~88% dos casos.
Mesma lógica para grupamento, bairro, logradouro, coordenadas, polo e distância: são
derivados. Perguntar à família o que o sistema já sabe é o desenho errado.

## Comandos globais

Rodam antes de qualquer passo, em `maquina.py`.

| Comando | Efeito |
|---|---|
| `/start` | Zera a sessão e recomeça, guardando a inscrição existente e a decisão sobre a IA. Sessão expirada faz o mesmo |
| `/status` | Salta para o bloco C |
| `/ia` | Liga, troca ou remove a chave da Anthropic. Chave colada **sozinha** entra por aqui também, senão viraria resposta do campo no ar ([D20](DECISOES.md)) |
| `/ajuda` | Lista os comandos |
| `/apagar` | `repo.apagar_tudo()`, LGPD art. 18 |
| `/avancar` | Empurra uma etapa para demonstrar a notificação. Existe enquanto o backend for o mock — o `BackendMapa` herda dele, então vale nos dois |
| `/demo` | Carrega uma das três famílias de demonstração nesta conversa, ou sai da demo. Ver [o modo demo](#o-modo-demo) |

## O modo demo

Quem vai avaliar o bot em cinco minutos não vai responder quatorze perguntas para chegar à tela
das creches, e não tem como adivinhar qual CPF o histórico reconhece. `/demo` abre uma lista com
três famílias fictícias e a saída de volta. Cada uma escreve o contexto na sessão de quem tocou
e devolve a tela de dentro do roteiro — persona é só um dicionário, porque `proximo_campo` pula
todo campo já respondido. Está em `conversa/passos/demo.py`.

| Opção | Onde entra | O que mostra |
|---|---|---|
| Escolhendo creche | `ESCOLAS`, CEP da Barra | Distância, vaga ociosa, chance estimada com o ano, panorama da região. Dali segue: escolher, régua, pendência, protocolo |
| Já inscrita | `PROTOCOLO`, CEP do Catete | Inscreve de verdade pelo `pendencias.enviar`, então `/status` e `/avancar` funcionam |
| Volta de 2025 | `CADASTRO_ANTERIOR` | O reconhecimento pelo CPF do responsável, com o endereço reaproveitado |
| Sem demo, do zero | `INICIO` | Sai da demonstração e volta ao bloco 0 |

Tocar numa família **substitui** o que estiver preenchido na conversa, e o menu avisa. O
consentimento é gravado com versão `demo/…`, para no banco dar para separar do de verdade.

`scripts/semear_demo.py` é o outro lado: enche o banco com treze conversas que param em pontos
diferentes do roteiro, para o painel ter funil de abandono, régua respondida, creches escolhidas
e fila de notificação. Os contatos ficam no canal `demo`, nunca `telegram` — sem identidade de
Telegram a entrega não manda mensagem para ninguém, e `make demo-limpar` desfaz tudo.

## Fora do roteiro: voz e classificação

Antes de qualquer decisão, e **sem salvar estado**:

1. **Áudio vira texto** (`ia/transcricao.py`, local). Nenhum passo sabe que existe voz.
2. **Toda mensagem digitada é classificada** ([D18](DECISOES.md)); botão e comando passam
   direto. `duvida` é respondida sem mexer no estado, com cota de 8/hora por contato
   ([D17](DECISOES.md)); `fora_de_contexto` redesenha a tela com o texto `me_perdi`, sem
   consumir a mensagem e sem contar erro, e nunca duas vezes seguidas, senão vira loop.

## Regras que valem em todo passo

| Regra | Onde é cobrada |
|---|---|
| Uma pergunta por mensagem | `formulario.py`, um `Campo` por vez |
| Exceção: os checklists de 8.3 e 8.4 | 5 perguntas invasivas em 5 turnos, para 13,6% de acerto, é péssimo desenho |
| Máx. 3 botões, 10 itens, rótulo de 20 chars, texto puro | `MensagemSaida.__post_init__` e `canal/render.py` |
| Eco do que foi recebido, **nunca** de resposta sensível | `Campo.eco`; o histórico fica no aparelho da família |
| Guardamos normalizado, mostramos legível | `formulario.formatar()` |
| Nada bloqueia além do consentimento e da faixa etária | Documento que falta vira pendência, não parede |
| Confiança baixa pede de novo, não grava | `DadosExtraidos.confianca == "baixa"` |
| Três falhas no mesmo campo → atendente | `formulario_passo._errar` |
| Sem consentimento não passa do início | `maquina.EXIGEM_CONSENTIMENTO` |
| **Consultar não exige o consentimento de inscrição** | É direito de acesso (art. 18), e exigi-lo barraria quem se inscreveu pelo site. O de comunicação é pedido no C.5 |
| Nunca prometer vaga, pontuação ou posição na fila | `persona.SISTEMA`, `redacao._promete`, e teste que varre o roteiro |
| Estado persiste; restart não perde conversa | `repo.salvar_sessao()` a cada turno |
| Conversa que cai não vira inscrição duplicada | `dados["chave_idempotencia"]` ([D16](DECISOES.md)) |

**Sobre uma creche:** distância, vaga ociosa agora no grupamento pedido, concorrência do ano
passado e a chance estimada de 2025, com o ano colado em todo número derivado, nunca "sua chance".
Nunca nota de corte, pontuação ou posição na fila.

## Cada estado tem duas portas

`PASSOS[estado]` **consome** a resposta que chegou. `ENTRADAS[estado]` **desenha** a tela pela
primeira vez. Correção, retomada, o gate do sensível e a volta do cadastro anterior usam a
segunda, via `maquina.entrar()`.

Sem essa separação, voltar a um bloco engole a próxima mensagem da família: ela responderia
uma pergunta que nunca foi feita. Estado novo com tela própria precisa de linha nos dois
dicionários.

## Para testar cada caminho

Com `BACKEND=mock` (`make roteiro`), que é o que a bateria usa. No padrão (`BackendMapa`) CEP,
histórico e consulta se comportam igual. O que muda são as creches, que passam a ser as reais
da região.

| Caminho | Como |
|---|---|
| Histórico achou · não achou | CPF `529.982.247-25` · qualquer outro CPF válido |
| CEP que resolve · que não resolve | `22710-560`, `22775-003`, `20220-030` (com número) · qualquer outro |
| Criança fora da faixa | Nascimento com 4 anos ou mais na data de corte |
| Escola com vaga aberta · sem histórico comparável | `EDI Leila Diniz` (sempre em primeiro, e tem `concorrencia=None`) |
| Processo fechado | `BackendMock(processo_aberto=False)` |
| NIS válido | Qualquer 11 dígitos, comprova `cadunico` e `bolsa_familia` de uma vez |
| Documento ilegível | Arquivo com menos de 1 KB |
| Consulta, os 7 desfechos | Números `2026-0847213` a `2026-0847277` |
| Notificação R1 a R4 | `/avancar` depois de concluir a inscrição |
