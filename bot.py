# bot.py (VERSÃO CORRIGIDA - PARA python-telegram-bot 20.0+)

import os
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters # Importações atualizadas!

# Seus handlers (comandos e mensagens)
async def start(update: Update, context): # Adicionado 'async' para handlers
    await update.message.reply_text('Olá! Eu sou seu bot!')

async def echo(update: Update, context): # Adicionado 'async' para handlers
    await update.message.reply_text(update.message.text)

# Sua função principal do bot que retorna a aplicação Flask
def main():
    TOKEN = os.environ.get('BOT_TOKEN')
    WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
    PORT = int(os.environ.get('PORT', '5000')) # Definindo a porta

    # 1. Cria a Application
    application = Application.builder().token(TOKEN).build()

    # 2. Adiciona os handlers à Application
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), echo))

    # 3. Configura o webhook
    # Esta parte é importante para integrar com o Flask
    # A PTB 20+ gerencia o webhook de forma diferente para Flask
    app = Flask(__name__)

    @app.route(f'/{TOKEN}', methods=['POST'])
    async def webhook_handler(): # Handler do Flask agora é async
        """Processa as atualizações do Telegram via webhook."""
        # A atualização vem como JSON do Telegram
        json_data = await request.get_json(force=True)
        update = Update.de_json(json_data, application.bot)

        # Processa a atualização com a Application
        await application.process_update(update)
        return 'ok'

    # Certifique-se de que o webhook esteja configurado no Telegram
    # Isso é feito na linha de comando antes de iniciar o gunicorn, como nos seus logs:
    # python -c "import asyncio, os, telegram; asyncio.run(telegram.Bot(token=os.environ['BOT_TOKEN']).set_webhook(url=os.environ['WEBHOOK_URL']))"
    # A linha acima define o webhook no lado do Telegram.

    return app

# Para gunicorn rodar o Flask, ele precisa de uma variável 'app' global
# Então, chamamos a função main para obter a instância da aplicação Flask
app = main()
