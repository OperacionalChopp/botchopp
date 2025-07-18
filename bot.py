import os
import json
import logging
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
import google.generativeai as genai
from dotenv import load_dotenv
import asyncio # Importar asyncio

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
        # As linhas abaixo foram indentadas corretamente dentro do bloco 'try'
        faq_data = {item["pergunta"].lower(): item["resposta"] for item in faq_list.values()}
        logger.info("FAQ_DATA carregado com sucesso.")
    except FileNotFoundError:
        logger.error("Arquivo faq_data.json não encontrado.")
        faq_data = {}
    except json.JSONDecodeError:
        logger.error("Erro ao decodificar faq_data.json. Verifique a sintaxe JSON.")
        faq_data = {}
    except Exception as e:
        logger.error(f"Erro inesperado ao carregar faq_data: {e}")
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

        telegram_app = Application.builder().token(token).build()

        telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        await telegram_app.initialize()
        logger.info("Aplicação do Telegram Bot inicializada.")

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
    # Garante que as inicializações síncronas aconteçam
    load_faq_data()
    configure_gemini_api()

    # Tenta inicializar o app do Telegram se ainda não estiver pronto
    # Executa a função assíncrona de inicialização do Telegram dentro do loop de eventos.
    # Isso é crucial para ambientes como Gunicorn que não rodam um loop de eventos automaticamente em todas as threads.
    try:
        if telegram_app is None or not telegram_app.updater.is_running:
            logger.info("Tentando inicializar a aplicação do Telegram Bot no webhook request.")
            await initialize_telegram_application()
    except Exception as e:
        logger.error(f"Erro crítico ao inicializar o Telegram Application no webhook: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Bot application failed to initialize"}), 500

    if telegram_app is None or not telegram_app.updater.is_running:
        logger.error("Aplicação do Telegram Bot não está inicializada ou rodando após tentativa.")
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

# Função principal que o Gunicorn vai chamar
def create_app():
    # As funções síncronas são chamadas aqui para garantir que sejam executadas uma vez na inicialização do Gunicorn.
    load_faq_data()
    configure_gemini_api()
    return app

# Se você estiver rodando localmente para testes (NÃO NO RENDER DIRETAMENTE):
if __name__ == "__main__":
    # Para teste local, é comum usar um loop de eventos para funções assíncronas.
    # No Render com Gunicorn, o Gunicorn gerenciará o loop.
    # Para rodar localmente e testar o webhook, você precisaria de um servidor ASGI como uvicorn.
    # Ex: uvicorn bot:app --port 8000 --reload
    # Ou, para testar a funcionalidade assíncrona (como o `set_webhook`),
    # você pode forçar a execução assíncrona aqui, mas cuidado em ambientes de produção Gunicorn.
    load_faq_data()
    configure_gemini_api()

    # Este bloco NÃO é executado pelo Gunicorn no Render, apenas para testes locais diretos.
    # Se quiser testar o initialize_telegram_application() localmente, você pode fazer:
    # asyncio.run(initialize_telegram_application())
    pass
