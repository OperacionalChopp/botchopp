import logging
import json
import os
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    filters # Alterado de 'Filters' para 'filters'
    # 'Dispatcher' foi removido desta linha, pois será acessado via updater.dispatcher
)
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Configura o logging para ver mensagens de depuração
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Token do seu bot do Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL") # Este deve ser a URL do seu serviço no Render

# Inicializa o bot
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Carrega os dados do FAQ
try:
    with open('faq_data.json', 'r', encoding='utf-8') as f:
        raw_faq_list = json.load(f)
        # CORREÇÃO AQUI: Itera sobre os VALORES do dicionário, não sobre as chaves
        FAQ_DATA = {str(item['id']): item for item in raw_faq_list.values()}
    logger.info("FAQ_DATA carregado com sucesso.")
except FileNotFoundError:
    logger.error("Arquivo faq_data.json não encontrado.")
    FAQ_DATA = {}
except json.JSONDecodeError:
    logger.error("Erro ao decodificar faq_data.json. Verifique a sintaxe JSON.")
    FAQ_DATA = {}
except Exception as e:
    logger.error(f"Erro inesperado ao carregar FAQ_DATA: {e}")
    FAQ_DATA = {}

# Função para a mensagem de boas-vindas
def start(update: Update, context):
    faq_item = FAQ_DATA.get('1') # Pegando a FAQ de ID 1 (boas-vindas)
    if faq_item:
        update.message.reply_text(faq_item['resposta'])
    else:
        update.message.reply_text('Olá! Sou o garçom digital da Loja CHOPP. Como posso ajudar?')

# Função para responder a dúvidas do FAQ
def answer_faq(update: Update, context):
    user_message = update.message.text.lower()

    # Tenta encontrar uma resposta baseada nas palavras-chave do FAQ
    for faq_id, data in FAQ_DATA.items():
        if any(keyword in user_message for keyword in data.get('palavras_chave', [])):
            update.message.reply_text(data['resposta'])
            return

    # Se não encontrar no FAQ, tenta encontrar a FAQ "Não encontrei minha dúvida" (ID 54)
    nao_encontrei_faq = FAQ_DATA.get('54')
    if nao_encontrei_faq:
        update.message.reply_text(nao_encontrei_faq['resposta'])
    else:
        update.message.reply_text("Desculpe, não entendi. Por favor, tente perguntar de outra forma ou entre em contato diretamente com a loja.")


# Configuração do Flask para o webhook
app = Flask(__name__)

# Declara o dispatcher como global para ser acessível na função webhook
dispatcher = None

@app.route(f'/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
def webhook():
    if request.method == "POST":
        # Processa o update usando o dispatcher que foi configurado em main()
        update_json = request.get_json()
        if update_json:
            update = Update.de_json(update_json, bot)
            # Verifica se o dispatcher foi inicializado antes de usá-lo
            if dispatcher:
                dispatcher.process_update(update)
            else:
                logger.error("Dispatcher não foi inicializado corretamente para o webhook.")
        return "ok"
    return "ok"

@app.route('/')
def index():
    return 'Bot está online!'

# Função principal para configurar e iniciar o bot
def main():
    # 'Updater' é usado para buscar updates, e ele contém o 'dispatcher'
    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
    
    # Obtém o dispatcher da instância do Updater
    dp = updater.dispatcher

    # Handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, answer_faq))

    # Configura o webhook
    # O bot.set_webhook é chamado apenas uma vez, ou quando a URL muda
    bot.set_webhook(WEBHOOK_URL)

    # Retorna o dispatcher para ser atribuído à variável global
    return dp

if __name__ == '__main__':
    # O dispatcher é inicializado quando o script é executado (localmente ou pelo Gunicorn)
    dispatcher = main()

    # Não chame app.run() quando estiver usando Gunicorn, pois o Gunicorn irá gerenciar a execução do Flask.
    # Esta linha é apenas para referência se você fosse rodar o Flask diretamente sem Gunicorn.
    # app.run(port=os.getenv("PORT", 5000))
