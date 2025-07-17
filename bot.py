# bot.py (VERSÃO FINAL COM NÚMERO DE CONTATO ATUALIZADO E INTEGRAÇÃO FAQ)

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
    # Adicionar um fallback ou tratamento de erro adequado
except json.JSONDecodeError:
    print("ERRO: faq_data.json com formato JSON inválido.")
    # Adicionar um fallback ou tratamento de erro adequado

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
    """Processa mensagens de texto (não comandos) e tenta encontrar respostas no FAQ."""
    user_text = update.message.text.lower()
    response_text = "Desculpe, não entendi sua pergunta. Por favor, tente reformular ou use os botões abaixo para explorar as opções."
    reply_markup = None

    for faq_id, entry in FAQ_DATA.items():
        if faq_id == "1": # Pula a FAQ de boas-vindas para não ser acionada por texto
            continue
        
        found_keywords = [
            kw for kw in entry.get("palavras_chave", []) if kw.lower() in user_text
        ]
        
        if found_keywords:
            response_text = entry["resposta"]
            
            # Se a resposta for o FAQ de "Falar com alguém" (ID 4), adiciona botões específicos
            if faq_id == "4":
                reply_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📞 Ligar para a Loja", url="tel:+556139717502")], # NÚMERO ATUALIZADO AQUI
                    [InlineKeyboardButton("💬 Abrir Chat", url="https://wa.me/556139717502")] # NÚMERO ATUALIZADO AQUI
                ])
            break # Parar após encontrar a primeira palavra-chave correspondente

    await update.message.reply_text(response_text, reply_markup=reply_markup)

async def handle_callback_query(update: Update, context):
    """Processa cliques nos botões inline."""
    query = update.callback_query
    await query.answer() # Notifica o Telegram que a query foi recebida

    callback_data = query.data
    response_text = "Opção não reconhecida ou em desenvolvimento."
    reply_markup = None

    if callback_data == "onde_fica":
        location_entry = None
        for faq_id, entry in FAQ_DATA.items():
            if "onde fica" in entry["pergunta"].lower() or "localização" in entry["pergunta"].lower():
                location_entry = entry
                break
        if location_entry:
            response_text = location_entry["resposta"]
        else:
            response_text = "Informação de localização não encontrada no FAQ. Por favor, verifique o arquivo FAQ."
    
    elif callback_data == "horario":
        hours_entry = None
        for faq_id, entry in FAQ_DATA.items():
            if "horário" in entry["pergunta"].lower() or "abre" in entry["pergunta"].lower():
                hours_entry = entry
                break
        if hours_entry:
            response_text = hours_entry["resposta"]
        else:
            response_text = "Informação de horário não encontrada no FAQ. Por favor, verifique o arquivo FAQ."

    elif callback_data == "cardapio":
        menu_entry = None
        for faq_id, entry in FAQ_DATA.items():
            if "cardápio" in entry["pergunta"].lower() or "menu" in entry["pergunta"].lower():
                menu_entry = entry
                break
        if menu_entry:
            response_text = menu_entry["resposta"]
        else:
            response_text = "Informação de cardápio não encontrada no FAQ. Por favor, verifique o arquivo FAQ."

    elif callback_data == "duvida_ia":
        response_text = "Estou pronto para tirar suas dúvidas! Digite sua pergunta agora e tentarei responder com base nas minhas informações. Se precisar de algo que não sei, use a opção 'Falar com alguém'."
    
    elif callback_data == "falar_com_alguem":
        contact_entry = FAQ_DATA.get("4") # Assumindo que FAQ_ID "4" é para Falar com Alguém
        if contact_entry:
            response_text = contact_entry["resposta"]
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("📞 Ligar para a Loja", url="tel:+556139717502")], # NÚMERO ATUALIZADO AQUI
                [InlineKeyboardButton("💬 Abrir Chat", url="https://wa.me/556139717502")] # NÚMERO ATUALIZADO AQUI
            ])
        else:
            response_text = "Opção de contato 'Falar com alguém' não encontrada no FAQ. Por favor, verifique o arquivo FAQ."
    
    await query.edit_message_text(text=response_text, reply_markup=reply_markup)

# Função principal que retorna a aplicação Flask para o Gunicorn
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

# Para gunicorn rodar o Flask, ele precisa de uma variável 'app' global
app = main()
