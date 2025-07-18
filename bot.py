import logging
import json
import os
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    filters
)
from dotenv import load_dotenv

# Carrega as variáveis de ambiente (se existirem, ótimo; se não, apenas não fará nada)
load_dotenv()

# Configura o logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Token e URL do Webhook
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Verifica se o token está presente antes de tentar usar
if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN não encontrado nas variáveis de ambiente.")
    exit(1) # Sai do programa se o token não estiver configurado

bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Carrega os dados do FAQ
FAQ_DATA = {} # Inicializa como vazio por segurança
try:
    with open('faq_data.json', 'r', encoding='utf-8') as f:
        FAQ_DATA = json.load(f)
    logger.info("FAQ_DATA carregado com sucesso.")
except FileNotFoundError:
    logger.error("Arquivo faq_data.json não encontrado.")
except json.JSONDecodeError:
    logger.error("Erro ao decodificar faq_data.json. Verifique a sintaxe JSON.")
except Exception as e:
    logger.error(f"Erro inesperado ao carregar FAQ_DATA: {e}")


# --- Funções do Bot ---

def start(update: Update, context):
    faq_item = FAQ_DATA.get('1')
    if faq_item:
        update.message.reply_text(faq_item['resposta'])
    else:
        update.message.reply_text('Olá! Sou o garçom digital da Loja CHOPP. Como posso ajudar?')

def answer_faq(update: Update, context):
    user_message = update.message.text.lower()
    logger.info(f"Mensagem do usuário (minúsculas): {user_message}")

    found_faq = False

    for faq_id, data in FAQ_DATA.items():
        keywords = data.get('palavras_chave', [])
        logger.info(f"Verificando FAQ ID: {faq_id} com palavras-chave: {keywords}")

        if any(keyword in user_message for keyword in keywords):
            update.message.reply_text(data['resposta'])
            logger.info(f"Correspondência encontrada para FAQ ID: {faq_id}")
            found_faq = True
            return

    if not found_faq:
        nao_encontrei_faq = FAQ_DATA.get('54')
        if nao_encontrei_faq:
            update.message.reply_text(nao_encontrei_faq['resposta'])
            logger.info("Nenhuma FAQ específica encontrada, respondendo com FAQ ID 54.")
        else:
            update.message.reply_text("Desculpe, não entendi. Por favor, tente perguntar de outra forma ou entre em contato diretamente com a loja.")
            logger.info("Nenhuma FAQ específica encontrada e FAQ ID 54 não existe.")


# --- Configuração do Flask e Webhook ---

app = Flask(__name__)
# O dispatcher não será mais uma variável global fora de uma função de setup
# Ele será inicializado uma vez quando o app for criado/configurado

@app.route(f'/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
def webhook():
    if request.method == "POST":
        update_json = request.get_json()
        if update_json:
            update = Update.de_json(update_json, bot)
            # Acessamos o dispatcher diretamente do atributo 'app'
            # Isso garante que ele esteja disponível, pois 'setup_bot' será chamada
            if hasattr(app, 'dispatcher_instance') and app.dispatcher_instance:
                app.dispatcher_instance.process_update(update)
            else:
                logger.error("Dispatcher não foi inicializado corretamente para o webhook (atributo app.dispatcher_instance ausente).")
        return "ok"
    return "ok"

@app.route('/')
def index():
    return 'Bot está online!'

# Função para configurar e iniciar o bot e seus handlers
def setup_bot():
    # 'Updater' é usado para buscar updates, e ele contém o 'dispatcher'
    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
    
    # Obtém o dispatcher da instância do Updater
    dp = updater.dispatcher

    # Handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, answer_faq))

    # Configura o webhook
    # Esta linha deve ser executada apenas uma vez, idealmente na inicialização do servidor.
    # Se você já configurou o webhook manualmente no BotFather para a URL do Render,
    # pode ser que não precise chamar set_webhook a cada deploy, mas é seguro mantê-la.
    if WEBHOOK_URL:
        try:
            bot.set_webhook(WEBHOOK_URL)
            logger.info(f"Webhook configurado para: {WEBHOOK_URL}")
        except Exception as e:
            logger.error(f"Erro ao configurar o webhook: {e}")
    else:
        logger.warning("WEBHOOK_URL não configurada. O bot não funcionará via webhook.")

    return dp

# O Gunicorn precisa de uma instância 'app' Flask para rodar.
# Ao invocar 'gunicorn bot:app', ele carregará este módulo e procurará por 'app'.
# Vamos garantir que o dispatcher seja inicializado quando a aplicação Flask é criada/pronta.

# Inicializa o dispatcher uma vez quando o módulo é carregado
# e o associa a um atributo da instância 'app'.
# Isso garante que ele esteja disponível para o webhook.
app.dispatcher_instance = setup_bot()

# Nota: app.run() não é necessário aqui, pois o Gunicorn irá gerenciar o servidor Flask.
