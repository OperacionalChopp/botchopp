import os
import logging
import asyncio
from dotenv import load_dotenv
from flask import Flask, request, abort
import redis
from telegram import Update, Bot
from telegram.ext import (
    Application, Dispatcher, MessageHandler, filters,
    CommandHandler, ApplicationBuilder
)
import google.generativeai as genai

# Carregar variáveis de ambiente do .env (para desenvolvimento local)
load_dotenv()

# --- Configurações ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL") # Deve ser a URL do seu serviço Render
REDIS_URL = os.getenv("REDIS_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configurar a API Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-pro')
else:
    logger.warning("GEMINI_API_KEY não configurada. Funcionalidades da Gemini AI estarão desabilitadas.")
    gemini_model = None

# Instanciar o bot
bot = Bot(token=BOT_TOKEN)

# Conexão com Redis
redis_conn = None
if REDIS_URL:
    try:
        # Adicionar parâmetros de SSL se a URL for 'rediss://'
        # ou se o Redis Cloud exigir SSL para a conexão padrão.
        # Ajuste ssl_cert_reqs para ssl.CERT_REQUIRED se você tiver o certificado
        # ou ssl.CERT_NONE se você quiser desabilitar a verificação (NÃO RECOMENDADO PARA PROD)
        
        # O problema WRONG_VERSION_NUMBER sugere que talvez o Redis Cloud esteja
        # esperando uma conexão SSL, mas o cliente não está negociando corretamente
        # ou a URL está apontando para uma porta não-SSL.
        # Tente forçar ssl_cert_reqs para ssl.CERT_NONE APENAS PARA TESTE INICIAL
        # para ver se é a verificação do certificado que está causando o problema.
        # Se funcionar, então você precisará investigar como obter e usar o certificado correto.
        # Caso contrário, pode ser que o Redis Cloud não suporte TLS 1.3 ou uma versão específica.
        
        import ssl
        
        # Analisa a URL para determinar se é SSL
        if REDIS_URL.startswith('rediss://'):
            redis_conn = redis.from_url(
                REDIS_URL,
                socket_connect_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
                ssl_cert_reqs=None # Alterado para None para teste. Mude para ssl.CERT_REQUIRED em produção com certificado
            )
        else:
            redis_conn = redis.from_url(
                REDIS_URL,
                socket_connect_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )

        redis_conn.ping()  # Testa a conexão
        logger.info("Conexão com Redis estabelecida com sucesso!")
    except redis.exceptions.ConnectionError as e:
        logger.critical(f"ERRO CRÍTICO: Não foi possível conectar ao Redis em {REDIS_URL}. O bot não poderá iniciar. Erro: {e}.")
        # Não tente enviar mensagem assíncrona aqui, pois o loop de eventos pode não estar pronto.
        # O Gunicorn/Render já irá sinalizar a falha.
        redis_conn = None # Garante que redis_conn seja None se a conexão falhar
    except Exception as e:
        logger.critical(f"ERRO INESPERADO ao conectar ao Redis: {e}")
        redis_conn = None
else:
    logger.warning("REDIS_URL não configurada. Algumas funcionalidades podem não funcionar.")

# Função para enviar mensagem ao admin (síncrona para ser chamada de forma segura aqui)
# Esta função AGORA NÃO SERÁ CHAMADA NA INICIALIZAÇÃO.
# Ela é apenas um utilitário para quando o bot já estiver rodando.
async def send_admin_message(message_text: str):
    if ADMIN_CHAT_ID:
        try:
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=message_text)
            logger.info(f"Mensagem de erro enviada ao admin: {message_text}")
        except Exception as e:
            logger.error(f"Não foi possível enviar mensagem ao admin {ADMIN_CHAT_ID}: {e}")

# Handlers
async def start(update: Update, context):
    await update.message.reply_text("Olá! Eu sou um bot integrado com a Gemini AI. Me envie uma mensagem e eu tentarei te responder!")

async def ask_gemini(update: Update, context):
    if not gemini_model:
        await update.message.reply_text("Desculpe, a Gemini AI não está configurada ou não conseguiu iniciar.")
        return

    user_message = update.message.text
    chat_id = update.message.chat_id

    try:
        if redis_conn:
            # Tentar obter histórico do Redis
            history_key = f"chat_history:{chat_id}"
            raw_history = redis_conn.lrange(history_key, 0, 9) # Últimas 10 interações
            chat_history = []
            for item in raw_history:
                try:
                    role, text = item.decode('utf-8').split(':', 1)
                    chat_history.append({"role": role, "parts": [text]})
                except ValueError:
                    logger.warning(f"Formato inválido no histórico do Redis: {item}")
                    continue
        else:
            chat_history = []

        # Adicionar a mensagem do usuário ao histórico para a chamada da API
        # A API Gemini espera 'user' e 'model' para o histórico
        gemini_history_for_api = []
        for entry in chat_history:
            if entry["role"] == "user":
                gemini_history_for_api.append({"role": "user", "parts": [entry["parts"][0]]})
            elif entry["role"] == "model":
                gemini_history_for_api.append({"role": "model", "parts": [entry["parts"][0]]})

        # Adicionar a mensagem atual do usuário
        gemini_history_for_api.append({"role": "user", "parts": [user_message]})

        # Iniciar chat com histórico (se houver)
        chat = gemini_model.start_chat(history=gemini_history_for_api[:-1]) # Exclui a mensagem atual do histórico para passá-la separadamente
        response = chat.send_message(user_message)

        bot_response = response.text

        # Armazenar histórico no Redis (se conectado)
        if redis_conn:
            try:
                redis_conn.rpush(history_key, f"user:{user_message}")
                redis_conn.rpush(history_key, f"model:{bot_response}")
                redis_conn.ltrim(history_key, -10, -1) # Manter apenas as últimas 10 interações
            except Exception as e:
                logger.error(f"Erro ao salvar histórico no Redis: {e}")
                await send_admin_message(f"⚠️ Alerta: Erro ao salvar histórico no Redis para {chat_id}: {e}")

        await update.message.reply_text(bot_response)

    except Exception as e:
        logger.error(f"Erro ao interagir com a Gemini API ou Redis: {e}", exc_info=True)
        await update.message.reply_text("Desculpe, ocorreu um erro ao processar sua solicitação. Tente novamente mais tarde.")
        await send_admin_message(f"🚨 ERRO: Bot '{BOT_USERNAME}' falhou ao processar mensagem de {chat_id}: {e}")


async def error_handler(update: object, context):
    logger.error(f"Erro no update {update}: {context.error}")
    if ADMIN_CHAT_ID:
        try:
            await send_admin_message(f"❌ Erro inesperado no bot!\n\nUpdate: {update}\nErro: {context.error}")
        except Exception as e:
            logger.error(f"Não foi possível enviar mensagem de erro ao admin: {e}")


# Inicializar Flask app
app = Flask(__name__)

# Configurar o Application do python-telegram-bot
application = ApplicationBuilder().bot(bot).build()

# Adicionar handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ask_gemini))

# Adicionar error handler
application.add_error_handler(error_handler)

@app.route('/')
def home():
    return "Bot is running!"

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
async def webhook():
    if request.method == "POST":
        update_json = request.get_json()
        if update_json:
            update = Update.de_json(update_json, bot)
            # Use process_update para lidar com o webhook
            # O application.update_queue já é assíncrono e thread-safe
            await application.process_update(update)
            return "ok", 200
        else:
            abort(400)
    else:
        abort(405)

# A linha `if __name__ == "__main__":` será executada apenas em execução local,
# não quando o Gunicorn/Uvicorn carrega o app.
# A configuração do webhook foi movida para o Start Command do Render.
