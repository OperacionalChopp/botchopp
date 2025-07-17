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
logger.info(f"Current working directory (CWD): {os.getcwd()}")
try:
    # Listar arquivos no diretório atual e subdiretórios para garantir que faq_data.json é visível
    logger.info("Listing files in current directory and subdirectories...")
    for root, dirs, files in os.walk('.'):
        for file in files:
            full_path = os.path.join(root, file)
            logger.info(f"  Found file: {full_path}")
except Exception as e:
    logger.error(f"Error listing files: {e}")
# --- FIM: NOVAS LINHAS PARA DEBUGAR faq_data.json ---


# --- Carregamento da Base de Conhecimento ---
faq_data = [] # Inicializa como lista vazia por segurança
try:
    # Caminho ajustado: o Render geralmente coloca os arquivos na raiz do projeto
    # A ÚNICA LINHA QUE FOI ALTERADA É A SEGUINTE:
    with open('base_conhecimento/faq_data.json', 'r', encoding='utf-8') as f: #
        faq_data = json.load(f)
    logger.info("faq_data.json carregado com sucesso.")
except FileNotFoundError:
    logger.critical("ERRO CRÍTICO: O arquivo 'faq_data.json' não foi encontrado. Certifique-se de que ele está na raiz do seu repositório.")
    # Isso pode causar falhas em outras partes do bot se faq_data for essencial.
except json.JSONDecodeError as e:
    logger.critical(f"ERRO CRÍTICO: Erro ao carregar faq_data.json. Verifique o formato JSON: {e}")

# ... (restante do seu código, não alterado) ...

# --- Configuração do Redis (APENAS A PARTE DA CONEXÃO) ---
# Encontre o bloco onde você define 'redis_conn'
# Ele deve ficar assim:
# Removi o 'ssl_cert_reqs=None' do bot.py que você me forneceu anteriormente
# pois o from_url deveria pegar do rediss, mas para ter certeza vamos explicitar
# e adicionar ssl_check_hostname=False

# Apenas para testar se a conexão SSL funciona de alguma forma
# NÃO USE ssl_check_hostname=False EM PRODUÇÃO PARA SEGURANÇA SE POSSÍVEL
try:
    redis_conn = redis.from_url(
        REDIS_URL,
        decode_responses=True,
        ssl_cert_reqs=None,      # Mantenha este se você o tinha ou adicione
        ssl_check_hostname=False # ADICIONE ESTA LINHA para tentar contornar o problema do SSL
    )
    redis_conn.ping() # Testar a conexão
    logger.info("Conexão com Redis estabelecida com sucesso.")
except RedisConnectionError as e:
    logger.critical(f"ERRO CRÍTICO: Não foi possível conectar ao Redis em {REDIS_URL}. Verifique a URL e a disponibilidade do serviço Redis. Worker não poderá iniciar: {e}")
    # É CRÍTICO que o worker não inicie sem Redis, então vamos re-lançar a exceção
    # para que o deploy falhe explicitamente.
    raise # Adicione esta linha para garantir que o deploy pare se o Redis falhar.

# ... (restante do seu código, não alterado) ...
