import os
import logging
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask, request, jsonify
import redis
import json
import asyncio # Necessário para create_task e para rodar funcoes async
import ssl # Necessário para configurar opções SSL para Redis

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
    logger.critical("GEMINI_API_KEY não está configurado. O bot não pode iniciar.")
    # Não vamos encerrar aqui, pois o bot pode funcionar parcialmente sem Gemini, mas registraremos o erro.
    # Se a integração com Gemini for CRÍTICA, você pode adicionar 'exit(1)' aqui.

# Função para enviar mensagem ao administrador (definida antes da conexão Redis para uso imediato)
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
# Tentativa de resolver o erro SSL: WRONG_VERSION_NUMBER
try:
    redis_conn = redis.from_url(
        REDIS_URL,
        ssl_cert_reqs=None, # Desabilita a verificação do certificado (PARA TESTE/DEPURAÇÃO, NÃO RECOMENDADO EM PROD.)
        ssl_version=ssl.PROTOCOL_TLSv1_2 # Força o uso do TLS 1.2, uma versão comum. Pode tentar ssl.PROTOCOL_TLS_CLIENT.
    )
    redis_conn.ping()  # Testa a conexão
    logger.info("Conectado ao Redis com sucesso!")
except redis.exceptions.ConnectionError as e:
    logger.critical(f"ERRO CRÍTICO: Não foi possível conectar ao Redis em {REDIS_URL}. Verifique a URL e a disponibilidade do serviço Redis. O bot não poderá iniciar: {e}.")
    # Tenta enviar mensagem de erro para o admin, garantindo que seja uma tarefa asyncio.
    # Se o loop de eventos ainda não estiver rodando (primeira vez que o Gunicorn/Uvicorn carrega o módulo),
    # create_task pode falhar com "no running event loop".
    # Em um cenário de Gunicorn/Uvicorn, a importação do módulo acontece antes do loop ser iniciado.
    # Por isso, lidar com esse erro de forma síncrona ou com um atraso é mais seguro.
    try:
        # Se você quer garantir que a mensagem seja enviada, mesmo que o bot não inicie,
        # pode tentar uma abordagem síncrona aqui se for possível, ou ajustar o entrypoint.
        # Para evitar 'RuntimeError: no running event loop' durante a inicialização do Gunicorn/Uvicorn,
        # é melhor não usar asyncio.create_task diretamente neste ponto crítico de inicialização.
        # O exit(1) abaixo já garante que o processo falhe.
        pass # Removemos o asyncio.create_task aqui para evitar o 'RuntimeError: no running event loop'
    except Exception as exc:
        logger.error(f"Não foi possível agendar mensagem de administrador durante erro de conexão Redis: {exc}")
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
        # logger.debug(f"Webhook data: {json_data}") # Cuidado com logs verbosos em prod.
        update = Update.de_json(json_data, application.bot)
        
        try:
            # Processa a atualização
            # Para ambientes de produção com Gunicorn/Uvicorn, a forma mais robusta é
            # enfileirar as atualizações para um worker RQ.
            # Para este exemplo direto, processamos na mesma thread Flask/Uvicorn,
            # o que pode ser um gargalo para alta carga, mas funciona para começar.
            await application.process_update(update)
            logger.info(f"Update do Telegram processado com sucesso para update_id {update.update_id}")
        except Exception as e:
            logger.error(f"Erro ao processar update do Telegram {update.update_id}: {e}", exc_info=True)
            # Envia o erro para o administrador.
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
    # No entanto, se precisar de um fallback ou para testes locais:
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
            asyncio.create_task(send_admin_message(f"🚨 ERRO CRÍTICO: Bot '{BOT_USERNAME}' falhou ao configurar o webhook na inicialização: {e}"))

    # Tenta configurar o webhook. asyncio.run() criará um novo loop de eventos.
    # No ambiente de produção com Gunicorn/Uvicorn, o loop de eventos já é gerenciado.
    # Se você vir um "RuntimeError: Event loop is already running", é normal.
    try:
        asyncio.run(set_my_webhook())
    except RuntimeError as e:
        logger.warning(f"Não foi possível configurar o webhook via asyncio.run (provavelmente o loop de eventos já está ativo pelo Uvicorn/Gunicorn): {e}")
    except Exception as e:
        logger.error(f"Erro inesperado ao tentar configurar o webhook: {e}", exc_info=True)

    # Inicia o servidor Flask localmente se o script for executado diretamente.
    # No Render, o Gunicorn/Uvicorn fará isso.
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Iniciando aplicativo Flask na porta {port}")
    app.run(host="0.0.0.0", port=port)
