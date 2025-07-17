import os
import json
import logging
import ssl
import sys
from flask import Flask, request, abort
from redis import Redis
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, MessageHandler, filters
from rq import Queue
import asyncio

# --- Configuração de Logging (Melhorado) ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL)
)
logger = logging.getLogger(__name__)

# --- Variáveis de Ambiente e Configurações ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") # Embora não usado diretamente no código atual, é bom manter
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
REDIS_URL = os.getenv("REDIS_URL")

# --- Chat ID do Administrador (para alertas) ---
# Converta para int, com um valor padrão seguro
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "12345")) # Mude para o seu ID real, se for diferente.

# --- Nome de Usuário do Bot ---
BOT_USERNAME = os.getenv("BOT_USERNAME", 'Brahmachoppexpress_bot')

# --- Verificações de Variáveis Essenciais ---
if not BOT_TOKEN:
    logger.critical("ERRO CRÍTICO: A variável de ambiente 'BOT_TOKEN' NÃO foi encontrada. O bot não pode iniciar.")
    sys.exit(1)

if not WEBHOOK_URL:
    logger.warning("AVISO: A variável de ambiente 'WEBHOOK_URL' não foi encontrada. O bot pode não funcionar corretamente em produção. Certifique-se de que está configurada no Render.")

if not REDIS_URL:
    logger.critical("ERRO CRÍTICO: A variável de ambiente 'REDIS_URL' NÃO foi encontrada. O bot não pode iniciar sem o Redis.")
    sys.exit(1)

# --- Conexão Redis e RQ (Revertido para a versão anterior que "quase" funcionava) ---
redis_conn = None
queue = None
try:
    # Apenas com ssl_cert_reqs=ssl.CERT_NONE, como era antes dos problemas mais recentes
    redis_conn = Redis.from_url(
        REDIS_URL,
        decode_responses=True,
        ssl_cert_reqs=ssl.CERT_NONE # Mantém esta configuração que foi adicionada anteriormente
    )
    redis_conn.ping() # Testa a conexão
    queue = Queue(connection=redis_conn)
    logger.info("Conexão Redis estabelecida com sucesso!")
except Exception as e:
    logger.critical(f"ERRO CRÍTICO: Não foi possível conectar ao Redis em {REDIS_URL}. Verifique a URL e a disponibilidade do serviço Redis. O bot não poderá iniciar: {e}.")
    sys.exit(1)

# --- Carregamento da Base de Conhecimento (FAQ) ---
FAQ_DATA = {}
script_dir = os.path.dirname(os.path.abspath(__file__))
faq_path = os.path.join(script_dir, 'base_conhecimento', 'faq_data.json')

logger.info(f"Caminho absoluto do diretório do script: {script_dir}")
logger.info(f"Tentando carregar faq_data.json de: {faq_path}")

try:
    with open(faq_path, 'r', encoding='utf-8') as f:
        FAQ_DATA = json.load(f)
    logger.info("faq_data.json carregado com sucesso!")
except FileNotFoundError:
    logger.critical(f"ERRO CRÍTICO: O arquivo faq_data.json NÃO foi encontrado em {faq_path}. Verifique se o arquivo foi commitado e enviado para o repositório Git na pasta 'base_conhecimento'.")
    sys.exit(1)
except json.JSONDecodeError as e:
    logger.critical(f"ERRO CRÍTICO: Erro ao decodificar JSON em {faq_path}. Verifique a formatação do JSON: {e}")
    sys.exit(1)
except Exception as e:
    logger.critical(f"ERRO CRÍTICO: Um erro inesperado ocorreu ao carregar faq_data.json: {e}")
    sys.exit(1)

# --- Instância do Flask App ---
app = Flask(__name__)

# --- Funções do Bot ---
def find_answer(question):
    question_lower = question.lower()
    best_match = None
    best_score = 0

    for key, item in FAQ_DATA.items():
        keywords = [kw.lower() for kw in item.get('palavras_chave', [])]
        for keyword in keywords:
            if keyword in question_lower:
                if len(keyword) > best_score:
                    best_score = len(keyword)
                    best_match = item['resposta']
                break

    if best_match:
        return best_match
    return "Desculpe, não entendi sua pergunta. Poderia reformulá-la?"

async def start_command(update: Update, context):
    logger.info(f"Comando /start recebido de {update.effective_user.id}")
    await update.message.reply_text("Olá! Eu sou o Bot Chopp. Como posso ajudar você hoje?")

async def help_command(update: Update, context):
    logger.info(f"Comando /help recebido de {update.effective_user.id}")
    await update.message.reply_text("Posso responder perguntas sobre nosso chopp, horários de funcionamento e mais. Basta perguntar!")

async def handle_message(update: Update, context):
    user_message = update.message.text
    user_id = update.effective_user.id
    logger.info(f"Mensagem de {user_id}: {user_message}")

    # Ignora mensagens de grupo que não mencionam o bot e não são comandos
    if
