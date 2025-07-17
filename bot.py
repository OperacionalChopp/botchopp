# bot.py (VERSÃO MAIS RECENTE - COM FAQ, BOTÕES E INTRODUÇÃO)

import os
import json
import asyncio
from flask import Flask, request
# Importa os tipos necessários para botões inline
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
# Importa CallbackQueryHandler para lidar com cliques de botão
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

# Variáveis globais para FAQ e Introdução
FAQ_DATA = {}
INTRODUCTION_MESSAGE = ""

# --- Funções de Apoio ---

def load_faq_data():
    """Carrega os dados do FAQ do arquivo faq_data.json."""
    global FAQ_DATA
    try:
        # Certifique-se de que faq_data.json está na mesma pasta do bot.py
        with open('faq_data.json', 'r', encoding='utf-8') as f:
            FAQ_DATA = json.load(f)
        print("FAQ_DATA carregado com sucesso!")
    except FileNotFoundError:
        print("Erro: faq_data.json não encontrado. Certifique-se de que o arquivo está na pasta correta.")
        # Se o FAQ não for encontrado, o bot pode não funcionar como esperado para perguntas
    except json.JSONDecodeError:
        print("Erro: faq_data.json está mal formatado. Verifique a sintaxe JSON.")
        # Se o JSON estiver inválido, o bot também não funcionará corretamente

def load_introduction_message():
    """Carrega a mensagem de introdução do arquivo introducao.txt."""
    global INTRODUCTION_MESSAGE
    try:
        # Certifique-se de que introducao.txt está na mesma pasta do bot.py
        with open('introducao.txt', 'r', encoding='utf-8') as f:
            INTRODUCTION_MESSAGE = f.read()
        print("introducao.txt carregado com sucesso!")
    except FileNotFoundError:
        print("Erro: introducao.txt não encontrado. Usando mensagem de boas-vindas padrão.")
        INTRODUCTION_MESSAGE = "Olá! Eu sou seu bot. Como posso ajudar hoje?"

def get_suggested_questions_keyboard():
    """
    Cria um teclado inline com botões de perguntas sugeridas.
    Você pode personalizar quais FAQs IDs aparecem aqui como sugestões.
    """
    # FAQs IDs para as perguntas que você quer sugerir consistentemente
    # Baseado nas perguntas principais do seu FAQ 1
    suggested_faq_ids = ["5", "3", "6", "54"] # Ex: Onde fica?, Horário, Produtos, Falar com atendente
    
    buttons = []
    for faq_id in suggested_faq_ids:
        if faq_id in FAQ_DATA and "pergunta" in FAQ_DATA[faq_id]:
            question_text = FAQ_DATA[faq_id]["pergunta"]
            # Cada botão terá o texto da pergunta e um callback_data 'faq_ID'
            buttons.append([InlineKeyboardButton(question_text, callback_data=f"faq_{faq_id}")])
    
    return InlineKeyboardMarkup(buttons)

def search_faq(text):
    """
    Busca uma resposta no FAQ com base no texto do usuário.
    Retorna a resposta e o ID do FAQ correspondente (ou padrão).
    """
    text_lower = text.lower()
    # Pega a resposta padrão do ID 54 para quando não houver correspondência
    default_response_54 = FAQ_DATA.get("54", {}).get("resposta", "Desculpe, não consegui encontrar uma resposta para sua pergunta no momento. Por favor, tente reformular ou entre em contato direto.")
    
    for entry_id, entry_data in FAQ_DATA.items():
        if "palavras_chave" in entry_data:
            for keyword in entry_data["palavras_chave"]:
                # Verifica se a palavra-chave está no texto do usuário
                if keyword.lower() in text_lower:
                    return entry_data["resposta"], entry_id # Retorna a resposta e o ID do FAQ
    
    # Se nenhuma correspondência for encontrada, retorna a resposta padrão do ID 54 e seu ID
    return default_response_54, "54"

# --- Handlers do Telegram ---

async def start(update: Update, context):
    """Handler para o comando /start."""
    keyboard = get_suggested_questions_keyboard()
    # Envia a mensagem de introdução carregada do arquivo introducao.txt
    await update.message.reply_text(INTRODUCTION_MESSAGE, reply_markup=keyboard)

async def handle_message(update: Update, context):
    """
    Handler para mensagens de texto comuns.
    Tenta encontrar uma resposta no FAQ e sugere mais perguntas.
    """
    user_text = update.message.text
    if user_text:
        response_text, faq_id = search_faq(user_text)
        keyboard = get_suggested_questions_keyboard()
        # Responde com o texto encontrado e os botões de sugestão
        await update.message.reply_text(response_text, reply_markup=keyboard)

async def button_callback_handler(update: Update, context):
    """
    Handler para cliques em botões inline.
    Responde com a informação do FAQ correspondente ao botão clicado.
    """
    query = update.callback_query
    await query.answer() # Importante para indicar que o clique foi recebido

    callback_data = query.data
    if callback_data.startswith("faq_"):
        faq_id = callback_data.split("_")[1] # Extrai o ID do FAQ do callback_data
        if faq_id in FAQ_DATA:
            response_text = FAQ_DATA[faq_id]["resposta"]
            keyboard = get_suggested_questions_keyboard()
            # Edita a mensagem do bot para mostrar a resposta e novos botões
            # query.edit_message_text é usado para não poluir o chat com novas mensagens
            await query.edit_message_text(text=response_text, reply_markup=keyboard)
        else:
            # Caso o ID do FAQ não seja encontrado (situação improvável se os botões forem gerados corretamente)
            await query.edit_message_text(text="Desculpe, não consegui encontrar esta informação.", reply_markup=get_suggested_questions_keyboard())

# --- Configuração Principal da Aplicação ---

def main():
    """Função principal que configura e retorna a aplicação Flask."""
    # Carregar dados do FAQ e a mensagem de introdução na inicialização
    load_faq_data()
    load_introduction_message()

    TOKEN = os.environ.get('BOT_TOKEN')
    WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
    PORT = int(os.environ.get('PORT', '5000'))

    # Constrói a Application do python-telegram-bot
    application = Application.builder().token(TOKEN).build()

    # Adiciona os handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(CallbackQueryHandler(button_callback_handler)) # Adiciona o handler para botões

    # Correção para o RuntimeWarning/Error de 'Application.initialize'
    # Esta coroutine precisa ser aguardada antes da Application ser usada
    async def initialize_ptb_application():
        await application.initialize()

    # Executa a inicialização assíncrona da Application
    asyncio.run(initialize_ptb_application())

    # Configura a aplicação Flask para lidar com webhooks
    app = Flask(__name__)

    @app.route(f'/{TOKEN}', methods=['POST'])
    async def webhook_handler():
        """Processa as atualizações do Telegram via webhook."""
        json_data = await request.get_json(force=True)
        update = Update.de_json(json_data, application.bot)
        await application.process_update(update) # Processa a atualização com a Application do PTB
        return 'ok'

    return app

# A variável 'app' global é o ponto de entrada para o Gunicorn
app = main()
