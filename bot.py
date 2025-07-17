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
    if update.message.chat.type != 'private' and not user_message.startswith('/'):
        # Verifica se o bot foi mencionado
        if BOT_USERNAME.lower() in user_message.lower():
            # Remove a menção ao bot para processar a pergunta
            response_text = find_answer(user_message.replace(f"@{BOT_USERNAME}", "").strip())
            await update.message.reply_text(response_text)
            return
        else:
            # Se não mencionou o bot em grupo, ignora
            return

    # Para mensagens privadas ou comandos em grupo
    response = find_answer(user_message)
    await update.message.reply_text(response)


# --- Envio de Mensagem para o Admin ---
async def send_admin_message(message: str):
    bot_instance = Bot(token=BOT_TOKEN) # Criar a instância do bot dentro da função
    try:
        await asyncio.sleep(1) # Pequena pausa para garantir que o log seja escrito antes
        await bot_instance.send_message(chat_id=ADMIN_CHAT_ID, text=message)
        logger.info(f"Mensagem de admin enviada: {message}")
    except Exception as e:
        logger.error(f"Falha ao enviar mensagem para o admin {ADMIN_CHAT_ID}: {e}")

# --- Configuração do Application do PTB (para o Webhook) ---
application = ApplicationBuilder().token(BOT_TOKEN).build()

application.add_handler(MessageHandler(filters.COMMAND, start_command))
application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))


# --- Rotas do Flask para o Webhook ---
@app.route('/webhook', methods=['POST'])
async def webhook():
    if not BOT_TOKEN:
        logger.error("Webhook recebido, mas BOT_TOKEN não está configurado.")
        abort(500)

    bot_instance = Bot(token=BOT_TOKEN)
    update_data = request.get_json()

    if not update_data:
        logger.warning("Webhook recebido sem dados JSON.")
        abort(400)

    update = Update.de_json(update_data, bot_instance)
    logger.debug(f"Webhook: Recebida atualização - {update.update_id}")

    try:
        # Usar application.update_queue.put(update) para processar assincronamente
        # ou processar diretamente se o flask for async (com uvicorn worker)
        await application.process_update(update) # process_update é assíncrono
    except Exception as e:
        logger.error(f"Erro ao processar atualização do Telegram: {e}")
        abort(500)

    return 'ok'

@app.route('/')
def hello_world():
    return 'Bot is running!'

# --- Configuração e Início do Webhook ---
# Esta função será chamada pela rota /set_webhook
async def setup_webhook():
    logger.info(f"Configurando webhook para: {WEBHOOK_URL}")
    bot_instance = Bot(token=BOT_TOKEN)
    try:
        await bot_instance.set_webhook(url=WEBHOOK_URL, allowed_updates=["message"])
        logger.info("Webhook configurado com sucesso!")
        # Enviar mensagem para o admin APÓS o webhook ser configurado
        asyncio.create_task(send_admin_message(f"Bot '{BOT_USERNAME}' iniciado e webhook configurado com sucesso no Render!"))
    except Exception as e:
        logger.critical(f"ERRO CRÍTICO: Falha ao configurar o webhook no Telegram: {e}")
        asyncio.create_task(send_admin_message(f"ERRO CRÍTICO: Bot '{BOT_USERNAME}' falhou ao configurar o webhook: {e}"))
        sys.exit(1) # Finaliza o processo se o webhook não puder ser configurado

@app.route('/set_webhook', methods=['GET'])
async def set_webhook_route():
    try:
        await setup_webhook()
        return 'Webhook setup initiated successfully!'
    except Exception as e:
        logger.error(f"Erro ao iniciar setup do webhook pela rota: {e}")
        return f"Erro ao iniciar setup do webhook: {e}", 500

if __name__ == '__main__':
    # Em ambientes como o Render/Gunicorn, este bloco não é executado diretamente para rodar o app.
    # A linha de comando `gunicorn bot:app` é que faz o Flask app rodar.
    # A configuração do webhook é feita via acesso à rota /set_webhook.
    logger.info("Script bot.py executado diretamente. Isso é normal em ambientes de desenvolvimento ou para testes específicos.")
