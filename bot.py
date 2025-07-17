import logging
import os
import asyncio
import json
import threading
from flask import Flask, request, jsonify
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, CallbackQueryHandler, CommandHandler, ApplicationBuilder

# Para a fila com Redis
import redis
from rq import Queue
from redis.exceptions import ConnectionError as RedisConnectionError

# --- Configuração de Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Variáveis de Ambiente e Configurações ---
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
# REDIS_URL deve vir do ambiente (Render)
REDIS_URL = os.getenv("REDIS_URL") 
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Verificação para garantir que as variáveis essenciais foram carregadas
if not TELEGRAM_BOT_TOKEN:
    logger.critical("ERRO CRÍTICO: A variável de ambiente 'BOT_TOKEN' não foi encontrada. Certifique-se de que está configurada no Render.")
    exit(1) # Sai do processo se o token não estiver disponível

if not REDIS_URL:
    logger.critical("ERRO CRÍTICO: A variável de ambiente 'REDIS_URL' não foi encontrada. Certifique-se de que está configurada no Render.")
    exit(1) # Sai do processo se o REDIS_URL não estiver disponível

if not WEBHOOK_URL:
    logger.warning("AVISO: A variável de ambiente 'WEBHOOK_URL' não foi encontrada. O bot pode não funcionar corretamente em produção. Certifique-se de que está configurada no Render.")

# --- Carregamento da Base de Conhecimento ---
script_dir = os.path.dirname(os.path.abspath(__file__))
faq_file_path = os.path.join(script_dir, 'base_conhecimento', 'faq_data.json')

logger.info(f"Caminho absoluto do diretório do script: {script_dir}")
logger.info(f"Tentando carregar faq_data.json de: {faq_file_path}")

faq_data = {}
try:
    if not os.path.exists(faq_file_path):
        # AQUI: Se o arquivo não existe, é um erro crítico no deploy.
        logger.critical(f"ERRO CRÍTICO: O arquivo faq_data.json NÃO foi encontrado em {faq_file_path}. Verifique se o arquivo foi commitado e enviado para o repositório.")
        exit(1) # Impede o bot de iniciar sem a base de conhecimento
    else:
        with open(faq_file_path, 'r', encoding='utf-8') as f:
            faq_data = json.load(f)
        logger.info("faq_data.json carregado com sucesso!")
except FileNotFoundError: # Embora o os.path.exists já trate, é bom manter para robustez.
    logger.critical(f"ERRO CRÍTICO: O arquivo faq_data.json não foi encontrado em {faq_file_path}. Worker não poderá iniciar.")
    exit(1)
except json.JSONDecodeError as e:
    logger.critical(f"ERRO CRÍTICO: Erro ao carregar faq_data.json. Verifique o formato JSON: {e}. Worker não poderá iniciar.")
    exit(1)
except Exception as e:
    logger.critical(f"ERRO INESPERADO ao carregar faq_data.json: {e}. Worker não poderá iniciar.")
    exit(1)


# --- Configuração do Redis ---
redis_conn = None # Inicializa como None para controle de erro
try:
    # A biblioteca 'redis-py' lida bem com 'rediss://' e SSL automaticamente.
    # Evitamos configurações SSL explícitas para permitir a negociação padrão.
    redis_conn = redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=10 # Aumenta o timeout para conexão
    )
    redis_conn.ping() # Testar a conexão
    logger.info("Conexão com Redis estabelecida com sucesso.")
except RedisConnectionError as e:
    logger.critical(f"ERRO CRÍTICO: Não foi possível conectar ao Redis em {REDIS_URL}. Verifique a URL e a disponibilidade do serviço Redis. Worker não poderá iniciar: {e}")
    exit(1) # Sai do processo se a conexão Redis falhar
except Exception as e:
    logger.critical(f"ERRO INESPERADO ao conectar ao Redis: {e}. Worker não poderá iniciar.")
    exit(1)

queue = Queue(connection=redis_conn)

# --- Funções do Bot ---

async def start(update: Update, context):
    response_text = faq_data.get("1", {}).get("resposta", "Olá! Como posso ajudar? Minha base de conhecimento está carregada.")
    await update.message.reply_text(response_text)

async def help_command(update: Update, context):
    await update.message.reply_text("Eu sou um bot de FAQ. Você pode me perguntar sobre chopps, eventos, etc.")

async def process_message(update: Update, context):
    user_message = update.message.text.lower()
    best_match = None
    max_matches = 0

    if not faq_data:
        await update.message.reply_text("Desculpe, minha base de conhecimento não está disponível no momento.")
        return

    for key, data in faq_data.items():
        if "palavras_chave" in data:
            matches = sum(1 for keyword in data["palavras_chave"] if keyword in user_message)
            if matches > max_matches:
                max_matches = matches
                best_match = data["resposta"]
    
    if best_match:
        await update.message.reply_text(best_match)
    else:
        user_id = update.effective_user.id
        # chat_id para enviar a resposta de volta
        chat_id = update.effective_chat.id 
        
        thinking_message = await update.message.reply_text("🤔 Pensando na sua resposta...")
        
        # Enfileira a tarefa no Redis. Note que 'bot_worker.process_ai_query' foi alterado para 'worker.process_ai_query'
        # para refletir o nome do novo arquivo do worker.
        job = queue.enqueue(
            'worker.process_ai_query', # 'worker' é o nome do arquivo, 'process_ai_query' a função
            {
                'user_id': user_id, 
                'chat_id': chat_id, 
                'message_text': user_message, 
                'thinking_message_id': thinking_message.message_id,
                'telegram_bot_token': TELEGRAM_BOT_TOKEN # Passa o token para o worker, pois ele também precisa enviar mensagens
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

@
