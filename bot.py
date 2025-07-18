import os
import json
import logging
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
import google.generativeai as genai
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Inicializa o Flask
app = Flask(__name__)

# Variáveis globais para o bot e o modelo Gemini
telegram_app: Application = None
gemini_model = None
faq_data = {} # Mantenha a estrutura de dicionário

# Carrega dados do FAQ
def load_faq_data():
    global faq_data
    try:
        with open("faq_data.json", "r", encoding="utf-8") as f:
            faq_list = json.load(f)
faq_data = {item["pergunta"].lower(): item["resposta"] for item in faq_list.values()}
logger.info("FAQ_DATA carregado com sucesso.")
    except FileNotFoundError:
        logger.error("Arquivo faq_data.json não encontrado.")
        faq_data = {}
    except json.JSONDecodeError:
        logger.error("Erro ao decodificar faq_data.json. Verifique a sintaxe JSON.")
        faq_data = {}

# Configura a API do Gemini
def configure_gemini_api():
    global gemini_model
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.error("GEMINI_API_KEY não está configurada nas variáveis de ambiente.")
            return
        genai.configure(api_key=api_key)
        gemini_model = genai.GenerativeModel('gemini-pro')
        logger.info("API do Gemini configurada.")
    except Exception as e:
        logger.error(f"Erro ao configurar a API do Gemini: {e}")

# Inicializa a aplicação do Telegram Bot (chamada uma única vez)
async def initialize_telegram_application():
    global telegram_app
    if telegram_app is None:
        token = os.getenv("BOT_TOKEN")
        if not token:
            logger.error("BOT_TOKEN não está configurado nas variáveis de ambiente.")
            return

        # Cria a aplicação sem o webhook inicialmente
        telegram_app = Application.builder().token(token).build()

        # Adiciona os handlers aqui (exemplo: para mensagens de texto)
        telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        # Inicializa a aplicação do telegram-bot
        await telegram_app.initialize()
        logger.info("Aplicação do Telegram Bot inicializada.")

        # Configura o webhook APÓS a inicialização da aplicação
        webhook_url = os.getenv("WEBHOOK_URL")
        if webhook_url:
            try:
                await telegram_app.bot.set_webhook(url=webhook_url)
                logger.info(f"Webhook configurado com sucesso para: {webhook_url}")
            except Exception as e:
                logger.error(f"Erro ao configurar o webhook com '{webhook_url}': {e}")
        else:
            logger.warning("WEBHOOK_URL não configurada. O bot não funcionará via webhook.")
    else:
        logger.info("Aplicação do Telegram Bot já está inicializada.")


# Handler para todas as mensagens de texto
async def handle_message(update: Update, context):
    user_message = update.effective_message.text.lower()
    chat_id = update.effective_chat.id
    logger.info(f"Mensagem recebida de {chat_id}: '{user_message}'")

    # 1. Tentar responder com o FAQ
    response = faq_data.get(user_message)
    if response:
        await update.message.reply_text(response)
        logger.info(f"Resposta do FAQ enviada para {chat_id}: '{response}'")
        return

    # 2. Se não encontrar no FAQ, consultar o Gemini
    if gemini_model:
        try:
            logger.info(f"Nenhum FAQ satisfatório encontrado para '{user_message}'. Consultando Gemini...")
            # Adicione um histórico de chat para manter o contexto
            chat = gemini_model.start_chat(history=[])
            gemini_response = chat.send_message(user_message).text
            await update.message.reply_text(gemini_response)
            logger.info(f"Resposta do Gemini enviada para {chat_id}: '{gemini_response}'")
            return
        except Exception as e:
            logger.error(f"Erro ao consultar Gemini para '{user_message}': {e}")

    # 3. Fallback se nada funcionar
    fallback_message = "Desculpe, não consegui encontrar uma resposta para sua pergunta. Por favor, tente reformular ou verifique as opções disponíveis."
    await update.message.reply_text(fallback_message)
    logger.info(f"Fallback enviado para {chat_id}: '{fallback_message}'")

# Rota para o webhook do Telegram
@app.route(f"/{os.getenv('BOT_TOKEN')}", methods=["POST"])
async def telegram_webhook():
    # Certifique-se de que a aplicação do bot está inicializada
    if telegram_app is None or not telegram_app.updater.is_running:
        logger.error("Aplicação do Telegram Bot não está inicializada ou rodando.")
        # Tentativa de inicializar (pode ser necessário um restart do serviço)
        await initialize_telegram_application()
        if telegram_app is None or not telegram_app.updater.is_running:
            return jsonify({"status": "error", "message": "Bot application not ready"}), 500


    try:
        update = Update.de_json(request.get_json(force=True), telegram_app.bot)
        await telegram_app.process_update(update)
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"Erro ao processar atualização do Telegram no webhook: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

# Rota raiz (para verificar se o serviço está vivo)
@app.route("/")
def home():
    return "Bot Chopp está online!"

# Executa a inicialização quando o aplicativo Flask é carregado
@app.before_request
def before_first_request():
    # Usar asyncio.run() aqui seria problemático se o gunicorn já tem um loop de eventos.
    # A melhor abordagem é ter a inicialização assíncrona feita pelo Gunicorn de forma apropriada.
    # No entanto, para garantir que initialize_telegram_application() seja chamado
    # e o webhook seja setado, podemos usar um truque ou confiar no primeiro POST
    # para disparar a inicialização.

    # Como gunicorn com gevent ou uvicorn gerenciam async,
    # 'before_request' não é o lugar ideal para asyncio.run().
    # A inicialização deve ser feita de forma mais integrada com o
    # ASGI server ou com a primeira requisição.

    # Chamamos diretamente as funções de setup que não são assíncronas
    load_faq_data()
    configure_gemini_api()
    # A inicialização assíncrona da aplicação do Telegram será feita
    # quando o webhook for chamado pela primeira vez, se ainda não estiver pronta.
    # Ou, idealmente, no startup do gunicorn/uvicorn.
    # Para Render, o 'gunicorn bot:app' inicia o Flask.
    # O set_webhook() é um método do bot, então precisa da Application.
    # A maneira mais robusta é ter um handler no gunicorn para isso.

    # Vamos fazer um workaround para o set_webhook, chamando-o quando a aplicação for instanciada.
    # Isso será melhor gerenciado dentro da função que retorna a aplicação para o gunicorn.
    pass # Mantemos vazio aqui para não bloquear o startup sync


# Função principal que o Gunicorn vai chamar
def create_app():
    # Esta função é chamada uma vez pelo Gunicorn para obter a instância da aplicação Flask.
    # Podemos inicializar as coisas assíncronas aqui, se o Gunicorn permitir o contexto async.
    # Para gunicorn[gevent], ele usa greenlets, então asyncio.run() ainda é um problema.
    # O python-telegram-bot Application.initialize() é async.
    # A melhor forma é deixar o `set_webhook` ser chamado apenas se `telegram_app` ainda não foi inicializado.

    # Chamadas síncronas que devem acontecer na inicialização do app
    load_faq_data()
    configure_gemini_api()

    # Retorna a instância do Flask. O webhook será configurado
    # na primeira requisição, se a aplicação ainda não estiver pronta.
    # Para ser mais robusto, é ideal usar `telegram_app.run_webhook()`
    # ou `telegram_app.run_polling()` se não for webhook, mas como é webhook,
    # o Flask lida com a requisição e passa para o `process_update`.

    return app

# Se você estiver rodando localmente para testes (NÃO NO RENDER DIRETAMENTE):
if __name__ == "__main__":
    # Apenas para teste local, não é usado no Render com Gunicorn
    # Certifique-se de que as variáveis de ambiente estão configuradas.
    load_faq_data()
    configure_gemini_api()
    # A inicialização assíncrona é mais complexa para teste local sem ASGI server.
    # Para teste local, você geralmente usaria telegram_app.run_polling()
    # ou um servidor ASGI como Uvicorn.

    # Para o Render, Gunicorn vai chamar `bot:app`, que é a instância do Flask.
    # A rota `/token` receberá as atualizações.

    # Para forçar a inicialização do app e webhook no startup do Gunicorn,
    # você pode mover a chamada para `initialize_telegram_application`
    # para um ponto onde o event loop já está disponível (por exemplo,
    # no handler da primeira requisição ou em um background task).
    # No seu caso atual, o `initialize_telegram_application` precisa ser chamado
    # ANTES que `telegram_app.process_update` seja invocado.
    pass # Não chame `app.run()` aqui para o Render.
