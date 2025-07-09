import os
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters
)
from base_conhecimento.faq_data import faq_data

# ✅ Substitua pelo seu token real!
TOKEN = "7561248614:AAHz-PCTNcgj5oyFei0PgNnmlwvSu4NSqfw"

# Cria o Flask app
flask_app = Flask(__name__)

# Cria a aplicação do Telegram
application = ApplicationBuilder().token(TOKEN).build()

# Handler de mensagens
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

# Adiciona handler de texto
application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), responder))

# ✅ Rota do webhook que o Telegram vai chamar
@flask_app.route('/webhook', methods=['POST'])
async def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return "ok"

# ✅ Rota de teste opcional
@flask_app.route('/', methods=['GET'])
def home():
    return "Bot CHOPP rodando com webhook! ✅"

