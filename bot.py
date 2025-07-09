# bot.py

from flask import Flask, request
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters
from base_conhecimento.faq_data import faq_data

TOKEN = "7561248614:AAHz-PCTNcgj5oyFei0PgNnmlwvSu4NSqfw"  # 👉 Coloque o token real aqui

# Instancia o bot
application = Application.builder().token(TOKEN).build()

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

appl
