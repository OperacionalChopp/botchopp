const express = require('express');
const { Telegraf } = require('telegraf');
const fs = require('fs');

// 🔐 Token do bot (via variável de ambiente)
const bot = new Telegraf(process.env.BOT_TOKEN);

// 📦 Carrega as perguntas do arquivo JSON
const faq = JSON.parse(fs.readFileSync('./faq.json', 'utf8'));

const app = express();
app.use(express.json());

// ✅ Mensagem de boas-vindas no /start
bot.start((ctx) => {
  ctx.replyWithMarkdown(`🍻 *Fala, mestre ${ctx.from.first_name || 'CHOPPzeiro'}!*

Seja muito bem-vindo ao *CHOPP DIGITAL*! Pergunte à vontade ou digite */menu* para ver as opções disponíveis.

Exemplos:
• como pedir chopp
• formas de pagamento
• promoções
• validade do barril
`);
});

// 👋 Detecta saudações tipo “oi”, “olá”, etc.
bot.hears(/^(oi|olá|ola|e aí|eai|opa|salve|bom dia|boa tarde|boa noite)/i, (ctx) => {
  ctx.replyWithMarkdown(`🍺 *Fala, mestre ${ctx.from.first_name || 'CHOPPzeiro'}!*

Manda sua dúvida aí — posso ajudar com:
• como pedir o Chopp Brahma Express
• prazo de validade
• promoções
• formas de pagamento

Ou digita */menu* pra ver o que temos no barril! 😄`);
});

// 🧠 Inteligência simples: busca por palavra-chave no FAQ
bot.on('text', (ctx) => {
  const texto = ctx.message.text.toLowerCase();

  const item = faq.find(f =>
    f.palavrasChave.some(palavra =>
      texto.includes(palavra.toLowerCase())
    )
  );

  if (item) {
    const resposta = item.resposta.replace(/

\[LINK:(.*?)\|(.*?)\]

/g, '🔗 $2 → $1');
    ctx.reply(resposta);
  } else {
    ctx.reply('Ainda não sei essa… mas tô aprendendo com o mestre CHOPP 🍺');
  }
});

// 🔗 Webhook do Render
app.post('/webhook', (req, res) => {
  bot.handleUpdate(req.body);
  res.sendStatus(200);
});

// 🚀 Inicia o servidor
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Bot rodando na porta ${PORT}`);
});

