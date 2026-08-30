# Script do Chatbot "Zé Matrícula" — Inscrição em Creche

**Versão 2.0** · Reescrita a partir da régua real do processo 195/2025, do portal matricula.rio e da base histórica de 5 processos seletivos (837.179 opções, 2021–2025).

Linguagem pensada para WhatsApp: mensagens curtas, uma pergunta por vez, botões quando possível em vez de texto livre.

> ### ⚠️ Leia antes de implementar
>
> **A régua de classificação muda todo ano.** Entre 2023 e 2024 apenas 3 das 13 perguntas sobreviveram e o teto caiu de 465 para 100 pontos. O bloco 8 deste script é o **retrato do processo 195 (2025)** — serve de referência de redação, não de conteúdo fixo.
>
> Na implementação, o bloco 8 é **montado em tempo de execução** a partir da tabela `ic.pergunta_processo` do processo vigente, ordenado por `ordem`, pulando as perguntas marcadas como `autopreenchivel`. Régua escrita à mão no código quebra na virada do ano.
>
> Para 2026 vale a **Resolução SME nº 542/2025**, ainda não carregada.

---

## Escopo

Este script cobre **creche: 0 a 3 anos e 11 meses** (Berçário, Maternal I, Maternal II). Não cobre pré-escola nem ensino fundamental.

O bot é **canal complementar**. O sistema de registro continua sendo o matricula.rio — a inscrição gerada aqui é gravada lá, com a hierarquia `prm_id / plm_id / ipl_id`.

---

## 0. Boas-vindas

> 👋 Oi! Eu sou o **Zé Matrícula**, assistente da Matrícula Carioca.
> Posso te ajudar a inscrever sua criança em creche da rede municipal. Leva uns 5 minutos, e a gente pode parar e continuar depois.

**[Botões]** `Quero inscrever` · `Já tenho inscrição, quero acompanhar` · `Tenho dúvidas`

*→ Se `acompanhar`: vai para o **Bloco C** — serve inclusive para quem se inscreveu pelo site.*
*→ Se `dúvidas`: FAQ + encaminhamento para o 1746 ou o WhatsApp oficial da SME.*

### 0.1 Retomada automática

*(⚙️ Se existe sessão aberta e não expirada para este número, o bot não recomeça)*

> Oi de novo! A gente parou no endereço. Quer continuar de onde paramos?

**[Botões]** `Continuar` · `Começar de novo`

*(⚙️ Sessão expira em 72h. Toda transição grava estado + payload parcial. Chave de idempotência criada no primeiro turno — sem ela, conversa que cai vira inscrição duplicada.)*

---

## 1. Consentimento

*(🔒 Gate obrigatório. Algumas perguntas mais à frente tratam de saúde, violência e situação prisional — dado sensível pela LGPD. Sem base legal, não pode nem ser gravado.)*

> Antes de começar, preciso da sua autorização para usar esses dados **só para a inscrição na creche**. Você pode cancelar quando quiser, é só me mandar mensagem.

**[Botões]** `Autorizo` · `Ler o termo primeiro`

*(Se `Ler o termo`: link para o Termo de Uso do matricula.rio, versão 1.1, e volta com os mesmos botões.)*

*(⚙️ Grava consentimento `finalidade = inscricao`. O consentimento para dado sensível é pedido separadamente no bloco 8.4, só para quem chega lá.)*

---

## 2. Identificação do responsável

*(💡 Começa pelo responsável, não pela criança. O CPF do adulto é mais confiável, é a âncora da conta, e é o que reconhece reinscrição e irmãos. Exigir CPF de criança de 0 a 3 anos no primeiro turno derruba família na porta.)*

> Pra começar, qual é o **seu CPF**? (só os números)

*(usuário envia)*

*(⚙️ Valida dígito verificador. Se inválido: "Esse CPF não confere. Pode conferir os números?" — 3 tentativas e oferece atendente.)*

*→ Sistema consulta processos anteriores*

### 2a. Se encontrou cadastro anterior — 27,9% dos casos

> 🎉 Achei seu cadastro do ano passado:
> **Ana Beatriz da Silva**, nascida em 10/01/2024
> Rua Franz Weissmann, 100 — Curicica
>
> Está tudo certo ainda?

**[Botões]** `Tudo certo` · `Mudei de endereço` · `É outra criança`

*(⚙️ **Preenche automaticamente a pergunta 11 da régua** — "esperou na fila no ano anterior" — e já marca como validada, porque a fonte é o próprio banco. Hoje 14,5% declaram isso e só 12,1% conseguem comprovar. Aqui sai comprovado de graça.)*

*→ `Tudo certo` pula para o Bloco 7. `Mudei de endereço` vai para o 6. `É outra criança` vai para o 4.*

### 2b. Se não encontrou

> Não achei nada ainda, sem problema. Vamos preencher juntos. 🙂

---

## 3. Dados do responsável

> Qual é o seu **nome completo**? (sem abreviar)

*(usuário responde)*

> Recebido: **Maria da Silva Santos** ✅
> E qual a sua **data de nascimento**? (dia/mês/ano)

*(usuário responde)*

*(⚙️ **Responde sozinha a pergunta 13 da régua** — "responsáveis com idade menor que 18 anos", critério de desempate. Não pergunte isso ao usuário.)*
*(⚠️ Atenção: os critérios "60 anos ou mais" e "mãe adolescente" existiram apenas de 2021 a 2023. Não existem mais. Não derive esses.)*

> Qual a sua relação com a criança?

**[Botões]** `Mãe` · `Pai` · `Avó/Avô` · `Responsável legal` · `Outro`

---

## 4. Dados da criança

> Agora a criança. Qual o **nome completo** dela? (sem abreviar)

*(usuário responde)*

> E a **data de nascimento**? (dia/mês/ano)

*(usuário responde)*

*(⚙️ **Deriva o grupamento** — nunca perguntar. "Berçário" e "Maternal I" são vocabulário interno da rede, não de família.)*
*(⚙️ Bandas confirmadas na base de 2025, medidas na data de corte do processo: menos de 24 meses = Berçário · 24 a 35 = Maternal I · 36 a 47 = Maternal II. Maternal I e II com 0,0% fora da faixa em 91 mil linhas.)*

**Se a criança estiver fora da faixa de creche:**

> Pela data de nascimento, a Ana vai ter 4 anos e 3 meses em março — já está fora da faixa da creche, que vai até 3 anos e 11 meses. O caminho é a **pré-escola**.
> Quer que eu te explique como fazer essa inscrição?

*(⚠️ Falhe cedo e explique. Não deixe a família descobrir isso no resultado.)*

> A criança é **menino** ou **menina**?

**[Botões]** `Menino` · `Menina`

> A filiação (nome da mãe e/ou pai) consta na **certidão de nascimento** dela?

**[Botões]** `Consta` · `Não consta`

*(💡 O portal trata isso explicitamente nas duas telas de consulta. É a chave alternativa de busca quando não há número de inscrição, e existe justamente para crianças sem filiação registrada.)*

> Pode me passar o **nome completo da mãe e/ou do pai**, como está na certidão?
> *(se `Não consta`: "Pode me passar o nome do responsável legal pela criança?")*

---

## 5. Documento da criança

> Você tem o **CPF da criança**?

**[Botões]** `Tenho o CPF` · `Não tenho, mas tenho a Declaração de Nascido Vivo` · `Não tenho nenhum dos dois`

**Se `Tenho o CPF`:** > Pode mandar? (só os números)

**Se `DNV`:** > Manda o número da **Declaração de Nascido Vivo** — é aquele papel da maternidade.

**Se `Não tenho nenhum dos dois`:** > Sem problema. Você sabe o **NIS** da criança? Se não souber, seguimos assim mesmo e a equipe confere depois.

*(⚙️ Chave natural da SME nesta ordem de precedência: **CPF → DNV → NIS**. Pelo menos uma é necessária para reconciliar a criança entre processos. Sem nenhuma, a inscrição segue mas fica marcada para conferência.)*

---

## 6. Endereço

> Onde vocês moram? Me manda o **CEP** e o **número** da casa.

*(usuário responde)*

*(⚠️ **Nunca aceite bairro nem rua digitados.** Na base histórica o campo livre gerou 1.608 grafias para ~925 bairros — "Inhaúma" tem 13 variantes. O CEP, ao contrário, é 100% preenchido e 100% válido desde 2024.)*
*(⚙️ Servidor deriva logradouro, bairro e coordenadas. Sem o número, a precisão cai para ~1,4 km — o suficiente para errar a creche certa dentro do raio de 2 km que as famílias aceitam.)*

> Confere se é aqui?
> 📍 **Rua Franz Weissmann, 100 — Curicica**

**[Botões]** `É isso` · `Não é esse endereço`

*(💡 Este é o único momento em que a família vê o bairro: para confirmar, nunca para digitar.)*

---

## 7. Horário

> Você precisa de vaga em **tempo integral** (dia todo) ou **parcial** (meio período)?

**[Botões]** `Integral` · `Parcial`

*(💡 93,8% do Berçário é integral, mas 6,2% é parcial — e no Maternal II a parcial chega a 12,5%. O campo particiona a oferta de verdade: sem ele a sugestão de escolas não filtra.)*

---

## 8. Critérios de prioridade

*(⚙️ **Bloco gerado da tabela do processo vigente.** O que está abaixo é o processo 195/2025. Ordem, pesos e textos vêm de `ic.pergunta_processo` + `ic.pergunta_catalogo`.)*

> Agora as perguntas que definem a prioridade na fila. São rápidas, e cada "sim" comprovado conta pontos.

### 8.1 CadÚnico e Bolsa Família — 51 + 2 pontos

*(🎯 **Este é o turno mais importante do bot inteiro.** 48,9% das famílias declaram CadÚnico. Hoje só 6,8% conseguem comprovar, e por isso 93,8% das inscrições terminam com pontuação validada zero. Capturar o NIS aqui é a razão de existir do projeto.)*

> Sua família está inscrita no **CadÚnico**, ou recebe **Bolsa Família** ou **Cartão Carioca**?

**[Botões]** `Sim` · `Não` · `Não sei`

*(💡 Duas perguntas da régua num turno só, porque validam pela mesma chave: o NIS.)*

**Se `Sim` ou `Não sei`:**

> Me manda o número do **NIS** (11 dígitos).
> Ele está no Cartão do Cidadão, no cartão do Bolsa Família ou no app CadÚnico.
> 📌 É o número mais importante da inscrição — sozinho ele vale metade da pontuação.

**[Botão extra]** `Não estou achando o número`

**Se `Não estou achando`:**

> Tudo bem. Deixo marcado e a gente confere depois — vou te lembrar por aqui.
> Se achar, é só me mandar a qualquer momento antes de **12/12**.

*(⚙️ Nunca trave a inscrição por falta do NIS. Grava a resposta, marca validação pendente e agenda o fluxo R1.)*
*(⚙️ Com o NIS, o servidor consulta CadÚnico e Bolsa Família — as duas perguntas validam de uma vez.)*

### 8.2 Educação especial — 25 pontos

> A criança tem alguma **deficiência**, **transtorno do desenvolvimento** (como TEA) ou **altas habilidades**?

**[Botões]** `Sim` · `Não`

**Se `Sim`:**

*(🔒 Primeira pergunta sensível — pede consentimento específico se ainda não foi pedido. Ver 8.4.)*

> Pode mandar uma **foto do laudo** ou do relatório médico? Pode ser foto do papel mesmo, só precisa dar pra ler. 📎

**[Botão extra]** `Não tenho agora`

*(⚙️ Se não tiver: grava pendente e agenda R1. Não bloqueia.)*

### 8.3 Composição familiar — 4 + 2 + desempate

> Marque o que se aplica à sua família (pode marcar mais de uma, ou nenhuma):

**[Seleção múltipla]**
- `A criança é criada por só uma pessoa responsável` *(monoparental — 4 pts)*
- `A família está no Brasil como refugiada` *(2 pts)*
- `A criança tem irmão ou irmã já matriculado na rede` *(desempate)*

**Se marcou monoparental:** > Manda uma foto da **certidão de nascimento** da criança 📎

**Se marcou refugiada:** > Manda uma foto do **protocolo de refúgio** ou do documento do CONARE 📎

**Se marcou irmão:**
> Qual o **nome completo** do irmão ou irmã que já estuda na rede?

*(⚙️ Verificável no SGA a partir do nome. Não precisa de documento. Hoje 35,9% marcam e só 6,0% conseguem validar — é ganho puro.)*

### 8.4 Situações sensíveis — 14 pontos somados

*(🔒 **Gate de consentimento para dado sensível.** Se ainda não foi dado:)*

> As próximas perguntas são sobre situações delicadas da família. Elas contam pontos na fila, mas você não é obrigada a responder.
> Posso perguntar?

**[Botões]** `Pode perguntar` · `Prefiro pular`

**Se `Pode perguntar`:**

> Marque o que se aplica. Nada aqui aparece pra ninguém além de quem analisa a inscrição.

**[Seleção múltipla]**
- `Alguém de casa está em situação de violência doméstica` *(4 pts)*
- `Algum responsável pela criança tem deficiência` *(3 pts)*
- `Alguém de casa tem doença crônica grave` *(3 pts)*
- `Alguém de casa faz uso abusivo de álcool ou outras drogas` *(2 pts)*
- `Alguém de casa está preso ou saiu da prisão nos últimos 5 anos` *(2 pts)*

*(💡 **Cinco perguntas da régua em um turno só, de propósito.** Individualmente disparam entre 1,6% e 5,3%. Somadas, 13,6% marcam ao menos uma, com média de 0,18 marcações. Cinco turnos invasivos para esse aproveitamento é péssimo desenho — e pior num canal cujo histórico fica no aparelho da família.)*

*(⚠️ **Nunca ecoar essas respostas de volta.** O eco de confirmação vale para CPF, nome e telefone. Não vale para isso.)*

**Se marcou alguma:**

> Se você tiver algum documento sobre isso (laudo, boletim de ocorrência, declaração), pode mandar agora. Se não tiver, tudo bem — a inscrição segue e a equipe entra em contato. 📎

*(⚠️ **Nunca bloqueante.** Exigir boletim de ocorrência de uma vítima de violência dentro de um chat, como condição para inscrever a criança, é violento.)*

### 8.5 As duas perguntas que o bot NÃO faz

| Pergunta da régua | Por que não perguntar |
|---|---|
| **11.** Esperou na fila no ano anterior *(2 pts)* | Está no banco. 27,9% das crianças de 2025 já constavam em 2024. Auto-preenchida no bloco 2a, e **já sai validada**. |
| **13.** Responsável menor de 18 anos *(desempate)* | Deriva da data de nascimento capturada no bloco 3. |

*(💡 Hoje as duas são perguntadas no portal e exigem comprovação que falha em cerca de 88% dos casos. Auto-preencher converte declaração em pontuação.)*

---

## 9. Contato

> Esse número que você está usando serve para eu te avisar sobre a vaga?

**[Botões]** `Pode ser esse` · `Prefiro outro número`

**Se `outro`:** > Qual número? (com DDD)

> Tem **outro contato** de alguém da família, caso eu não consiga falar com você?

**[Botões]** `Tenho outro contato` · `Não tenho`

*(🎯 Em 2025, **5.519 inscrições (7,7%) foram convocadas e perderam a vaga** — concentradas em Pilares (24,9%), Santa Teresa (23,6%), Gávea (22,9%) e Bangu (471 famílias). O canal de contato é a correção direta desse vazamento.)*

> Quer me passar um **e-mail** também? É opcional.

**[Botões]** `Passar e-mail` · `Pular`

---

## 10. Escolha das creches

> Achei estas creches perto de você que atendem **turma de bebês** em **tempo integral**:
>
> 1️⃣ **EDI Leila Diniz** — 400 m (uns 6 min a pé) · 🟢 tem vaga aberta agora
> 2️⃣ **CM Criança do Futuro** — 1,2 km · ano passado, 5 famílias por vaga
> 3️⃣ **CM Maria da Conceição S. de Carvalho** — 1,8 km · RIO 2 · ano passado, 13 famílias por vaga
>
> Quais você quer? Pode escolher quantas quiser, na ordem de preferência.

**[Seleção múltipla ordenável]**

*(⚠️ **Não mostre "nota de corte".** A classificação só roda em 13/01, depois do fechamento das inscrições — no momento da conversa ela não existe. E o teto da régua foi 465 em 2023 e 100 em 2024, então histórico não é comparável. Prometer isso sobre alocação de vaga pública é passivo.)*
*(✅ O que dá para mostrar, porque é fato verificável: **distância**, **vaga ociosa agora**, e **concorrência do ano passado** rotulada como passado.)*

*(💡 **Não force 5 opções.** Em 2025 a taxa de atendimento foi 68,8% com 1 opção e 69,7% com 5. O número de opções não muda o desfecho — a oferta perto muda.)*
*(⚙️ Raio padrão de 2 km: 72,8% dos confirmados ficaram na própria 1ª opção, e entre os que trocaram, 82,9% andaram até 2 km, mediana 0,91 km.)*
*(⚙️ Use o campo **Polo** do catálogo do matricula.rio — é a unidade real de classificação. Polo não é microárea: coincidem em só 21,5% das unidades.)*
*(💡 Mostre o campo **Referência** quando existir ("RIO 2", "PARK SHOPPING"). A família reconhece o lugar pelo apelido, não pelo nome oficial.)*

---

## 11. Resumo

> Vou repetir tudo antes de enviar:
>
> 👶 **Ana Beatriz da Silva** — turma de bebês (Berçário), tempo integral
> 📍 Rua Franz Weissmann, 100 — Curicica
> 🏫 1. EDI Leila Diniz · 2. CM Criança do Futuro
> 📞 (21) 99887-7665
>
> ✅ **Já comprovado:** CadÚnico
> ⏳ **Falta comprovar:** laudo da educação especial
>
> Está tudo certo?

**[Botões]** `Enviar inscrição` · `Quero corrigir algo`

*(Se `corrigir`: bot pergunta qual campo e volta ao bloco dono daquele campo.)*

*(⚠️ **Nunca mostre pontuação nem posição na fila.** A classificação roda depois do fechamento. Prometer posição aqui é criar expectativa que a SME não pode honrar. O que é acionável e deve aparecer é **o que falta comprovar**.)*

---

## 12. Documentação pendente

*(Só aparece se sobrou algo pendente.)*

> Falta só o **laudo da educação especial**. Como você prefere enviar?

**[Botões]** `Mandar foto aqui` · `Levar na creche` · `Levar num CRAS`

*(⚠️ O WhatsApp não é uma opção entre três — é o caminho recomendado. Hoje a comprovação acontece depois, presencialmente, e valida 8,0% dos casos. Capturar a evidência dentro da conversa é o produto. As outras duas são alternativa para quem não consegue.)*

### 12a. Mandar foto aqui
> Manda a foto do laudo 📎 Pode ser foto do papel mesmo.

> Recebido! ✅ A equipe vai conferir e eu te aviso por aqui.

### 12b. Levar na creche
> Combinado. Leve:
> 📄 **Laudo médico ou relatório** da criança
> 📍 EDI Leila Diniz — Estrada de Curicica, 200
> 🕐 Segunda a sexta, 8h às 16h

### 12c. Levar num CRAS
> Combinado. Leve:
> 📄 **Laudo médico ou relatório** da criança
> 📍 CRAS mais próximos: [lista]
> 🕐 Segunda a sexta, 9h às 17h
>
> Quando o CRAS receber, eu te aviso. E aviso de novo quando chegar na creche. ✅

*(🎯 **Este é o buraco do fluxo atual.** Hoje o documento sai do CRAS e ninguém avisa a família se chegou. O critério é descartado em silêncio. Precisa de estado explícito: `entregue no CRAS` → `recebido pela creche` → `validado`, com aviso a cada passo.)*

### Documento por critério

| Critério | O que comprova |
|---|---|
| CadÚnico · Bolsa Família · Cartão Carioca | **NIS** — número, não documento |
| Educação especial | Laudo ou relatório médico |
| Responsável com deficiência | Laudo |
| Doença crônica grave | Laudo ou relatório médico |
| Família monoparental | Certidão de nascimento |
| Refugiado | Protocolo de refúgio ou documento do CONARE |
| Violência doméstica | B.O., medida protetiva ou encaminhamento — **opcional** |
| Uso abusivo de substâncias | Declaração ou encaminhamento — **opcional** |
| Situação prisional | Declaração — **opcional** |
| Irmão matriculado | Nada. Consulta ao SGA pelo nome |
| Esperou na fila ano anterior | Nada. O banco responde |
| Responsável menor de 18 | Nada. Deriva do cadastro |

*(⚠️ Lista genérica de documentos faz a família levar o papel errado. A lista tem que ser condicional ao que ela declarou.)*

---

## 13. Protocolo

> Pronto! 🎉
> Sua inscrição é a **2026-0847213**.
> Guarde esse número. O resultado sai em **21/01/2026** e eu te aviso por aqui.

> Quer inscrever **outra criança**? Já tenho seus dados, é bem mais rápido.

**[Botões]** `Sim, outra criança` · `Não, terminei`

*(💡 1.738 responsáveis inscreveram 2 ou mais crianças em 2025. Reaproveita responsável, endereço e consentimentos — só a pergunta do irmão matriculado muda para a segunda criança.)*

> Se mudar de endereço ou de telefone, é só me mandar mensagem. Isso é importante: é por aqui que eu vou te chamar quando a vaga sair.

---

## C. Acompanhar uma inscrição já feita

*(Entrada pelo botão `Já tenho inscrição, quero acompanhar` do bloco 0.)*

*(💡 **Serve para quem se inscreveu pelo site também.** É leitura pura, não toca no fluxo de inscrição, e alcança as ~62 mil famílias que usaram o matricula.rio normalmente — inclusive os 7,7% que perdem a vaga já convocados. É a extensão de menor risco e maior alcance do projeto.)*

### C.1 Identificação

> Vou procurar sua inscrição. Você tem o **número dela** em mãos?

**[Botões]** `Tenho o número` · `Não tenho o número`

**Se `Tenho o número`:**

> Me manda o **número da inscrição** e a **data de nascimento** da criança.

**Se `Não tenho o número`:**

> Sem problema, dá pra achar assim também. Qual o **nome completo da criança**? (sem abreviar)

*(usuário responde)*

> E a **data de nascimento** dela?

*(usuário responde)*

> A filiação (nome da mãe e/ou pai) consta na **certidão de nascimento**?

**[Botões]** `Consta` · `Não consta`

> Pode me passar o **nome completo da mãe ou do pai**, como está na certidão?
> *(se `Não consta`: "Pode me passar o nome do responsável legal?")*

*(⚙️ São exatamente os dois caminhos de busca das rotas `/ConsultaInscricao` e `/ConsultaCreche` do portal: **número + nascimento**, OU **nome + nascimento + filiação**. Manter os dois é obrigatório — o segundo existe porque nem todo mundo guarda o número.)*

### C.2 Se o responsável tem mais de uma criança

*(⚙️ Dispara em 2,8% dos casos — 1.738 responsáveis em 2025.)*

> Achei duas inscrições no seu nome. Qual delas você quer ver?

**[Botões]** `Ana Beatriz (10/01/2024)` · `Pedro Henrique (03/2022)` · `Ver as duas`

### C.3 Mostrar a situação

> ⚠️ **REGRA CRÍTICA DE IMPLEMENTAÇÃO — leia antes de escrever qualquer tela**

*(⚠️ **Nunca mostre a situação bruta da opção.** O banco grava um status por opção de creche, e 77,8% das linhas `Cancelado pelo sistema` pertencem a inscrições que **foram atendidas** — é o cancelamento automático das outras opções quando uma é preenchida. Uma família que conseguiu a vaga veria "cancelado" em 4 das suas 5 escolhas.)*

*(⚙️ **Calcule o desfecho da inscrição** — a melhor situação entre todas as opções — e mostre só isso. Ordem de precedência: Confirmado > Ativo > Selecionado da lista > Selecionado > Lista de espera > Cancelado na confirmação > Cancelado > Cancelado pelo sistema.)*

Sete estados possíveis, com a frequência real de 2025:

| Estado da inscrição | 2025 | O que o bot diz |
|---|---:|---|
| Vaga confirmada | 67,7% | C.3a |
| Na lista de espera | 11,2% | C.3b |
| Nenhuma opção seguiu | 9,5% | C.3c |
| Perdeu o prazo de confirmação | 7,7% | C.3d |
| Cancelada | 3,8% | C.3e |
| Selecionada, precisa confirmar | 0,2% | C.3f |
| Inscrição ativa | 0,0% | C.3g |

#### C.3a — Vaga confirmada

> ✅ **A Ana está com vaga confirmada!**
> 🏫 EDI Leila Diniz — Estrada de Curicica, 200
> 📅 Início das aulas: [data]
>
> É só levar a criança no primeiro dia. Se precisar de alguma coisa, me chama.

#### C.3b — Na lista de espera

> ⏳ **A Ana está na lista de espera.**
> Ela está esperando em: EDI Leila Diniz e CM Criança do Futuro.
>
> Isso quer dizer que a inscrição está válida e ela entra assim que abrir vaga. Assim que abrir, eu te aviso por aqui na hora.

**Se houver critério pendente de comprovação:**

> 📌 Uma coisa que ajuda: **falta comprovar o CadÚnico**. Esse critério é o que mais pesa na classificação, e sem o comprovante ele não conta.
> Quer mandar o número do NIS agora?

**[Botões]** `Mandar o NIS` · `Depois`

*(🎯 **É aqui que a consulta deixa de ser passiva.** Quem está na fila e tem critério pendente é exatamente quem perdeu pontuação por não comprovar. Transformar a consulta em cobrança de documento é o maior ganho do fluxo.)*
*(⚠️ **Nunca informe posição na fila nem pontuação.** A classificação é por critério, não por ordem de chegada, e a posição muda conforme outras famílias comprovam. Prometer número é criar expectativa que a SME não pode honrar.)*

#### C.3c — Nenhuma opção seguiu

> A inscrição da Ana **não seguiu no processo deste ano**. Isso costuma acontecer quando os dados não puderam ser confirmados ou quando houve outra inscrição para a mesma criança.
>
> Quem consegue te explicar exatamente o que houve é a CRE da sua região:
> 📍 [endereço da CRE] · 🕐 [horário] · ☎️ 1746

**[Botões]** `Quero fazer nova inscrição` · `Falar com atendente`

*(⚠️ Estado ambíguo no banco. Não invente o motivo — encaminhe.)*

#### C.3d — Perdeu o prazo de confirmação

> A Ana chegou a ser **chamada** para a EDI Leila Diniz, mas o prazo de confirmação venceu em [data] e a vaga foi para outra criança.
>
> Sei que é uma notícia ruim. A inscrição para o próximo processo abre em [data] e eu te aviso quando abrir.

**[Botões]** `Me avise quando abrir` · `Falar com atendente`

*(🎯 São 5.519 famílias em 2025 — 7,7%. Concentradas em Pilares (24,9%), Santa Teresa (23,6%), Gávea (22,9%) e Bangu (471 famílias). **A maior parte dessas famílias nunca soube que foi chamada.** É exatamente o vazamento que o canal existe para fechar: com o WhatsApp cadastrado, o R2 e o R3 chegam antes do prazo vencer.)*

#### C.3e — Cancelada

> A inscrição da Ana consta como **cancelada**.
> Se você não pediu esse cancelamento, vale falar com a CRE: 📍 [endereço] · ☎️ 1746

#### C.3f — Selecionada, precisa confirmar

> 🎉 **A Ana foi selecionada** para a EDI Leila Diniz!
> ⏰ Você precisa confirmar até **[data]** — depois disso a vaga vai para outra criança.

**[Botões]** `Confirmar a vaga` · `Não vou poder`

*(⚠️ Se a inscrição está nesse estado, **este é o primeiro balão da conversa** — antes de qualquer outra coisa. Não deixe para o meio do fluxo.)*

#### C.3g — Inscrição ativa

> A inscrição da Ana está **ativa** e aguardando a classificação, que sai em **[data]**. Eu te aviso aqui no dia.

### C.4 O que dá para fazer a partir daqui

> Posso te ajudar com mais alguma coisa?

**[Botões]** `Mandar documento que falta` · `Atualizar meu telefone` · `Mudei de endereço` · `Inscrever outra criança`

*(💡 **"Atualizar meu telefone" parece pequeno e não é.** O documento de parametrização da SME lista "atualização de contatos" como problema em aberto. Contato desatualizado é uma das causas do 7,7% que perde a vaga já convocado.)*
*(⚠️ Mudança de endereço no meio do processo pode alterar o polo de classificação. Não trate como edição de cadastro — encaminhe para a CRE confirmar o efeito.)*

### C.5 Ativar os avisos

*(🎯 O turno mais valioso do fluxo de consulta.)*

> Quer que eu te avise por aqui quando tiver novidade? Aviso quando sair o resultado, quando abrir vaga e quando faltar documento.

**[Botões]** `Quero ser avisada` · `Não, obrigada`

*(⚙️ Grava `canal_contato` + consentimento `finalidade = comunicacao`. **É assim que o bot alcança quem se inscreveu pelo site** — a família chega por uma consulta e sai com o canal de convocação ativo.)*

### C.6 Se não encontrou

> Não achei nenhuma inscrição com esses dados. Isso pode ser por três motivos:
>
> • Algum dado saiu diferente do que está na certidão — nome abreviado, por exemplo
> • A inscrição foi feita com o nome de outro responsável
> • A inscrição não chegou a ser concluída
>
> Quer tentar de novo, ou prefere fazer uma inscrição nova?

**[Botões]** `Tentar de novo` · `Fazer inscrição nova` · `Falar com atendente`

*(⚙️ Depois de 3 tentativas sem achar, ofereça atendente direto — não deixe a família em loop.)*

---

## Fluxos em que o bot fala primeiro

### R1. Cobrança de documento pendente

> Oi! Faltou um documento na inscrição da Ana: **o laudo da educação especial**.
> Sem ele esse critério não conta na classificação. Pode mandar a foto por aqui? 📎

*(🎯 Ataca direto os 8,0% de validação documental.)*

### R2. Convocação

> 🎉 Boa notícia! Saiu vaga para a **Ana** na **EDI Leila Diniz**, a 400 m da sua casa.
> Você tem até **29/01** para confirmar.

**[Botões]** `Confirmar vaga` · `Não vou poder`

### R3. Lembrete de convocação

*(Se a mensagem R2 não foi lida em 24h: reenvia. Depois escalona para ligação da CRE.)*

*(🎯 Separa "não foi avisada" de "foi avisada e desistiu". Hoje as duas viram `Cancelado na confirmacao` e são tratadas como desistência. Só a primeira é problema que o bot resolve.)*

### R4. Resultado

> Saiu o resultado da inscrição da **Ana**: ela foi **classificada na EDI Leila Diniz**! 🎉
> Agora é confirmar a vaga entre **22 e 29/01**.

---

## Saídas de exceção

**Fora do período de inscrição**
> As inscrições para 2026 foram de **09 a 12/12/2025**. Quer que eu te avise quando abrir o próximo processo?

**Criança fora da faixa etária** — ver bloco 4.

**Três falhas de validação no mesmo campo, ou pedido explícito**
> Vou te passar para um atendente da CRE, que resolve melhor que eu. Já mandei tudo o que a gente preencheu junto.

---

## Observações de design de conversa

- **Uma pergunta por mensagem.** Nunca empilhar duas no mesmo balão. As únicas exceções são os checklists dos blocos 8.3 e 8.4, que são deliberados.
- **Botões sempre que a resposta for fechada.** Texto livre só para nome, CPF, NIS, telefone, e-mail, CEP e número.
- **Eco de confirmação para identidade e contato** — CPF, nome, telefone. **Nunca para resposta sensível.** Ecoar "Recebido: alguém de casa está preso ✅" num histórico que fica no aparelho da família é perigoso.
- **Nada bloqueia a inscrição** exceto o consentimento e a faixa etária. Documento que falta vira pendência com lembrete, não parede.
- **Retomada é requisito.** Conversa de WhatsApp cai. Sessão persistida + chave de idempotência, senão a família recomeça do zero ou entra duplicada.

### O que a IA faz e o que não faz

| Faz | Não faz |
|---|---|
| Interpreta linguagem natural ("nasceu em março do ano passado") | **Calcular pontuação** — é norma (Resolução SME nº 542/2025), roda em SQL determinístico |
| Lê documento por foto (OCR de NIS, laudo, certidão) | Decidir prioridade ou posição na fila |
| Reconcilia nome divergente com a base oficial | Julgar se uma evidência é válida |
| Reformula a pergunta quando a família não entende | Prometer vaga |

### Tradução da situação — o banco não fala com a família

O sistema grava **uma situação por opção de creche**, com oito valores possíveis. A família tem que ver **um** estado, calculado como a melhor situação entre as opções dela. Mostrar o valor bruto quebra a confiança na hora.

| Valor no banco | % das linhas que pertencem a quem **foi atendido** | O que a família vê |
|---|---:|---|
| `Confirmado` | 100% | Vaga confirmada |
| `Ativo` | 100% | Inscrição ativa |
| `Selecionado` / `Selecionado da lista` | 100% | Selecionada — precisa confirmar |
| `Cancelado pelo sistema` | **77,8%** | *(nunca mostrar — é o cancelamento automático das outras opções)* |
| `Cancelado na confirmacao` | **25,5%** | Perdeu o prazo *(só se for o desfecho da inscrição)* |
| `Lista de espera` | 0,5% | Na lista de espera |
| `Cancelado` | 0,4% | Cancelada |

Ordem de precedência para calcular o desfecho: `Confirmado` > `Ativo` > `Selecionado da lista` > `Selecionado` > `Lista de espera` > `Cancelado na confirmacao` > `Cancelado` > `Cancelado pelo sistema`.

*(⚠️ Detalhe que quebra query: o valor gravado é `Cancelado na confirmacao` — **sem cedilha e sem til**. Filtrar pela grafia correta devolve zero linhas.)*

### Campos derivados — nunca perguntados

| Campo | De onde vem |
|---|---|
| Grupamento | Data de nascimento da criança + data de corte do processo |
| Bairro, logradouro, coordenadas | CEP + número |
| Polo / CRE | Catálogo de unidades do matricula.rio |
| Pergunta 11 (fila ano anterior) | Histórico do próprio banco |
| Pergunta 13 (responsável < 18) | Data de nascimento do responsável |
| Distância até cada creche | Endereço × coordenadas das unidades |
| Pontuação | `ic.pergunta_processo` × respostas validadas |