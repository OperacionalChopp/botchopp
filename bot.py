# bot.py (VERSÃO MAIS RECENTE - COM FAQ INTEGRADO)

import os
import json # Importar o módulo json para ler o FAQ
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import asyncio

# Carregar o arquivo FAQ uma vez na inicialização
FAQ_DATA = {}
try:
    # Ajuste o caminho conforme onde seu arquivo faq_data.json está.
    # Se estiver na mesma pasta do bot.py, apenas 'faq_data.json' é suficiente.
    with open('faq_data.json', 'r', encoding='utf-8') as f:
        FAQ_DATA = json.load(f)
    print("FAQ_DATA carregado com sucesso!")
except FileNotFoundError:
    print("Erro: faq_data.json não encontrado. Certifique-se de que o arquivo está na pasta correta.")
except json.JSONDecodeError:
    print("Erro: faq_data.json está mal formatado. Verifique a sintaxe JSON.")

# Função para buscar resposta no FAQ
def search_faq(text):
    text_lower = text.lower()
    best_match_response = None
    # Definindo a resposta padrão do ID 54 para quando não houver correspondência
    default_response_54 = FAQ_DATA.get("54", {}).get("resposta", "Desculpe, não consegui encontrar uma resposta para sua pergunta no momento. Por favor, tente reformular ou entre em contato direto.")

    for entry_id, entry_data in FAQ_DATA.items():
        if "palavras_chave" in entry_data:
            for keyword in entry_data["palavras_chave"]:
                if keyword.lower() in text_lower:
                    return entry_data["resposta"] # Retorna a primeira correspondência encontrada
    
    # Se nenhuma correspondência for encontrada, retorna a resposta padrão do ID 54
    return default_response_54


# Seus handlers (comandos e mensagens)
async def start(update: Update, context):
    # Pode usar o FAQ 1 para a mensagem de boas-vindas do /start
    welcome_message = FAQ_DATA.get("1", {}).get("resposta", "Olá! Eu sou seu bot! Digite algo para começar.")
    await update.message.reply_text(welcome_message)

async def handle_message(update: Update, context):
    """Processa mensagens de texto e tenta responder usando o FAQ."""
    user_text = update.message.text
    if user_text:
        response = search_faq(user_text)
        await update.message.reply_text(response)


# Sua função principal do bot que retorna a aplicação Flask
def main():
    TOKEN = os.environ.get('BOT_TOKEN')
    WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
    # PORT é opcional se o Render fornecer dinamicamente, mas é bom ter um fallback
    PORT = int(os.environ.get('PORT', '5000')) 

    # 1. Cria a Application
    application = Application.builder().token(TOKEN).build()

    # 2. Adiciona os handlers à Application
    application.add_handler(CommandHandler("start", start))
    # Altera o MessageHandler para usar a nova função handle_message
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    # Correção do RuntimeWarning: Await application.initialize() dentro de um contexto assíncrono
    async def initialize_ptb_application():
        await application.initialize()

    # Executa a inicialização assíncrona
    asyncio.run(initialize_ptb_application())

    # 3. Configura o webhook
    app = Flask(__name__)

    @app.route(f'/{TOKEN}', methods=['POST'])
    async def webhook_handler():
        """Processa as atualizações do Telegram via webhook."""
        json_data = await request.get_json(force=True)
        update = Update.de_json(json_data, application.bot)

        # Processa a atualização com a Application
        await application.process_update(update)
        return 'ok'
    
    return app

# Para gunicorn rodar o Flask, ele precisa de uma variável 'app' global
app = main()
