const express = require('express');
const { Telegraf } = require('telegraf');

const bot = new Telegraf(process.env.BOT_TOKEN);
const app = express();

app.use(express.json());

bot.start((ctx) => ctx.reply('Fala, mestre CHOPP! 🍻'));
app.post('/webhook', (req, res) => {
  bot.handleUpdate(req.body);
  res.sendStatus(200);
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Bot rodando na porta ${PORT}`);
});
