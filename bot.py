# bot.py (VERSÃO ANTIGA - COM ERRO DE DISPATCHER)

import os
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, Dispatcher # << Esta linha causa o erro!

# Seus handlers (comandos e mensagens)
def start(update, context):
    update.message.reply_text('Olá! Eu sou seu bot.')

def echo(update, context):
    update.message.reply_text(update.message.text)

# Sua função principal do bot
def main():
    TOKEN = os.environ.get('BOT_TOKEN')
    WEBHOOK_URL = os.environ.get('WEBHOOK_URL')

    updater = Updater(TOKEN, use_context=True) # << ERRO AQUI!
    dispatcher = updater.dispatcher # << ERRO AQUI!

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & (~Filters.command), echo))

    # Configuração do webhook para Flask
    updater.start_webhook(listen="0.0.0.0",
                          port=int(os.environ.get('PORT', '5000')),
                          url_path=TOKEN)
    updater.bot.set_webhook(WEBHOOK_URL + TOKEN)

    app = Flask(__name__)

    @app.route(f'/{TOKEN}', methods=['POST'])
    def respond():
        update = Update.de_json(request.get_json(force=True), updater.bot)
        dispatcher.process_update(update) # << ERRO AQUI!
        return 'ok'

    return app

app = main() # Para gunicorn rodar o Flask
