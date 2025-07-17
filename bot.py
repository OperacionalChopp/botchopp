import logging
import os
import asyncio
import json
import threading
from flask import Flask, request, jsonify
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, CallbackQueryHandler, CommandHandler
from telegram.ext import ApplicationBuilder

# Para a fila com Redis
import redis
from rq import Queue, Worker
from rq.job import Job
from redis.exceptions import ConnectionError as RedisConnectionError # Importar o erro específico

# --- Configuração de Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Variáveis de Ambiente e Configurações ---
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Verificação para garantir que o token foi carregado
if not TELEGRAM_BOT_TOKEN:
    logger.critical("ERRO CRÍTICO: A variável de ambiente 'BOT_TOKEN' não foi encontrada. Certifique-se de que está configurada no Render.")

# --- INÍCIO: NOVAS LINHAS PARA DEBUGAR faq_data.json ---
# Obter o caminho absoluto do diretório do script atual
script_dir = os.path.dirname(os.path.abspath(__file__))
faq_file_path = os.path.join(script_dir, 'faq_data.json')

logger.info(f"Caminho absoluto do diretório do script: {script_dir}")
logger.info(f"Tentando carregar faq_data.json de: {faq_file_path}")

faq_data = {}
try:
    if not os.path.exists(faq_file_path):
        logger.critical(f"ERRO CRÍTICO: O arquivo faq_data.json NÃO foi encontrado em {faq_file_path}. Por favor, verifique a localização do arquivo.")
    else:
        with open(faq_file_path, 'r', encoding='utf-8') as f:
            faq_data = json.load(f)
        logger.info("faq_data.json carregado com sucesso!")
except FileNotFoundError:
    logger.critical(f"ERRO CRÍTICO: O arquivo faq_data.json não foi encontrado em {faq_file_path}. Worker não poderá iniciar.")
except json.JSONDecodeError as e:
    logger.critical(f"ERRO CRÍTICO: Erro ao carregar faq_data.json. Verifique o formato JSON: {e}")

# --- Configuração do Redis (APENAS A PARTE DA CONEXÃO) ---
try:
    redis_conn = redis.from_url(
        REDIS_URL,
        decode_responses=True,
        # Removendo ssl_cert_reqs=None e ssl_check_hostname=False para permitir que a biblioteca Redis
        # negocie a conexão SSL automaticamente, o que geralmente resolve WRONG_VERSION_NUMBER
        # Se você tiver problemas persistentes, pode tentar reintroduzi-los COM CAREFUL.
    )
    redis_conn.ping() # Testar a conexão
    logger.info("Conexão com Redis estabelecida com sucesso.")
except RedisConnectionError as e:
    logger.critical(f"ERRO CRÍTICO: Não foi possível conectar ao Redis em {REDIS_URL}. Verifique a URL e a disponibilidade do serviço Redis. Worker não poderá iniciar: {e}")
    # É CRÍTICO que o worker não inicie sem Redis, então...
    exit(1) # Sai do processo se a conexão Redis falhar

# Configuração da fila RQ
queue = Queue(connection=redis_conn)

# --- Funções do Bot ---

async def start(update: Update, context):
    await update.message.reply_text(faq_data.get("1", {}).get("resposta", "Olá! Como posso ajudar?"))

async def help_command(update: Update, context):
    await update.message.reply_text("Eu sou um bot de FAQ. Você pode me perguntar sobre chopps, eventos, etc.")

async def process_message(update: Update, context):
    user_message = update.message.text.lower()
    best_match = None
    max_matches = 0

    for key, data in faq_data.items():
        if "palavras_chave" in data:
            matches = sum(1 for keyword in data["palavras_chave"] if keyword in user_message)
            if matches > max_matches:
                max_matches = matches
                best_match = data["resposta"]
    
    if best_match:
        await update.message.reply_text(best_match)
    else:
        # Se não encontrar correspondência, enfileira a pergunta para a IA
        user_id = update.effective_user.id
        message_id = update.message.message_id
        
        # Envia a mensagem de "pensando"
        thinking_message = await update.message.reply_text("🤔 Pensando na sua resposta...")
        
        # Enfileira a tarefa no Redis
        job = queue.enqueue(
            'bot_worker.process_ai_query', # 'bot_worker' é o nome do seu arquivo worker, e 'process_ai_query' a função
            {
                'user_id': user_id,
                'chat_id': update.effective_chat.id,
                'message_text': user_message,
                'thinking_message_id': thinking_message.message_id # Passa o ID da mensagem "pensando"
            },
            job_timeout=300 # Tempo limite maior para a IA
        )
        logger.info(f"Tarefa de IA enfileirada com ID: {job.id}")

async def button(update: Update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text=f"Você clicou no botão: {query.data}")

# --- Configuração do Flask para Webhook ---
app = Flask(__name__)

@app.route('/')
def index():
    return "Bot está rodando!"

@app.route('/webhook', methods=['POST'])
async def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), application.bot)
        await application.process_update(update)
        return jsonify({"status": "ok"}), 200
    return jsonify({"status": "bad request"}), 400

# --- Início do Bot ---
def run_bot():
    global application
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message))

    # Configurar webhook
    webhook_url = os.getenv("WEBHOOK_URL")
    if webhook_url:
        logger.info(f"Configurando webhook para: {webhook_url}/webhook")
        application.run_webhook(
            listen="0.0.0.0",
            port=int(os.getenv("PORT", "5000")),
            url_path="webhook",
            webhook_url=f"{webhook_url}/webhook"
        )
    else:
        logger.warning("WEBHOOK_URL não configurada. O bot pode não funcionar corretamente no Render.")
        # Se não há webhook_url, podemos tentar polling para desenvolvimento local
        logger.info("Iniciando bot em modo polling para desenvolvimento local (se não for no Render)...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    # Garante que o bot e o Flask rodem em threads diferentes ou com asyncio.run
    # Para o Render, run_webhook já é non-blocking, então basta chamá-lo
    run_bot()
