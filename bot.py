import os
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

# A URL base do seu serviço no Render
WEBHOOK_URL = "https://botchopp.onrender.com/api/telegram/webhook"

# Cria a aplicação do Telegram
application = (
    ApplicationBuilder( )
    .token(TOKEN)
    .build()
)

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

# ESTA PARTE É CRUCIAL PARA INICIAR O SERVIDOR DO WEBHOOK
if __name__ == '__main__':
    # O Render vai fornecer a porta via variável de ambiente PORT
    port = int(os.environ.get("PORT", 8000)) # Use 8000 como padrão se PORT não estiver definida

    # Inicia o webhook usando o método da Application
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path="/api/telegram/webhook", # O caminho que o Telegram vai chamar
        webhook_url=WEBHOOK_URL # A URL completa do seu webhook
    )
