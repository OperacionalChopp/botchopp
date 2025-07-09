from flask import Flask, request
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters
from base_conhecimento.faq_data import faq_data

# 1) Configure seu bot
TOKEN = "SEU_TOKEN_AQUI"

# 2) Crie a aplicação Telegram
application = Application.builder().token(7561248614:AAHz-PCTNcgj5oyFei0PgNnmlwvSu4NSqfw).build()

# 3) Adicione o handler de mensagens
async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.lower()

    for item in faq_data:
        for palavra in item["palavras_chave"]:
            if palavra in texto:
                await update.message.reply_text(item["resposta"])
                return

    await update.message.reply_text(
        "Desculpe, não entendi. 🤔\n"
        "Você pode perguntar sobre horário, formas de pagamento, região de atendimento, etc."
    )

application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), responder))

# 4) Crie o Flask para expor o webhook
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
async def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), application.bot)
        await application.process_update(update)
    return "ok", 200

# 5) Use gunicorn para rodar: gunicorn bot:app

