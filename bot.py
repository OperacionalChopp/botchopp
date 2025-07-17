import logging
import os
import asyncio
import json
import threading
from flask import Flask, request, jsonify
from telegram import Update, Bot
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
REDIS_URL = os.getenv("REDIS_URL") 
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Verificação para garantir que as variáveis essenciais foram carregadas
if not TELEGRAM_BOT_TOKEN:
    logger.critical("ERRO CRÍTICO: A variável de ambiente 'BOT_TOKEN' não foi encontrada. Certifique-se de que está configurada no Render.")
    exit(1)

if not REDIS_URL:
    logger.critical("ERRO CRÍTICO: A variável de ambiente 'REDIS_URL' não foi encontrada. Certifique-se de que está configurada no Render.")
    exit(1)

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
        logger.critical(f"ERRO CRÍTICO: O arquivo faq_data.json NÃO foi encontrado em {faq_file_path}. Verifique se o arquivo foi commitado e enviado para o repositório Git na pasta 'base_conhecimento'.")
        exit(1)
    else:
        with open(faq_file_path, 'r', encoding='utf-8') as f:
            faq_data = json.load(f)
        logger.info("faq_data.json carregado com sucesso!")
except FileNotFoundError:
    logger.critical(f"ERRO CRÍTICO: O arquivo faq_data.json não foi encontrado em {faq_file_path}. O bot não poderá iniciar.")
    exit(1)
except json.JSONDecodeError as e:
    logger.critical(f"ERRO CRÍTICO: Erro ao carregar faq_data.json. Verifique o formato JSON: {e}. O bot não poderá iniciar.")
    exit(1)
except Exception as e:
    logger.critical(f"ERRO INESPERADO ao carregar faq_data.json: {e}. O bot não poderá iniciar.")
    exit(1)

# --- Configuração do Redis ---
redis_conn = None
try:
    redis_conn = redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=10 # Aumenta o timeout para conexão
    )
    redis_conn.ping() # Testar a conexão
    logger.info("Conexão com Redis estabelecida com sucesso.")
except RedisConnectionError as e:
    logger.critical(f"ERRO CRÍTICO: Não foi possível conectar ao Redis em {REDIS_URL}. Verifique a URL e a disponibilidade do serviço Redis. O bot não poderá iniciar: {e}")
    exit(1)
except Exception as e:
    logger.critical(f"ERRO INESPERADO ao conectar ao Redis: {e}. O bot não poderá iniciar.")
    exit(1)

queue = Queue(connection=redis_conn)

# --- Instância Global do ApplicationBuilder ---
# Esta instância é criada globalmente para ser acessível pelo Flask no webhook
application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

# Handlers do Bot
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
        chat_id = update.effective_chat.id 
        
        thinking_message = await update.message.reply_text("🤔 Pensando na sua resposta...")
        
        job = queue.enqueue(
            'worker.process_ai_query', # Nome do arquivo do worker e da função
            {
                'user_id': user_id, 
                'chat_id': chat_id, 
                'message_text': user_message, 
                'thinking_message_id': thinking_message.message_id,
                'telegram_bot_token': TELEGRAM_BOT_TOKEN 
            },
            job_timeout=300 
        )
        logger.info(f"Tarefa de IA enfileirada com ID: {job.id}")

async def button(update: Update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text=f"Você clicou no botão: {query.data}")

# Adiciona os handlers à aplicação global
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CallbackQueryHandler(button))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message))

# --- Configuração do Flask para Webhook ---
app = Flask(__name__)

# Rotas do Flask
@app.route('/')
def index():
    return "Bot está rodando! Acesse /webhook para as atualizações do Telegram."

@app.route('/webhook', methods=['POST'])
async def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), application.bot)
        # Processa a atualização em uma task assíncrona para não bloquear o webhook
        asyncio.create_task(application.process_update(update))
        return jsonify({"status": "ok"}), 200
    return jsonify({"status": "bad request"}), 400

# Função para configurar o webhook do Telegram.
# Esta função será chamada no início do deploy ou como um script separado para configurar o webhook.
async def setup_telegram_webhook():
    if WEBHOOK_URL:
        full_webhook_url = f"{WEBHOOK_URL}/webhook"
        try:
            await application.bot.set_webhook(url=full_webhook_url)
            logger.info(f"Webhook do Telegram configurado com sucesso para: {full_webhook_url}")
        except Exception as e:
            logger.error(f"Falha ao configurar o webhook do Telegram: {e}")
    else:
        logger.warning("WEBHOOK_URL não definida, não foi possível configurar o webhook do Telegram automaticamente.")

# Chamada principal quando o script é executado diretamente (ex: para testes locais ou setup inicial)
if __name__ == "__main__":
    # Para o Render, o Gunicorn executa o `app` Flask. 
    # A configuração do webhook deve ser um passo separado ou acionada uma vez.
    # No Render, você não deve chamar `application.run_webhook()` ou `application.run_polling()`
    # no comando de início do "Web Service" se estiver usando Gunicorn/Uvicorn para o Flask.
    # O Gunicorn vai rodar o Flask, e a rota /webhook do Flask vai processar as atualizações.

    # Esta parte é mais para rodar localmente ou para testes.
    # Em um ambiente de produção como Render, o Gunicorn inicia o Flask.
    # A configuração do webhook pode ser feita via um comando separado no Render (build command, por exemplo).
    # Ou, em um ambiente de desenvolvimento local, você pode chamar `application.run_polling()` diretamente.
    logger.info("Iniciando bot em modo de desenvolvimento/depuração (Flask e Telegram separados ou polling)...")
    
    # Inicia o servidor Flask em uma thread separada para não bloquear o loop do Telegram (se usar polling)
    # ou para que o Gunicorn possa gerenciá-lo.
    def run_flask_app():
        port = int(os.getenv("PORT", "5000"))
        logger.info(f"Iniciando Flask app na porta {port}...")
        # `debug=True` apenas para desenvolvimento local. Não use em produção.
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False) 

    # Se estiver rodando em produção (Render), Gunicorn/Uvicorn gerenciarão o Flask e o webhook.
    # A linha abaixo é útil para testar localmente.
    if os.getenv("RENDER") != "true": # Só roda localmente se não for Render
        # Para testes locais, você pode querer apenas o polling
        # ou rodar Flask e PTB Webhook em threads separadas.
        
        # Opção 1: Rodar Flask em thread e configurar webhook/polling em async loop
        flask_thread = threading.Thread(target=run_flask_app)
        flask_thread.start()

        # Configura webhook OU inicia polling
        async def main_local():
            if WEBHOOK_URL:
                await setup_telegram_webhook()
                # Em modo webhook local, você precisa de um servidor ASGI como application.run_webhook()
                # mas se o Flask já está rodando, é mais complexo.
                # Para local, polling é mais simples:
                logger.info("Executando Telegram Bot em modo polling localmente (Webhook configurado, mas polling para desenvolvimento).")
                await application.run_polling(allowed_updates=Update.ALL_TYPES)
            else:
                logger.info("WEBHOOK_URL não definida. Executando Telegram Bot em modo polling localmente.")
                await application.run_polling(allowed_updates=Update.ALL_TYPES)
        
        asyncio.run(main_local())
    # Em produção (Render), Gunicorn/Uvicorn chamam `app` e não precisam do `if __name__ == "__main__":`
    # para iniciar o Flask ou o Telegram Bot Application diretamente aqui.
    # O Telegram Bot Application será processado na rota /webhook.
