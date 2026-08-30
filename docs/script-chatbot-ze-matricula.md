# Script do Chatbot "Zé Matrícula" — Fluxo de Cadastro

Linguagem pensada para WhatsApp: mensagens curtas, uma pergunta por vez, botões quando possível em vez de texto livre.

---

## 0. Boas-vindas

> 👋 Oi! Eu sou o **Zé Matrícula**, assistente virtual da Matrícula Rio.
> Vou te ajudar a inscrever seu filho(a) na rede municipal. Leva poucos minutos!

**[Botões]** `Vamos começar` · `Já tenho uma inscrição em andamento`

---

## 1. Pesquisa inicial

> Antes de começar, deixa eu ver se você já tem um cadastro com a gente.
> Qual é o **CPF** do candidato (da criança/aluno)?

*(usuário envia CPF)*

> Perfeito! E a **data de nascimento** dele(a)? (dia/mês/ano)

*(usuário envia data)*

*→ Sistema consulta o data lake*

### Se encontrou cadastro (SIM):
> 🎉 Boa notícia! Já encontrei um cadastro com esse CPF.
> Vou te mostrar as informações que já temos, para você só confirmar ou corrigir.

*(pula direto para o Bloco 5 — Resumo/Edição)*

### Se não encontrou (NÃO):
> Não encontrei nada ainda, sem problemas! Vamos preencher juntos — é rápido. 🙂

*(segue para o Bloco 2)*

---

## 2. Sobre a vaga

> O candidato já estuda em alguma escola?

**[Botões]** `Já estuda na rede municipal` · `Estuda em escola particular` · `Nunca estudou` · `Estuda em outra rede/cidade`

**Se "Já estuda na rede municipal":**
> Você tem o **número de matrícula** dele(a) em mãos?

**[Botão extra]** `Não sei / não tenho agora`

> Última pergunta desse bloco: o candidato possui **deficiência, transtorno global do desenvolvimento (TGD/TEA) ou altas habilidades/superdotação**?

**[Botões]** `Sim` · `Não`

**Se "Sim":**
> Qual dessas opções descreve melhor a situação dele(a)?

**[Botões]** `Deficiência física` · `Deficiência intelectual` · `TGD/TEA` · `Altas habilidades/superdotação` · `Outra`

---

## 3. Dados pessoais

> Qual é o **nome completo** do candidato?

*(usuário responde)*

> A filiação (nome da mãe e/ou pai) consta na **certidão de nascimento** dele(a)?

**[Botões]** `Sim` · `Não`

> Pode me passar o **nome completo da mãe e/ou pai**, como consta na certidão?
> *(se "Não" na pergunta anterior: "Pode me passar o nome do responsável legal pela criança?")*

*(usuário responde)*

> E qual é o **nome do responsável** que vai acompanhar essa matrícula?

*(usuário responde)*

> Qual é a **data de nascimento do responsável**? (dia/mês/ano)

*(usuário responde)*
*(⚙️ o bot calcula a idade automaticamente e já marca os critérios de prioridade — "60 anos ou mais" e "mãe adolescente, menor de 18 anos" — sem precisar perguntar isso diretamente ao usuário)*

> O candidato tem pais ou responsáveis com alguma **deficiência**?

**[Botões]** `Sim` · `Não`

---

## 4. Contato

> Show! Agora preciso do **celular do responsável**, para mantermos contato sobre a inscrição.

*(usuário responde)*

> Tem algum **outro contato de celular** (segunda pessoa) para casos de emergência ou caso não conseguirmos falar com o responsável principal?

**[Botões]** `Sim, tenho outro contato` · `Não tenho outro contato`

**Se "Sim":**
> Pode me passar esse outro número, por favor?

> O responsável tem **e-mail**?

**[Botões]** `Sim` · `Não`

**Se "Sim":**
> Pode me passar o e-mail, por favor?

---

## 5. Resumo e confirmação dos dados

> Aqui está o resumo do que já tenho:
> *(bot exibe: origem, matrícula, necessidades especiais, nome, filiação, responsável, data de nascimento do responsável, deficiência dos pais/responsáveis, celular, outro contato, e-mail)*
>
> Está tudo certo?

**[Botões]** `Está tudo certo` · `Quero corrigir algo`

*(se "corrigir", bot pergunta qual campo e volta para aquele bloco específico)*

---

## 6. Busca das escolas

> Última etapa antes de escolher a escola! Qual é o **CEP ou bairro** onde vocês moram?

*(usuário responde)*

> Encontrei essas creches/escolas mais próximas de você:
>
> 🏫 **[Nome da escola 1]** — Nota de corte: X pontos
> 🏫 **[Nome da escola 2]** — Nota de corte: Y pontos
> 🏫 **[Nome da escola 3]** — Nota de corte: Z pontos
>
> *A nota de corte te ajuda a entender a chance de vaga em cada uma.*
> Quais você quer escolher? (pode marcar mais de uma, em ordem de preferência)

**[Seleção múltipla/ordenável]**

---

## 7. Confirmação final da escolha

> Aqui está sua lista final de escolas escolhidas, em ordem de preferência:
> 1️⃣ [Escola A]
> 2️⃣ [Escola B]
> 3️⃣ [Escola C]
>
> Posso confirmar essa escolha?

**[Botões]** `Confirmar` · `Quero alterar a ordem/escolas`

---

## 8. Envio da documentação

> Ótimo, inscrição quase pronta! Como você prefere enviar os documentos?

**[Botões]** `Enviar aqui pelo WhatsApp` · `Levar até a creche escolhida` · `Levar a um CRAS`

### 8a. Enviar pelo WhatsApp
> Perfeito! Pode me mandar os documentos aqui mesmo, um de cada vez 📎
> *(lista de documentos necessários é exibida antes)*

*(usuário envia os arquivos)*

> Recebido! ✅
> Seu número de protocolo é **[Ticket]**.
> Você pode acompanhar tudo por aqui: **[link]**
> Também vou te avisar automaticamente a cada atualização!

### 8b. Levar até a creche escolhida
> Sem problemas! Aqui está o que você precisa levar:
> 📄 Lista de documentos: [lista]
> 📍 Endereço da escola: [endereço]
> 🕐 Horário de atendimento: [horário]
>
> Seu número de protocolo já está gerado: **[Ticket]**
> Acompanhe por aqui: **[link]**

### 8c. Levar a um CRAS
> Combinado! Aqui está o que você precisa:
> 📄 Lista de documentos: [lista]
> 📍 CRAS mais próximos: [lista de CRAS + endereços]
> 🕐 Horário de atendimento: [horário]
>
> ⚠️ *(ponto de atenção do fluxo original: aqui é necessário notificar o usuário quando o CRAS enviar/receber os documentos e repassar para a creche — hoje esse retorno não existe)*
>
> Assim que tivermos essa confirmação, vou te avisar por aqui automaticamente ✅
> Seu número de protocolo: **[Ticket]**
> Acompanhe por aqui: **[link]**

---

## Observações de design de conversa

- **Uma pergunta por mensagem** — nunca empilhar 2+ perguntas no mesmo balão.
- **Botões sempre que a resposta for fechada** (Sim/Não, escolha entre opções) — texto livre só para nome, CPF, telefone, e-mail, endereço.
- **Confirmação de leitura**: depois de cada resposta importante (CPF, nome, e-mail), o bot pode ecoar de volta ("Recebido: Fulano da Silva ✅") para reduzir erro de digitação.
- **Ponto de atenção do CRAS**: o fluxograma original não define como o usuário é avisado quando os documentos saem do CRAS/Poupa Tempo e chegam à creche — vale fechar esse retorno para não deixar o usuário no escuro depois de entregar os documentos.
