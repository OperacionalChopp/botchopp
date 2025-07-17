# bot.py (VERSÃO CORRIGIDA - PARA python-telegram-bot 20.0+ E INTEGRAÇÃO FAQ)

import os
import json # Importar para ler o JSON
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup # Importações atualizadas para botões
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# --- Carregar dados do FAQ ---
# Aconselhável carregar os dados uma vez ao iniciar a aplicação
# E torná-los acessíveis aos handlers.
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

        # Criar os botões conforme as sugestões na mensagem de boas-vindas
        # e adicionando a opção de "Falar com alguém" da FAQ ID 4.
        # Os callback_data são chaves para identificar qual botão foi clicado.
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
        # Mensagem de fallback se a FAQ de boas-vindas não for encontrada
        await update.message.reply_text('Olá! Eu sou seu bot! Parece que a mensagem de boas-vindas não foi carregada corretamente. Por favor, verifique o arquivo FAQ.')

async def handle_message(update: Update, context):
    """Processa mensagens de texto (não comandos) e tenta encontrar respostas no FAQ."""
    user_text = update.message.text.lower()
    response_text = "Desculpe, não entendi sua pergunta. Por favor, tente reformular ou use os botões abaixo para explorar as opções."
    reply_markup = None # Inicializa o markup como None

    # Tenta encontrar uma resposta baseada nas palavras-chave do FAQ
    for faq_id, entry in FAQ_DATA.items():
        # Ignora a FAQ de boas-vindas (ID 1) para busca de palavras-chave, pois ela é para o comando /start
        if faq_id == "1":
            continue
        
        # Verifica se alguma palavra-chave da FAQ está contida na mensagem do usuário
        # Convertemos todas as palavras-chave para minúsculas para comparação
        found_keywords = [
            kw for kw in entry.get("palavras_chave", []) if kw.lower() in user_text
        ]
        
        if found_keywords:
            response_text = entry["resposta"]
            
            # Se a resposta for o FAQ de "Falar com alguém" (ID 4), adiciona botões específicos
            if faq_id == "4":
                reply_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📞 Ligar para a Loja", url="tel:+5511987654321")], # SUBSTITUA PELO NÚMERO DE TELEFONE REAL DA LOJA
                    [InlineKeyboardButton("💬 Abrir Chat", url="https://wa.me/5511987654321")] # SUBSTITUA PELO NÚMERO DE WHATSAPP REAL DA LOJA
                ])
            break # Encontrou uma resposta, sai do loop de busca

    await update.message.reply_text(response_text, reply_markup=reply_markup)

async def handle_callback_query(update: Update, context):
    """Processa cliques nos botões inline (InlineKeyboardButtons)."""
    query = update.callback_query
    await query.answer() # Responde ao callback para que o Telegram saiba que o clique foi processado

    callback_data = query.data
    response_text = "Opção não reconhecida ou em desenvolvimento."
    reply_markup = None

    # Lógica para cada callback_data dos botões do start
    if callback_data == "onde_fica":
        # Busca no FAQ a pergunta que corresponde à localização
        location_entry = None
        for faq_id, entry in FAQ_DATA.items():
            # Critério de busca: pergunta que contenha "onde fica" ou "localização"
            if "onde fica" in entry["pergunta"].lower() or "localização" in entry["pergunta"].lower():
                location_entry = entry
                break
        if location_entry:
            response_text = location_entry["resposta"]
        else:
            response_text = "Informação de localização não encontrada no FAQ. Por favor, verifique o arquivo FAQ."
    
    elif callback_data == "horario":
        # Busca no FAQ a pergunta que corresponde ao horário
        hours_entry = None
        for faq_id, entry in FAQ_DATA.items():
            # Critério de busca: pergunta que contenha "horário" ou "abre"
            if "horário" in entry["pergunta"].lower() or "abre" in entry["pergunta"].lower():
                hours_entry = entry
                break
        if hours_entry:
            response_text = hours_entry["resposta"]
        else:
            response_text = "Informação de horário não encontrada no FAQ. Por favor, verifique o arquivo FAQ."

    elif callback_data == "cardapio":
        # Busca no FAQ a pergunta que corresponde ao cardápio
        menu_entry = None
        for faq_id, entry in FAQ_DATA.items():
            # Critério de busca: pergunta que contenha "cardápio" ou "menu"
            if "cardápio" in entry["pergunta"].lower() or "menu" in entry["pergunta"].lower():
                menu_entry = entry
                break
        if menu_entry:
            response_text = menu_entry["resposta"]
        else:
            response_text = "Informação de cardápio não encontrada no FAQ. Por favor, verifique o arquivo FAQ."

    elif callback_data == "duvida_ia":
        response_text = "Estou pronto para tirar suas dúvidas! Digite sua pergunta agora e tentarei responder com base nas minhas informações. Se precisar de algo que não sei, use a opção 'Falar com alguém'."
        # Futuramente, esta parte poderia ser integrada com uma API de IA generativa (ex: Google Gemini, OpenAI GPT)
    
    elif callback_data == "falar_com_alguem":
        # Usa o FAQ ID 4 para a resposta e os botões específicos de contato
        contact_entry = FAQ_DATA.get("4")
        if contact_entry:
            response_text = contact_entry["resposta"]
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("📞 Ligar para a Loja", url="tel:+5511987654321")], # SUBSTITUA PELO NÚMERO DE TELEFONE REAL DA LOJA
                [InlineKeyboardButton("💬 Abrir Chat", url="https://wa.me/5511987654321")] # SUBSTITUA PELO NÚMERO DE WHATSAPP REAL DA LOJA
            ])
        else:
            response_text = "Opção de contato 'Falar com alguém' não encontrada no FAQ. Por favor, verifique o arquivo FAQ."
    
    # Envia a resposta de volta ao usuário, editando a mensagem original do botão
    await query.edit_message_text(text=response_text, reply_markup=reply_markup)


# Sua função principal do bot que retorna a aplicação Flask
def main():
    TOKEN = os.environ.get('BOT_TOKEN')
    WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
    PORT = int(os.environ.get('PORT', '5000')) # Definindo a porta

    # 1. Cria a Application
    application = Application.builder().token(TOKEN).build()

    # 2. Adiciona os handlers à Application
    application.add_handler(CommandHandler("start", start))
    # Handler para mensagens de texto que não são comandos
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    # Handler para cliques em botões inline
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    # 3. Configura o webhook do Flask
    app = Flask(__name__)

    @app.route(f'/{TOKEN}', methods=['POST'])
    async def webhook_handler():
        """Processa as atualizações do Telegram via webhook."""
        # A atualização vem como JSON do Telegram
        json_data = await request.get_json(force=True)
        update = Update.de_json(json_data, application.bot)

        # Processa a atualização com a Application
        await application.process_update(update)
        return 'ok'

    return app

# Para gunicorn rodar o Flask, ele precisa de uma variável 'app' global
# Então, chamamos a função principal para obter a instância da aplicação Flask
app = main()
