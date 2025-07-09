from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from base_conhecimento.faq_data import faq_data

async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.lower()

    for item in faq_data:
        for palavra in item["palavras_chave"]:
            if palavra in texto:
                await update.message.reply_text(item["resposta"])
                return

    # fallback se nada bateu
    await update.message.reply_text(
        "Desculpe, não entendi. 🤔\n"
        "Você pode perguntar sobre horário, formas de pagamento, região de atendimento, etc."
    )

async def main():
    # substitua pelo seu token real
    app = ApplicationBuilder().token("7561248614:AAHz-PCTNcgj5oyFei0PgNnmlwvSu4NSqfw").build()

    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), responder))

    print("Bot CHOPP rodando...")
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
