import os
import logging
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask, request, jsonify
import redis
import json
import asyncio # Necessário para create_task e para rodar funcoes async

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configurações do bot - Carregadas de variáveis de ambiente
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
REDIS_URL = os.environ.get("REDIS_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID") # Adicione esta variável de ambiente no Render
BOT_USERNAME = os.environ.get("BOT_USERNAME", "botchopp_bot") # Nome de usuário do bot para mensagens de erro

if not BOT_TOKEN:
    logger.critical("BOT_TOKEN não está configurado. O bot não pode iniciar.")
    exit(1)
if not WEBHOOK_URL:
    logger.critical("WEBHOOK_URL não está configurado. O bot não pode iniciar.")
    exit(1)
if not REDIS_URL:
    logger.critical("REDIS_URL não está configurado. O bot não pode iniciar.")
    exit(1)
if not GEMINI_API_KEY:
    logger.critical("GEMINI_API_KEY não está configurado. O bot não pode iniciar.")
    exit(1)

# Função para enviar mensagem ao administrador (definida aqui para resolver o NameError)
async def send_admin_message(message_text: str):
    if ADMIN_CHAT_ID:
        try:
            bot = Bot(token=BOT_TOKEN)
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=message_text)
            logger.info(f"Mensagem de administrador enviada com sucesso para {ADMIN_CHAT_ID}")
        except Exception as e:
            logger.error(f"Falha ao enviar mensagem de administrador para {ADMIN_CHAT_ID}: {e}")
    else:
        logger.warning("ADMIN_CHAT_ID não está configurado. Não é possível enviar mensagens de administrador.")

# Conexão com o Redis
try:
    redis_conn = redis.from_url(REDIS_URL)
    redis_conn.ping()  # Testa a conexão
    logger.info("Conectado ao Redis com sucesso!")
except redis.exceptions.ConnectionError as e:
    logger.critical(f"ERRO CRÍTICO: Não foi possível conectar ao Redis em {REDIS_URL}. Verifique a URL e a disponibilidade do serviço Redis. O bot não poderá iniciar: {e}.")
    # Tenta enviar mensagem de erro para o admin, mas o bot pode não ter inicializado completamente
    asyncio.create_task(send_admin_message(f"ERRO CRÍTICO: Bot '{BOT_USERNAME}' falhou ao conectar ao Redis: {e}"))
    exit(1) # Finaliza a execução se não conseguir conectar ao Redis

# Carregar base de conhecimento
FAQ_DATA = {}
try:
    with open("base_conhecimento/faq_data.json", "r", encoding="utf-8") as f:
        FAQ_DATA = json.load(f)
    logger.info("Base de conhecimento FAQ carregada com sucesso.")
except FileNotFoundError:
    logger.error("Arquivo faq_data.json não encontrado. A base de conhecimento não será utilizada.")
except json.JSONDecodeError:
    logger.error("Erro ao decodificar faq_data.json. Verifique a formatação do JSON.")

# Inicializar o aplicativo Flask
app = Flask(__name__)

# Inicializar o bot do Telegram
application = Application.builder().token(BOT_TOKEN).build()


# Handlers do Telegram (exemplo de implementação, adapte conforme sua lógica)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Olá! Eu sou o BotChopp. Como posso ajudar?")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Exemplo: Responder com a mesma mensagem
    await update.message.reply_text(update.message.text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_message = update.message.text.lower()
    response = "Desculpe, não entendi. Tente perguntar de outra forma."

    # Exemplo simples de busca na FAQ
    for entry in FAQ_DATA.get("perguntas_frequentes", []):
        if any(keyword in user_message for keyword in entry["palavras_chave"]):
            response = entry["resposta"]
            break
    
    # Se não encontrar na FAQ, pode passar para o Gemini (exemplo)
    # if response == "Desculpe, não entendi. Tente perguntar de outra forma.":
    #    try:
    #        # Aqui você integraria com a API do Gemini
    #        # Ex: response = await call_gemini_api(user_message, GEMINI_API_KEY)
    #        response = f"Você perguntou: '{user_message}'. (Integração Gemini aqui)"
    #    except Exception as e:
    #        logger.error(f"Erro ao chamar API Gemini: {e}")
    #        response = "No momento, não consigo processar sua solicitação com a IA. Tente mais tarde."

    await update.message.reply_text(response)

# Adicionar handlers ao dispatcher
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Rota para receber atualizações do webhook
@app.route("/", methods=["POST"])
async def webhook_handler():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), application.bot)
        
        # Processar a atualização
        # NOTA: Em produção com Gunicorn e Uvicorn, você deve usar run_polling ou set_webhook
        # e o processamento de atualizações em background com a Application.
        # Para um webhook, a abordagem comum é usar application.update_queue.put(update)
        # e um worker separado (rq) para processar a fila.
        # Este exemplo simples processa diretamente para fins de teste/demonstração.
        try:
            await application.process_update(update)
        except Exception as e:
            logger.error(f"Erro ao processar update do Telegram: {e}")
            # Você pode querer enviar este erro para o admin também
            asyncio.create_task(send_admin_message(f"Erro ao processar update no bot: {e}"))
        return "ok"
    return "ok"

# Rota de health check
@app.route("/health", methods=["GET"])
def health_check():
    return "Bot is running", 200

# Execução do aplicativo Flask (para o Gunicorn/Uvicorn)
if __name__ == '__main__':
    # Configura o webhook na inicialização
    # Em um ambiente de produção, esta configuração pode ser feita uma vez ou gerenciada externamente
    # No Render, geralmente o `startup.sh` ou similar cuida de setar o webhook.
    # Este bloco é mais para teste local ou para garantir que o webhook seja configurado.
    async def set_my_webhook():
        try:
            bot = Bot(token=BOT_TOKEN)
            await bot.set_webhook(url=WEBHOOK_URL)
            logger.info(f"Webhook configurado para: {WEBHOOK_URL}")
        except Exception as e:
            logger.error(f"Falha ao configurar o webhook: {e}")
            asyncio.create_task(send_admin_message(f"ERRO CRÍTICO: Bot '{BOT_USERNAME}' falhou ao configurar o webhook: {e}"))

    # Para rodar a função async em um contexto não-async
    # Isso é comum em scripts de inicialização ou quando usado diretamente
    try:
        asyncio.run(set_my_webhook())
    except RuntimeError as e:
        logger.warning(f"Não foi possível configurar o webhook via asyncio.run (pode já estar em um loop de eventos): {e}")
        # Se você está rodando com gunicorn/uvicorn, eles criam seu próprio loop de eventos.
        # Nesse caso, `asyncio.run` falharia. A solução é usar `asyncio.create_task`
        # ou garantir que o webhook seja configurado pelo script de startup.sh.
        # Para fins de deploy no Render, o `startup.sh` é o local mais robusto para isso.
    
    # Este bloco só é executado se você rodar o arquivo diretamente (e não via gunicorn/uvicorn)
    # Para Render, o Gunicorn/Uvicorn se encarrega de iniciar o app.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
