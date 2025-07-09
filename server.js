const express = require('express');
const { Telegraf } = require('telegraf');

const bot = new Telegraf(process.env.BOT_TOKEN);
const app = express();
app.use(express.json());

// Mensagem padrão no /start
bot.start((ctx) => {
  ctx.reply('Fala, mestre do CHOPP! 🍻 Bem-vindo ao bot CHOPP DIGITAL!');
});

// Exemplo de resposta manual
bot.hears(/promo/i, (ctx) => {
  ctx.reply('Hoje tem chope em dobro das 18h às 20h! 🍺🍺');
});

// Mensagem padrão pra qualquer texto
bot.on('text', (ctx) => {
  ctx.reply('Pergunta aí sobre promoções, horário, chope ou reservas! 😄');
});

// Webhook pro Render
app.post('/webhook', (req, res) => {
  bot.handleUpdate(req.body);
  res.sendStatus(200);
});

// Inicia servidor
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Bot rodando na porta ${PORT}`);
});
