import logging
import json
import os
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import (
    Application, # Alterado: Importar Application
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

# O objeto Bot ainda é necessário, mas a inicialização do dispatcher muda.
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
# O objeto Application será inicializado e armazenado como um atributo de 'app'

@app.route(f'/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
async def webhook(): # Adicionado 'async' pois Application.update_queue é assíncrono
    if request.method == "POST":
        update_json = request.get_json()
        if update_json:
            update = Update.de_json(update_json, bot)
            # Adiciona o update à fila de processamento da Application
            # app.application_instance é o nome do atributo que conterá a Application
            if hasattr(app, 'application_instance') and app.application_instance:
                # Usa o Application.update_queue para processar o update
                await app.application_instance.update_queue.put(update)
            else:
                logger.error("Application não foi inicializada corretamente para o webhook (atributo app.application_instance ausente).")
        return "ok"
    return "ok"

@app.route('/')
def index():
    return 'Bot está online!'

# Função para configurar e iniciar a Application
def setup_application():
    # Cria a Application diretamente com o token
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Adiciona os handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, answer_faq))

    # Configura o webhook
    if WEBHOOK_URL:
        try:
            # Não é mais 'bot.set_webhook', mas sim application.bot.set_webhook
            application.bot.set_webhook(WEBHOOK_URL)
            logger.info(f"Webhook configurado para: {WEBHOOK_URL}")
        except Exception as e:
            logger.error(f"Erro ao configurar o webhook: {e}")
    else:
        logger.warning("WEBHOOK_URL não configurada. O bot pode não funcionar via webhook.")
    
    return application

# Inicializa a Application uma vez quando o módulo é carregado
# e a associa a um atributo da instância 'app'.
app.application_instance = setup_application()

# Inicia o processamento em background (para o Application)
# Isso é importante para que a Application comece a escutar e despachar updates.
# Usamos application.run_polling() para iniciar o loop de eventos, mas em um ambiente de webhook
# a Application precisa ser iniciada de forma assíncrona ou em um thread separado,
# ou simplesmente deixamos o Gunicorn rodar a aplicação Flask e a Application
# processa os updates que chegam via webhook.
# Para o webhook, não chamamos run_polling, mas sim run_webhook.
# No Render, a Application precisa ser "executada" para seus handlers funcionarem.
# A forma mais simples de fazer isso com Flask/Gunicorn é ter o webhook
# adicionando as updates a uma fila, e a Application processando essa fila.
# application.run_webhook não é o que precisamos aqui, pois já temos o endpoint Flask.

# O que precisamos é iniciar a 'Application' para que ela gerencie os handlers e a fila de updates.
# No contexto de um servidor WSGI como Gunicorn, precisamos iniciar a Application de forma não-bloqueante.
# A forma mais simples para este cenário (webhook POST para /<token>)
# é deixar a Application rodando em segundo plano.

# Este trecho de código abaixo é crucial para que a Application realmente processe as mensagens.
# Ele roda a Application em um loop de eventos, mas de forma não-bloqueante para o Gunicorn/Flask.
# Para WS
