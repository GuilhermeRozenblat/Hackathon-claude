# Configurar o bot no Telegram

10 minutos, sem escrever código. Faça **um bot por desenvolvedor** — dois processos
fazendo polling com o mesmo token dão `409 Conflict` e um derruba o outro.

## 1. Criar o bot

No Telegram, abra [@BotFather](https://t.me/BotFather) e mande `/newbot`.

Ele pede duas coisas:

| | Exemplo | Regra |
|---|---|---|
| Nome | `Creche Amiga` | Livre, é o que aparece no topo do chat. Pode mudar depois |
| Username | `creche_amiga_dev_gui_bot` | Único no Telegram inteiro e **tem que terminar em `bot`** |

Ele responde com o token: `8123456789:AAH...`. **É segredo** — quem tem o token controla
o bot. Se vazar, `/revoke` no BotFather gera outro.

## 2. Desligar grupos — faça isso antes de qualquer teste

```
/setjoingroups  ->  escolha o bot  ->  Disable
```

Este bot recebe foto de documento de criança. Se alguém adicionar ele a um grupo, mensagens
com dado sensível passam a chegar num contexto com terceiros. Não é paranoia, é o desenho
certo: o bot é 1:1 e só isso.

Confirme depois com o script — ele imprime `pode entrar em grupo: False`.

## 3. Vestir o bot

Ainda no BotFather, `/mybots` → seu bot → **Edit Bot**:

- **Edit Description** — aparece na tela vazia, antes do primeiro `/start`:
  > Oi! Eu te ajudo a inscrever seu filho ou filha numa creche perto de casa. A gente faz
  > junto, no seu ritmo, e eu te aviso de cada novidade. 💚
- **Edit About** — aparece no perfil, 120 caracteres:
  > Ajudo famílias a conseguir vaga em creche. Rapidinho e sem burocracia.
- **Edit Botpic** — uma imagem quadrada. Reconhecimento visual importa quando a pessoa
  volta ao chat semanas depois.
- **Edit Commands** — cole exatamente:

```
start - Começar ou retomar minha inscrição
status - Ver como está minha inscrição
ajuda - Falar com uma pessoa
apagar - Apagar meus dados
```

`apagar` não é enfeite: é o direito de eliminação da LGPD, e deixá-lo visível no menu é a
forma honesta de oferecer. Ele chama `repositorio.apagar_tudo()`.

## 4. Token no `.env`

```bash
cp .env.example .env
```

Cole o token em `TELEGRAM_TOKEN=`. O `.env` já está no `.gitignore` — **nunca commite**.

## 5. Verificar

```bash
python scripts/verificar_telegram.py
```

Deve imprimir `✅ token válido — @seu_bot`. Para testar no celular:

```bash
python scripts/verificar_telegram.py --eco
```

Abra `t.me/seu_bot`, mande `/start` e uma foto. O eco responde e mostra 3 botões — que é a
prova de que o contrato `MensagemSaida` renderiza no Telegram real, com o limite que o
WhatsApp vai impor depois.

`Ctrl+C` para parar. Este script é só diagnóstico — o `creche_bot/canal/telegram.py` de
verdade já existe e é o que `make bot` usa.

## Coisas que vão te morder

| Sintoma | Causa | Solução |
|---|---|---|
| `409 Conflict` | Dois processos com o mesmo token | Um bot por dev, e feche a instância antiga |
| Bot não responde | Webhook antigo configurado | O script já chama `deleteWebhook` |
| Mensagem não chega ao usuário | Ele nunca deu `/start` | O bot **só** fala com quem iniciou. No WhatsApp o equivalente é a janela de 24h |
| `401 Unauthorized` | Token errado ou revogado | `/token` no BotFather |
| Texto com `*` ou `_` saindo torto | Alguém pôs `parse_mode` | Texto puro, sempre. Os dialetos de Telegram e WhatsApp divergem |

## Depois

```bash
make bot
```

O roteiro completo já está implementado. Para testar os dois caminhos do Bloco 1:

| Caminho | CPF | Nascimento |
|---|---|---|
| Cadastro **encontrado** no data lake | `111.222.333-44` | `18/03/2024` |
| Cadastro **não encontrado** | qualquer outro | qualquer |

Depois de concluir a inscrição, `/avancar` empurra uma etapa e a notificação chega
sozinha. Roteiro completo em [ROTEIRO.md](ROTEIRO.md).
