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

# Verificação de variáveis de ambiente essenciais
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
    logger.warning("GEMINI_API_KEY não está configurado. A funcionalidade Gemini pode estar limitada.")

# Função para enviar mensagem ao administrador (definida antes da conexão Redis para uso imediato)
# Note: Esta função ainda é assíncrona e precisa de um loop de eventos.
# Para chamadas críticas na inicialização *antes* do loop, a abordagem síncrona ou log é preferível.
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
# Removendo a chamada `asyncio.create_task` aqui, pois este é um ponto crítico
# antes do loop de eventos principal do Uvicorn estar ativo.
# O `exit(1)` já garante que o serviço não continue se o Redis não estiver acessível.
try:
    redis_conn = redis.from_url(REDIS_URL)
    redis_conn.ping()  # Testa a conexão
    logger.info("Conectado ao Redis com sucesso!")
except Exception as e: # Capture Exception para pegar TypeErrors e ConnectionErrors
    logger.critical(f"ERRO CRÍTICO: Não foi possível conectar ao Redis em {REDIS_URL}. O bot não poderá iniciar. Erro: {e}.")
    # Se você *realmente* precisa enviar uma mensagem de admin aqui, ela teria que ser síncrona
    # ou o serviço teria que ser iniciado de forma diferente. Por simplicidade e robustez,
    # neste ponto, vamos confiar nos logs e no `exit(1)`.
    exit(1) # Finaliza a execução se não conseguir conectar ao Redis

# Carregar base de conhecimento (exemplo de como carregar um JSON)
FAQ_DATA = {}
try:
    with open("base_conhecimento/faq_data.json", "r", encoding="utf-8") as f:
        FAQ_DATA = json.load(f)
    logger.info("Base de conhecimento FAQ carregada com sucesso.")
except FileNotFoundError:
    logger.error("Arquivo base_conhecimento/faq_data.json não encontrado. A base de conhecimento não será utilizada.")
except json.JSONDecodeError:
    logger.error("Erro ao decodificar base_conhecimento/faq_data.json. Verifique a formatação do JSON.")
except Exception as e:
    logger.error(f"Erro inesperado ao carregar base de conhecimento: {e}")

# Inicializar o aplicativo Flask
app = Flask(__name__)

# Inicializar o bot do Telegram
application = Application.builder().token(BOT_TOKEN).build()

# Handlers do Telegram (exemplo de implementação, adapte conforme sua lógica)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia uma mensagem quando o comando /start é emitido."""
    await update.message.reply_text("Olá! Eu sou o BotChopp. Como posso ajudar?")
    logger.info(f"Comando /start recebido de {update.effective_user.id}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa mensagens de texto."""
    user_message = update.message.text
    if user_message: # Garante que há texto na mensagem
        user_message_lower = user_message.lower()
        response = "Desculpe, não entendi. Tente perguntar de outra forma."

        # Tenta buscar na FAQ
        found_in_faq = False
        for entry in FAQ_DATA.get("perguntas_frequentes", []):
            if any(keyword in user_message_lower for keyword in entry["palavras_chave"]):
                response = entry["resposta"]
                found_in_faq = True
                break
        
        # Se não encontrar na FAQ, pode passar para o Gemini (ou outra IA)
        if not found_in_faq and GEMINI_API_KEY:
            try:
                # Aqui você integraria com a API do Gemini
                # Ex: response = await call_gemini_api(user_message, GEMINI_API_KEY)
                # Por enquanto, é apenas um placeholder:
                response = f"Você perguntou: '{user_message}'. (A integração com Gemini virá aqui em breve!)"
                logger.info(f"Mensagem processada por Gemini placeholder para {update.effective_user.id}")
            except Exception as e:
                logger.error(f"Erro ao chamar API Gemini: {e}")
                response = "No momento, não consigo processar sua solicitação com a IA. Tente mais tarde."
        elif not found_in_faq and not GEMINI_API_KEY:
             response = "Não consigo responder a essa pergunta. A chave Gemini API não está configurada."

        await update.message.reply_text(response)
        logger.info(f"Mensagem de {update.effective_user.id}: '{user_message}' - Resposta: '{response}'")
    else:
        logger.warning(f"Mensagem sem texto recebida de {update.effective_user.id}")
        await update.message.reply_text("Recebi sua mensagem, mas parece que ela não contém texto.")


# Adicionar handlers ao dispatcher do application
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


# Rota para receber atualizações do webhook
@app.route("/", methods=["POST"])
async def webhook_handler():
    """Lida com as requisições POST do webhook do Telegram."""
    if request.method == "POST":
        json_data = request.get_json(force=True)
        update = Update.de_json(json_data, application.bot)
        
        try:
            # `application.process_update` já lida com a execução assíncrona
            # dentro do contexto do loop de eventos do Uvicorn/Flask.
            await application.process_update(update)
            logger.info(f"Update do Telegram processado com sucesso para update_id {update.update_id}")
        except Exception as e:
            logger.error(f"Erro ao processar update do Telegram {update.update_id}: {e}", exc_info=True)
            # Aqui, como já estamos dentro de um loop de eventos, podemos usar asyncio.create_task
            asyncio.create_task(send_admin_message(f"🚨 Erro no bot '{BOT_USERNAME}' ao processar update {update.update_id}: {e}"))
        return "ok"
    return "ok"

# Rota de health check para o Render
@app.route("/health", methods=["GET"])
def health_check():
    """Endpoint para verificar a saúde do serviço."""
    logger.info("Health check solicitado.")
    return "Bot is running", 200

# Execução do aplicativo Flask (para o Gunicorn/Uvicorn)
if __name__ == '__main__':
    # Este bloco é executado quando o script é rodado diretamente (e.g., python bot.py).
    # No Render, o Gunicorn/Uvicorn que inicializa o 'app'.
    # A configuração do webhook deve ser feita no script de inicialização do Render (startup.sh)
    # ou por uma chamada API única, não a cada inicialização do processo worker.
    async def set_my_webhook():
        try:
            bot = Bot(token=BOT_TOKEN)
            webhook_info = await bot.get_webhook_info()
            if webhook_info.url != WEBHOOK_URL:
                await bot.set_webhook(url=WEBHOOK_URL)
                logger.info(f"Webhook configurado para: {WEBHOOK_URL}")
            else:
                logger.info("Webhook já está configurado corretamente.")
        except Exception as e:
            logger.error(f"Falha ao configurar o webhook: {e}", exc_info=True)
            # Aqui, se não houver um loop, a mensagem não será enviada.
            # Para testes locais, pode ser útil. Em produção, confie nos logs.
            print(f"ERRO: Falha ao configurar o webhook na inicialização: {e}")

    # Tenta configurar o webhook. `asyncio.run()` cria um novo loop de eventos
    # e só deve ser usado se *não* houver um loop rodando.
    # No ambiente de produção com Gunicorn/Uvicorn, o loop de eventos já é gerenciado.
    # Se você executa este script com `python bot.py`, ele funcionará.
    # Se for pelo Gunicorn, esta parte será ignorada ou causará o erro.
    # A maneira mais limpa para o Render é chamar o `set_webhook` APENAS NO SEU STARTUP COMMAND.
    # Vou manter o `asyncio.run` para o uso local, mas ciente que Gunicorn não usará isso.
    try:
        if os.environ.get("RUN_FLASK_LOCALLY") == "true" or not os.environ.get("RENDER"):
            # Este é um hack para rodar localmente ou quando não estiver no Render
            # e realmente querer que o bot inicie o loop Flask.
            # Para produção no Render, a linha `app.run` e `asyncio.run(set_my_webhook())`
            # *não serão executadas* porque o Gunicorn importa `app` diretamente.
            asyncio.run(set_my_webhook())
            port = int(os.environ.get("PORT", 5000))
            logger.info(f"Iniciando aplicativo Flask na porta {port}")
            app.run(host="0.0.0.0", port=port)
        else:
            logger.info("Executando no ambiente Render. Gunicorn/Uvicorn gerenciará a execução.")
            # Não chame app.run() ou asyncio.run() aqui, pois o Gunicorn/Uvicorn fará isso.
            # O Render assume que seu `gunicorn bot:app` no `Start Command`
            # é o suficiente para iniciar a aplicação.
            pass # O Gunicorn irá importar `app` e iniciá-lo.
    except RuntimeError as e:
        logger.warning(f"Não foi possível configurar o webhook via asyncio.run (provavelmente o loop de eventos já está ativo pelo Uvicorn/Gunicorn): {e}")
    except Exception as e:
        logger.error(f"Erro inesperado ao tentar configurar o webhook na inicialização local: {e}", exc_info=True)
