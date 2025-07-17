# bot.py (VERSÃO CORRIGIDA COM PARÊNTESE QUE FALTAVA)

import os
import json
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# --- Carregar dados do FAQ ---
FAQ_DATA = {}
try:
    with open('faq_data.json', 'r', encoding='utf-8') as f:
        FAQ_DATA = json.load(f)
except FileNotFoundError:
    print("ERRO: faq_data.json não encontrado. Certifique-se de que o arquivo está na raiz do projeto.")
except json.JSONDecodeError:
    print("ERRO: faq_data.json com formato JSON inválido.")

# --- Seus handlers (comandos e mensagens) ---

async def start(update: Update, context):
    """Envia a mensagem de boas-vindas com botões."""
    welcome_entry = FAQ_DATA.get("1")
    if welcome_entry:
        introduction_message = welcome_entry["resposta"]

        keyboard = [
            [InlineKeyboardButton("📍 Onde fica a loja?", callback_data="onde_fica")],
            [InlineKeyboardButton("🕒 Qual nosso horário?", callback_data="horario")],
            [InlineKeyboardButton("🍔 Quero ver o cardápio", callback_data="cardapio")],
            [InlineKeyboardButton("🧠 Tirar uma dúvida com a IA", callback_data="duvida_ia")],
            [InlineKeyboardButton("📞 Falar com alguém", callback_data="falar_com_alguem")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(introduction_message, reply_markup=reply_markup)
    else:
        await update.message.reply_text('Olá! Eu sou seu bot! Parece que a mensagem de boas-vindas não foi carregada corretamente. Por favor, verifique o arquivo FAQ.')

async def handle_message(update: Update, context):
    """
    Processa mensagens de texto (não comandos) e tenta encontrar respostas no FAQ.
    Se encontrar palavras-chave relevantes, pode apresentar botões de perguntas relacionadas.
    """
    user_text = update.message.text.lower()
    response_text = "Desculpe, não consegui encontrar uma resposta para sua pergunta no momento. Por favor, tente reformular ou use os botões abaixo para explorar as opções."
    reply_markup = None
    
    related_faq_buttons = []
    
    found_exact_match = False 

    for faq_id, entry in FAQ_DATA.items():
        if faq_id == "1": 
            continue
        
        entry_keywords = [kw.lower() for kw in entry.get("palavras_chave", [])]

        matches = [kw for kw in entry_keywords if kw in user_text]
        
        if matches:
            if faq_id == "6": 
                response_text = entry["resposta"]
                reply_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📞 Ligar para a Loja", url="tel:+556139717502")],
                    [InlineKeyboardButton("💬 Abrir Chat", url="https://wa.me/556139717502")]
                ])
                found_exact_match = True 
                break 
            
            if user_text in entry_keywords or any(user_text == kw for kw in entry_keywords): 
                response_text = entry["resposta"]
                found_exact_match = True
                break 
            
            if not found_exact_match:
                related_faq_buttons.append([InlineKeyboardButton(entry["pergunta"], callback_data=faq_id)])

    if found_exact_match:
        await update.message.reply_text(response_text, reply_markup=reply_markup)
    elif related_faq_buttons:
        await update.message.reply_text(
            "Encontrei algumas informações que podem ser úteis. Qual delas você gostaria de saber?",
            reply_markup=InlineKeyboardMarkup(related_faq_buttons)
        )
    else:
        await update.message.reply_text(response_text, reply_markup=reply_markup)

async def handle_callback_query(update: Update, context):
    query = update.callback_query
    await query.answer()

    callback_data = query.data 
    
    response_text = "Desculpe, não consegui encontrar uma resposta para esta opção."
    reply_markup = None

    if callback_data == "onde_fica":
        entry = FAQ_DATA.get("4") 
        if entry:
            response_text = entry["resposta"]
    elif callback_data == "horario":
        entry = FAQ_DATA.get("3") 
        if entry:
            response_text = entry["resposta"]
    elif callback_data == "cardapio":
        entry = FAQ_DATA.get("5") 
        if entry:
            response_text = entry["resposta"]
    elif callback_data == "duvida_ia":
        response_text = "Para tirar dúvidas mais complexas, por favor, me diga sua pergunta e tentarei ajudar."
    elif callback_data == "falar_com_alguem":
        entry = FAQ_DATA.get("6") 
        if entry:
            response_text = entry["resposta"]
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("📞 Ligar para a Loja", url="tel:+556139717502")],
                [InlineKeyboardButton("💬 Abrir Chat", url="https://wa.me/556139717502")]
            ])
    else:
        entry = FAQ_DATA.get(callback_data) 
        if entry:
            response_text = entry["resposta"]
            if callback_data == "6": 
                reply_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📞 Ligar para a Loja", url="tel:+556139717502")],
                    [InlineKeyboardButton("💬 Abrir Chat", url="https://wa.me/556139717502")]
                ])

    # A linha abaixo foi corrigida com o parêntese final
    await query.edit_message_text(text=response_text, reply_markup=reply_markup)

def main():
    TOKEN = os.environ.get('BOT_TOKEN')
    WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
    PORT = int(os.environ.get('PORT', '5000'))

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    app = Flask(__name__)

    @app.route(f'/{TOKEN}', methods=['POST'])
    async def webhook_handler():
        json_data = await request.get_json(force=True)
        update = Update.de_json(json_data, application.bot)
        await application.process_update(update)
        return 'ok'

    return app
