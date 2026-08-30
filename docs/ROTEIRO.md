# Roteiro do Zé Matrícula — estados e telas

Mapa entre [`script-chatbot-ze-matricula.md`](script-chatbot-ze-matricula.md) (roteiro v2,
processo 195/2025) e os estados do código.

Quem mexe no **texto** edita `creche_bot/ia/persona.py` e `creche_bot/conversa/formulario.py`.
Quem mexe no **fluxo** edita `creche_bot/conversa/passos/`.

## O fluxo de inscrição

```mermaid
stateDiagram-v2
    [*] --> INICIO
    [*] --> RETOMADA: sessão viva < 72h
    INICIO --> PORTA
    PORTA --> CONSULTA_COMO: acompanhar
    PORTA --> PORTA: dúvidas
    PORTA --> FORA_DO_PERIODO: processo fechado
    PORTA --> CONSENTIMENTO: inscrever
    RETOMADA --> INICIO: começar de novo
    CONSENTIMENTO --> CPF_RESPONSAVEL: autorizo
    CPF_RESPONSAVEL --> CADASTRO_ANTERIOR: achou histórico
    CPF_RESPONSAVEL --> CADASTRO: não achou
    CADASTRO_ANTERIOR --> HORARIO: tudo certo
    CADASTRO_ANTERIOR --> ENDERECO_CEP: mudei de endereço
    CADASTRO_ANTERIOR --> CADASTRO: é outra criança
    CADASTRO --> FORA_DA_FAIXA: 4 anos ou mais
    CADASTRO --> ENDERECO_CEP
    ENDERECO_CEP --> ENDERECO_CONFIRMA
    ENDERECO_CONFIRMA --> ENDERECO_CEP: não é esse
    ENDERECO_CONFIRMA --> HORARIO: é isso
    HORARIO --> CRIT_CADUNICO
    CRIT_CADUNICO --> CRIT_NIS: sim ou não sei
    CRIT_NIS --> CRIT_ESPECIAL
    CRIT_CADUNICO --> CRIT_ESPECIAL: não
    CRIT_ESPECIAL --> CRIT_FAMILIA
    CRIT_FAMILIA --> CRIT_IRMAO: marcou irmão
    CRIT_IRMAO --> CRIT_GATE
    CRIT_FAMILIA --> CRIT_GATE
    CRIT_GATE --> CRIT_SENSIVEL: pode perguntar
    CRIT_GATE --> CONTATO: prefiro pular
    CRIT_SENSIVEL --> CRIT_ANEXO
    CRIT_ANEXO --> CONTATO
    CONTATO --> ESCOLAS
    ESCOLAS --> ESCOLAS: mais uma preferência
    ESCOLAS --> RESUMO: pronto
    RESUMO --> CORRECAO: quero corrigir
    CORRECAO --> CADASTRO
    RESUMO --> PENDENCIAS: enviar inscrição
    PENDENCIAS --> RECEBER_DOC: mandar foto aqui
    RECEBER_DOC --> PROTOCOLO
    PENDENCIAS --> PROTOCOLO: creche ou CRAS
    PROTOCOLO --> CADASTRO: outra criança
    PROTOCOLO --> ACOMPANHAR
```

## Bloco a bloco

| Roteiro | Estado | Arquivo | O que importa |
|---|---|---|---|
| 0 · Boas-vindas | `INICIO`, `PORTA` | `passos/entrada.py` | Três portas: inscrever, acompanhar, dúvida. A do meio serve inclusive para quem se inscreveu pelo site |
| 0.1 · Retomada | `RETOMADA` | `passos/entrada.py` | Sessão viva por 72h não recomeça — diz onde parou e oferece continuar |
| — · Fora do período | `FORA_DO_PERIODO` | `passos/entrada.py` | Fora da janela, inscrever não é opção. Oferece o aviso de abertura |
| 1 · Consentimento | `CONSENTIMENTO` | `passos/entrada.py` | Gate. LGPD art. 14, e o bloco 8.4 trata de saúde e violência |
| 2 · CPF do responsável | `CPF_RESPONSAVEL` | `passos/responsavel.py` | A âncora é o **adulto**, nunca a criança — ver [D12](DECISOES.md) |
| 2a · Cadastro anterior | `CADASTRO_ANTERIOR` | `passos/responsavel.py` | Dispara em 27,9%. Preenche tudo e auto-valida "esperou na fila" |
| 3, 4, 5 · Responsável, criança, documento | `CADASTRO` | `formulario.py::CADASTRO` | Lista de `Campo`. CPF > DNV > NIS, e **nenhum é obrigatório** |
| — · Fora da faixa | `FORA_DA_FAIXA` | `passos/formulario_passo.py` | Creche vai até 3 anos e 11 meses. Único bloqueio além do consentimento |
| 6 · Endereço | `ENDERECO_CEP`, `ENDERECO_CONFIRMA` | `passos/endereco.py` | CEP + número. Bairro nunca é digitado — ver [D13](DECISOES.md) |
| 7 · Horário | `HORARIO` | `passos/escolas.py` | Integral ou parcial. Sem isso a oferta não filtra |
| 8.1 · CadÚnico e NIS | `CRIT_CADUNICO`, `CRIT_NIS` | `passos/criterios.py` | **O turno mais importante do bot.** Duas perguntas da régua, uma chave só |
| 8.2 · Educação especial | `CRIT_ESPECIAL` | `passos/criterios.py` | Sensível: pede o consentimento do 8.4 antes, se ainda não pediu |
| 8.3 · Composição familiar | `CRIT_FAMILIA`, `CRIT_IRMAO` | `passos/criterios.py` | Checklist. Irmão é verificável no SGA pelo nome, sem documento |
| 8.4 · Situações sensíveis | `CRIT_GATE`, `CRIT_SENSIVEL`, `CRIT_ANEXO` | `passos/criterios.py` | Consentimento próprio, checklist único, **nunca ecoado** — ver [D7](DECISOES.md) |
| 9 · Contato | `CONTATO` | `formulario.py::CONTATO` | O canal de convocação. É a correção direta dos 7,7% que perdem a vaga |
| 10 · Escolha das creches | `ESCOLAS` | `passos/escolas.py` | Ordem montada em toques — ver [D6](DECISOES.md) |
| 11 · Resumo | `RESUMO`, `CORRECAO` | `passos/resumo.py` | Mostra o que **falta comprovar**. Nunca pontuação nem posição |
| 12 · Documentação pendente | `PENDENCIAS`, `RECEBER_DOC` | `passos/pendencias.py` | Lista de documentos condicional ao que foi declarado |
| 13 · Protocolo | `PROTOCOLO` | `passos/pendencias.py` | Oferece a segunda criança: 1.738 responsáveis fizeram isso em 2025 |
| C · Acompanhar | `CONSULTA_*` | `passos/consulta.py` | Ver abaixo |
| — · Pós-inscrição | `ACOMPANHAR` | `passos/consulta.py` | Entrada do `/status`. Comportamento vem de `etapa.tipo`, nunca do `codigo` |

## O bloco C — acompanhar

Leitura pura. Não toca no fluxo de inscrição, e é a extensão de menor risco e maior
alcance do projeto: alcança as ~62 mil famílias que se inscreveram pelo portal.

| Roteiro | Estado |
|---|---|
| C.1 · Identificação | `CONSULTA_COMO` → `CONSULTA_NUMERO` (número + nascimento) ou `CONSULTA_NOME` (nome + nascimento + filiação) |
| C.2 · Mais de uma criança | `CONSULTA_ESCOLHER` — 2,8% dos casos |
| C.3 · Situação | Sete telas, uma por `EstadoInscricao`. `CONSULTA_CONFIRMAR` quando é convocação |
| C.3b · Pendência na espera | `CONSULTA_PENDENCIA` → `CONSULTA_NIS` |
| C.4 · O que fazer daqui | `CONSULTA_ACOES` → `CONSULTA_DOC`, `CONSULTA_TELEFONE` |
| C.5 · Ativar avisos | `CONSULTA_AVISOS` — o turno mais valioso do fluxo |
| C.6 · Não encontrou | `CONSULTA_NAO_ACHOU` — três tentativas, depois atendente |

Os **dois caminhos de busca são obrigatórios**: são as rotas `/ConsultaInscricao` e
`/ConsultaCreche` do portal. O segundo existe porque nem todo mundo guarda o número, e
porque há criança sem filiação registrada na certidão.

**A regra crítica:** o que aparece é o `Desfecho` — a melhor situação entre as opções —
nunca o status bruto por opção. Ver [D14](DECISOES.md).

## O bloco 8 é montado em tempo de execução

A régua muda todo ano: entre 2023 e 2024 só 3 das 13 perguntas sobreviveram e o teto caiu
de 465 para 100 pontos. Por isso o bloco 8 **não** é uma tupla de `Campo` como os blocos 3
a 5 — o conteúdo vem de `backend.criterios_do_processo()`, agrupado por `Criterio.grupo`
(`8.1` a `8.4`), e `criterios.py` só define a **forma** de cada turno. Ver
[D15](DECISOES.md).

## As duas perguntas que o bot não faz

| Pergunta da régua | De onde vem |
|---|---|
| Esperou na fila no ano anterior | `CadastroAnterior.esperou_na_fila` — e já sai **validada**, porque a fonte é o banco |
| Responsável menor de 18 anos | Data de nascimento do responsável, capturada no bloco 3 |

As duas são perguntadas no portal hoje e a comprovação falha em cerca de 88% dos casos.
Auto-preencher converte declaração em pontuação.

Mesma lógica para grupamento, bairro, logradouro, coordenadas, polo e distância: são
derivados. Perguntar à família o que o sistema já sabe é o desenho errado.

## Comandos globais

Rodam antes de qualquer passo, em `maquina.py`.

| Comando | Efeito |
|---|---|
| `/start` | Zera a sessão e recomeça, guardando a inscrição que já existe |
| — | O mesmo vale para sessão expirada: recomeça limpa, mas o número sobrevive |
| `/status` | Salta para o fluxo de consulta (bloco C) |
| `/ajuda` | Lista os comandos |
| `/apagar` | `repo.apagar_tudo()` — direito de eliminação, LGPD art. 18 |
| `/avancar` | **Só com o mock**: empurra uma etapa para demonstrar a notificação |

## Fora do roteiro: voz e dúvida solta

Antes de qualquer decisão, `maquina.processar()` faz duas coisas:

1. **Áudio vira texto** (`ia/transcricao.py`, local). Quem falou segue o mesmo caminho de
   quem digitou, e nenhum passo sabe que existe áudio.
2. **Pergunta solta é respondida sem mudar o estado** — perguntar não faz perder o lugar na
   fila. Com cota de 8 por hora por contato e o texto do cidadão tratado como dado, nunca
   como instrução. Ver [D17](DECISOES.md).

## Regras que valem em todo passo

| Regra | Onde é cobrada |
|---|---|
| Uma pergunta por mensagem | `formulario.py`, um `Campo` por vez |
| Exceção: os checklists de 8.3 e 8.4 são deliberados | 5 perguntas invasivas em 5 turnos, para 13,6% de acerto, é péssimo desenho |
| Máx. 3 botões, 10 itens de lista, rótulo de 20 chars | `MensagemSaida.__post_init__` |
| Texto puro, sem markdown | `canal/render.py` não manda `parse_mode` |
| Eco do que foi recebido | `Campo.eco` — vale para CPF, nome e telefone |
| **Nunca ecoar resposta sensível** | O histórico fica no aparelho da família |
| Guardamos normalizado, mostramos legível | `formulario.formatar()` |
| Nada bloqueia além do consentimento e da faixa etária | Documento que falta vira pendência, não parede |
| Confiança baixa pede de novo, não grava | `DadosExtraidos.confianca == "baixa"` |
| Três falhas no mesmo campo → atendente | `formulario_passo._errar` |
| Sem consentimento não passa do início | `maquina.EXIGEM_CONSENTIMENTO` |
| **Consultar não exige o consentimento de inscrição** | É direito de acesso (art. 18), não tratamento novo — e exigi-lo barraria justamente quem se inscreveu pelo site. O consentimento de comunicação é pedido no C.5 |
| Nunca prometer vaga, pontuação ou posição na fila | `persona.SISTEMA`, `redacao._promete`, e teste que varre o roteiro |
| Estado persiste; restart não perde conversa | `repo.salvar_sessao()` a cada turno |
| Conversa que cai não vira inscrição duplicada | `dados["chave_idempotencia"]` — ver [D16](DECISOES.md) |

## O que o bot mostra sobre uma creche

Só fato verificável: **distância**, **vaga ociosa agora** e **concorrência do ano
passado**, rotulada como passado. Nunca nota de corte — a classificação só roda depois do
fechamento das inscrições, então no momento da conversa ela não existe — e nunca posição
na fila. Ver [D5](DECISOES.md).

## Para testar cada caminho

Com o `BackendMock`:

| Caminho | Como |
|---|---|
| Histórico **achou** | CPF do responsável `529.982.247-25` |
| Histórico **não achou** | Qualquer outro CPF válido |
| CEP que resolve | `22710-560`, `22775-003` ou `20220-030` — com número |
| CEP que não resolve | Qualquer outro |
| Criança fora da faixa | Nascimento com 4 anos ou mais na data de corte |
| Escola com vaga aberta | `EDI Leila Diniz` — sempre em primeiro |
| Escola sem histórico comparável | `EDI Leila Diniz` tem `concorrencia=None` |
| Processo fechado | `BackendMock(processo_aberto=False)` |
| NIS válido | Qualquer 11 dígitos — comprova `cadunico` e `bolsa_familia` de uma vez |
| Documento ilegível | Arquivo com menos de 1 KB |
| Consulta, os 7 desfechos | Números `2026-0847213` a `2026-0847277` — um por estado |
| Notificação R1 a R4 | `/avancar` depois de concluir a inscrição |

## Cada estado tem duas portas

`PASSOS[estado]` **consome** a resposta que chegou. `ENTRADAS[estado]` **desenha** a tela
pela primeira vez. Correção (bloco 11) e retomada (bloco 0.1) usam a segunda, via
`maquina.entrar()`.

Sem essa separação, voltar a um bloco engole a próxima mensagem da família: ela responderia
uma pergunta que nunca foi feita. Nem todo estado precisa de entrada própria — `entrar()`
cai no handler normal quando não há uma.
