# Configurar o bot no Telegram

10 minutos, sem escrever código. Faça um bot por desenvolvedor: dois processos com o
mesmo token dão `409 Conflict` e um derruba o outro.

## 1. Criar

No [@BotFather](https://t.me/BotFather), `/newbot`. Ele pede o nome (livre, aparece no topo do
chat) e o username (único no Telegram inteiro, e tem que terminar em `bot`), e responde com
o token: `8123456789:AAH...`.

O token é segredo: quem o tem controla o bot. Se vazar, `/revoke`.

## 2. Desligar grupos, antes de qualquer teste

```
/setjoingroups  →  escolha o bot  →  Disable
```

Este bot recebe foto de documento de criança. Num grupo, dado sensível passa a chegar num
contexto com terceiros. O bot é 1:1, e só. `make verificar` imprime
`pode entrar em grupo: False`.

## 3. Vestir o bot

`/mybots` → seu bot → Edit Bot:

- Description (tela vazia, antes do primeiro `/start`):
  > Oi! Eu te ajudo a inscrever seu filho ou filha numa creche perto de casa. A gente faz
  > junto, no seu ritmo, e eu te aviso de cada novidade. 💚
- About (perfil, 120 caracteres):
  > Ajudo famílias a conseguir vaga em creche. Rapidinho e sem burocracia.
- Botpic: imagem quadrada. Reconhecimento visual importa quando a pessoa volta semanas
  depois.
- Commands: cole exatamente:

```
start - Começar ou retomar minha inscrição
status - Ver como está minha inscrição
ajuda - Ver os comandos e o telefone do 1746
apagar - Apagar meus dados
```

O `apagar` não é enfeite: é o direito de eliminação da LGPD, e deixá-lo visível no menu é a
forma honesta de oferecer. Fora do menu ficam `/ia`, `/demo` e `/avancar`. Os três funcionam e
o `/ajuda` os anuncia, mas o menu está em linguagem de família e eles não estão.

## 4. Rodar

```bash
cp .env.example .env       # cole o token em TELEGRAM_TOKEN=
make verificar             # deve imprimir: ✅ token válido: @seu_bot
make eco                   # opcional: /start no celular e o eco responde com 3 botões
make bot                   # precisa também de DATABASE_URL (BANCO.md); make memoria dispensa
```

O eco é diagnóstico: prova que `MensagemSaida` renderiza no Telegram real, com o limite que o
WhatsApp vai impor depois.

## 5. Testar o fluxo

Com `make roteiro` (`BACKEND=mock`): CPF do responsável `529.982.247-25` traz o cadastro do ano
passado; qualquer outro CPF válido segue no preenchimento completo. CEPs que resolvem:
`22710-560`, `22775-003`, `20220-030`, sempre com número. Valem nos dois backends (o
`BackendMapa` herda `resolver_cep` do mock); o que muda é a lista de creches. Depois de
concluir, `/avancar` empurra uma etapa e a notificação chega sozinha. Roteiro completo em
[ROTEIRO.md](ROTEIRO.md).

## Coisas que vão te morder

| Sintoma | Causa | Solução |
|---|---|---|
| `409 Conflict` | Dois processos com o mesmo token | Um bot por dev; feche a instância antiga |
| Bot não responde | Webhook antigo configurado | O script já chama `deleteWebhook` |
| Mensagem não chega ao usuário | Ele nunca deu `/start` | O bot só fala com quem iniciou. No WhatsApp o equivalente é a janela de 24h |
| `401 Unauthorized` | Token errado ou revogado | `/token` no BotFather |
| Texto com `*` ou `_` saindo torto | Alguém pôs `parse_mode` | Texto puro, sempre |
