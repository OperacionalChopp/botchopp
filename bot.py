import logging
import os
import asyncio
import json
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
# REDIS_URL será automaticamente preenchido pelo Render. Fallback para desenvolvimento local.
# IMPORTANTE: Para testes locais, certifique-se de que o Redis esteja rodando em localhost:6379
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Verificação para garantir que o token foi carregado
if not TELEGRAM_BOT_TOKEN:
    logger.critical("ERRO CRÍTICO: A variável de ambiente 'BOT_TOKEN' não foi encontrada. Certifique-se de que está configurada no Render.")
    # Em um ambiente de produção, você pode querer parar a execução se o token for essencial.
    # raise ValueError("BOT_TOKEN não configurado. Impossível prosseguir.")

# Construção da URL do Webhook
RENDER_EXTERNAL_HOSTNAME = os.getenv('RENDER_EXTERNAL_HOSTNAME')
WEBHOOK_URL = f"https://{RENDER_EXTERNAL_HOSTNAME}/api/telegram/webhook" if RENDER_EXTERNAL_HOSTNAME else None


# --- Conexão Redis ---
try:
    # A adição de ssl_cert_reqs=None é crucial para resolver o erro SSL: WRONG_VERSION_NUMBER
    # em alguns ambientes de nuvem como o Redis Cloud usado pelo Render.
    # Esta linha espera a versão atualizada do Redis (>=4.5.0) para funcionar corretamente com SSL.
    redis_conn = redis.from_url(REDIS_URL, decode_responses=True, ssl_cert_reqs=None)
    redis_conn.ping()  # Test connection
    logger.info("Conexão com Redis estabelecida com sucesso.")
except RedisConnectionError as e:
    logger.critical(f"ERRO CRÍTICO: Não foi possível conectar ao Redis em {REDIS_URL}. Verifique a URL e a disponibilidade do serviço Redis. Worker não poderá iniciar: {e}")
    # Se o Redis for essencial para o worker, o worker pode não funcionar corretamente sem ele.
    # Em um ambiente real, você pode querer que o processo do worker saia aqui.
    # import sys; sys.exit(1)
except Exception as e:
    logger.critical(f"ERRO DESCONHECIDO ao conectar ou usar Redis: {e}")
    # import sys; sys.exit(1)

# Inicializa a fila do RQ (se a conexão Redis for bem-sucedida)
if 'redis_conn' in locals() and redis_conn: # Verifica se redis_conn foi criada
    queue = Queue(connection=redis_conn)
else:
    # Caso a conexão Redis falhe, a fila não será inicializada.
    # Isso será tratado nos handlers que tentam enfileirar jobs.
    queue = None
    logger.error("Fila RQ não inicializada devido a falha na conexão Redis.")

# --- Carregamento da Base de Conhecimento (FAQ) ---
# O arquivo faq_data.json DEVE estar na mesma pasta do bot.py.
try:
    with open('faq_data.json', 'r', encoding='utf-8') as f:
        faq_data_raw = json.load(f)
    # Converte o dicionário de FAQs para uma lista de dicionários para facilitar a busca
    faq_data = list(faq_data_raw.values())
    logger.info(f"FAQ carregado com sucesso. Total de {len(faq_data)} itens.")
except FileNotFoundError:
    logger.critical("ERRO CRÍTICO: O arquivo 'faq_data.json' não foi encontrado. Certifique-se de que ele está no diretório correto.")
    faq_data = [] # Inicializa vazio para evitar erros posteriores
except json.JSONDecodeError:
    logger.critical("ERRO CRÍTICO: Erro ao decodificar 'faq_data.json'. Verifique a sintaxe JSON do arquivo.")
    faq_data = [] # Inicializa vazio
except Exception as e:
    logger.critical(f"ERRO CRÍTICO: Erro inesperado ao carregar FAQ: {e}")
    faq_data = [] # Inicializa vazio

# --- Funções de Ajuda do Bot ---

def find_faqs_by_keywords(text):
    """
    Encontra FAQs que contenham as palavras-chave no texto do usuário.
    Retorna uma lista de dicionários FAQ correspondentes.
    """
    text_lower = text.lower()
    matched_faqs = []
    for faq_item in faq_data:
        # Verifica se alguma das palavras-chave do FAQ está no texto do usuário
        if any(keyword.lower() in text_lower for keyword in faq_item.get('palavras_chave', [])):
            matched_faqs.append(faq_item)
    return matched_faqs

def generate_faq_response(matched_faqs):
    """
    Gera a resposta baseada nas FAQs encontradas.
    Se uma FAQ for encontrada, retorna a resposta.
    Se múltiplas forem encontradas, cria botões para cada uma.
    """
    if not matched_faqs:
        return "Desculpe, não consegui encontrar uma resposta para isso no momento. Poderia reformular sua pergunta ou tentar algo diferente? Se precisar de atendimento humano, digite 'humano'.", None
    elif len(matched_faqs) == 1:
        return matched_faqs[0]['resposta'], None
    else:
        # Múltiplas FAQs encontradas, oferece opções ao usuário
        keyboard_buttons = []
        for faq_item in matched_faqs:
            # Garante que o callback_data não exceda o limite de 64 bytes
            # Usamos o ID do FAQ como callback_data
            callback_data = f"faq_{faq_item['id']}"
            keyboard_buttons.append([InlineKeyboardButton(faq_item['pergunta'], callback_data=callback_data)])
        
        reply_markup = InlineKeyboardMarkup(keyboard_buttons)
        return "Encontrei algumas opções. Qual delas você gostaria de saber mais?", reply_markup

# --- Handlers do Bot (executados pelo RQ Worker) ---

async def handle_message_job(update_json):
    """
    Função a ser executada pelo RQ worker para processar mensagens.
    Recebe o update em formato JSON e o reconstrói.
    """
    update = Update.de_json(update_json, bot=Bot(token=TELEGRAM_BOT_TOKEN))
    chat_id = update.effective_chat.id
    user_message = update.message.text
    logger.info(f"Processando mensagem de {chat_id}: '{user_message}'")

    response_text, reply_markup = generate_faq_response(find_faqs_by_keywords(user_message))

    if reply_markup:
        await update.message.reply_text(response_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(response_text)
    logger.info(f"Update ID: {update.update_id} processado com sucesso.")


async def button_callback_job(update_json):
    """
    Função a ser executada pelo RQ worker para processar callbacks de botões.
    """
    update = Update.de_json(update_json, bot=Bot(token=TELEGRAM_BOT_TOKEN))
    query = update.callback_query
    chat_id = query.message.chat_id
    callback_data = query.data
    logger.info(f"Processando callback de botão de {chat_id}: '{callback_data}'")

    await query.answer() # Avisa o Telegram que a query foi recebida para remover o "loading" no botão

    if callback_data.startswith("faq_"):
        try:
            faq_id = int(callback_data.split("_")[1])
            faq_item = next((item for item in faq_data if item['id'] == faq_id), None)
            if faq_item:
                await query.edit_message_text(text=faq_item['resposta'])
                logger.info(f"Resposta FAQ {faq_id} enviada para {chat_id}.")
            else:
                await query.edit_message_text(text="FAQ não encontrada.")
                logger.warning(f"FAQ com ID {faq_id} não encontrada para callback.")
        except (IndexError, ValueError):
            await query.edit_message_text(text="Dados do botão inválidos.")
            logger.error(f"Erro ao processar callback_data inválido: {callback_data}")
    else:
        await query.edit_message_text(text="Ação desconhecida do botão.")
        logger.warning(f"Callback data desconhecido: {callback_data}")
    logger.info(f"Update ID: {update.update_id} (callback) processado com sucesso.")


# --- Aplicação Flask (Web Service) ---
flask_app = Flask(__name__)

# Cria uma instância da aplicação do Telegram Bot para definir o webhook
application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

@flask_app.route('/api/telegram/webhook', methods=['POST'])
async def telegram_webhook():
    """
    Endpoint para o webhook do Telegram.
    Recebe as atualizações do Telegram e as enfileira para processamento.
    """
    if not request.json:
        logger.warning("Webhook endpoint hit com requisição vazia.")
        return jsonify({'status': 'no content'}), 200

    logger.info("Webhook endpoint hit! (Recebendo requisição do Telegram)")
    update = Update.de_json(request.json, application.bot)

    if not queue:
        logger.error("Requisição de webhook recebida, mas a fila do Redis não está disponível. Retornando 503.")
        return jsonify({'status': 'Fila de processamento indisponível'}), 503

    try:
        # Enfileira a atualização para ser processada pelo worker RQ
        if update.message:
            job = queue.enqueue(handle_message_job, update.to_dict(), job_timeout=300)
        elif update.callback_query:
            job = queue.enqueue(button_callback_job, update.to_dict(), job_timeout=300)
        else:
            logger.info(f"Tipo de atualização não tratado: {update.update_id}. Ignorando.")
            return jsonify({'status': 'Update type not handled'}), 200

        logger.info(f"Atualização enfileirada para o RQ. Job ID: {job.id}")
        return jsonify({'status': 'ok', 'job_id': job.id}), 200
    except Exception as e:
        logger.error(f"Erro ao enfileirar atualização para o RQ: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@flask_app.route('/health', methods=['GET'])
def health_check():
    """
    Endpoint de health check para o Render.
    Verifica a conexão com o Redis e o bot.
    """
    try:
        if redis_conn and redis_conn.ping():
            redis_status = "OK"
        else:
            redis_status = "ERROR: Redis connection failed or ping failed."
    except Exception as e:
        redis_status = f"ERROR: Redis exception: {e}"

    if not TELEGRAM_BOT_TOKEN:
        bot_token_status = "ERROR: BOT_TOKEN not set."
    else:
        bot_token_status = "OK"

    status = {
        "status": "Healthy",
        "redis_connection": redis_status,
        "telegram_bot_token": bot_token_status,
        "queue_initialized": queue is not None
    }

    if "ERROR" in redis_status or "ERROR" in bot_token_status or not status["queue_initialized"]:
        status["status"] = "Degraded"
        return jsonify(status), 500
    return jsonify(status), 200


# --- Funções de Startup para o Render (chamadas pelo Procfile) ---

async def set_webhook_on_startup():
    """
    Define o webhook do Telegram. Esta função deve ser chamada na inicialização do serviço web.
    """
    if not WEBHOOK_URL:
        logger.critical("ERRO CRÍTICO: RENDER_EXTERNAL_HOSTNAME não configurado. Não é possível definir o webhook.")
        return

    logger.info("Iniciando setup do Web Service (Configuração de Webhook e Flask).")
    try:
        # Verifica se o webhook já está configurado corretamente
        current_webhook_info = await application.bot.get_webhook_info()
        if current_webhook_info.url == WEBHOOK_URL:
            logger.info("Webhook já está configurado corretamente. Nenhuma ação necessária.")
        else:
            # Define o webhook
            await application.bot.set_webhook(url=WEBHOOK_URL)
            logger.info(f"Webhook definido para: {WEBHOOK_URL}")
        logger.info("Configuração de webhook do Telegram concluída ou verificada com sucesso.")
    except Exception as e:
        logger.critical(f"ERRO CRÍTICO ao definir o webhook do Telegram: {e}")

    logger.info("Servidor Flask pronto para ser iniciado pelo Gunicorn.")


def run_ptb_worker():
    """
    Função para iniciar o RQ Worker que processa as atualizações do Telegram.
    Esta função deve ser chamada no serviço 'worker' do Procfile.
    """
    if not queue:
        logger.critical("RQ Worker não pode iniciar porque a fila não foi inicializada. Verifique a conexão Redis.")
        return

    logger.info("Iniciando RQ Worker para processar a fila do Telegram...")
    # O worker escuta na fila padrão 'default'
    worker = Worker([queue], connection=redis_conn)
    worker.work() # Isso inicia o loop de processamento do worker

# --- Ponto de Entrada para Execução Local ou Render ---

if __name__ == '__main__':
    # Este bloco é principalmente para testes e desenvolvimento local.
    # No ambiente Render, o Procfile.txt irá chamar as funções
    # 'set_webhook_on_startup' e 'run_ptb_worker' separadamente.

    logger.info("Executando em ambiente local (modo __main__).")
    logger.info("Para deploy no Render, use o Procfile e startup.sh.")

    # Exemplo de como rodaria no startup.sh para configurar o webhook
    asyncio.run(set_webhook_on_startup())

    # Para rodar o Flask server localmente (para receber webhooks)
    # Você precisaria de ngrok ou similar para expor este endpoint à internet.
    # flask_app.run(host='0.0.0.0', port=5000)

    # Para rodar o RQ worker localmente
    # run_ptb_worker()

    logger.info("Para testes locais completos, você precisará:")
    logger.info("1. Ter um servidor Redis rodando localmente (ex: `docker run -p 6379:6379 redis`)")
    logger.info("2. Em um terminal, inicie o worker RQ:")
    logger.info("   python -c \"from bot import run_ptb_worker; run_ptb_worker()\"")
    logger.info("3. Em *outro* terminal, inicie o servidor Flask (para o webhook):")
    logger.info("   python -c \"from bot import flask_app, set_webhook_on_startup; asyncio.run(set_webhook_on_startup()); flask_app.run(host='0.0.0.0', port=5000, debug=True)\"")
    logger.info("   - `set_webhook_on_startup()` configurará o webhook.")
    logger.info("   - `flask_app.run()` iniciará o servidor web para receber os webhooks.")
    logger.info("4. **Importante para testes locais:** Você precisará de uma forma de expor seu `localhost:5000` para a internet")
    logger.info("   (ex: ngrok, localtunnel) e configurar essa URL gerada como o webhook no BotFather do Telegram.")

    logger.info("No ambiente Render, o Procfile irá chamar as funções `set_webhook_on_startup` (via startup.sh) e `run_ptb_worker` separadamente.")
    logger.info("Certifique-se de que seu Procfile está configurado assim (ou similar):")
    logger.info("  web: gunicorn bot:flask_app --bind 0.0.0.0:$PORT --worker-class gevent --workers 2") # Ajuste --workers conforme sua necessidade
    logger.info("  worker: python -c \"from bot import run_ptb_worker; run_ptb_worker()\"")
