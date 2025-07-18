import os
import logging
import json
import asyncio # Importar asyncio para set_webhook e rodar a API Gemini
from flask import Flask, request, jsonify # Import Flask e outros
from telegram import Update, Bot # Mantenha Bot aqui se ainda usar para Update.de_json
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from dotenv import load_dotenv
import unicodedata # Para normalize_text

# Importar a biblioteca do Google Generative AI
import google.generativeai as genai

# Carrega variáveis de ambiente do .env
load_dotenv()

# Configuração de logs
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Variáveis de ambiente
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL") # Ex: https://botchopp.onrender.com
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configurar a API do Gemini
gemini_model = None
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel('gemini-pro')
        logger.info("API do Gemini configurada.")
    except Exception as e:
        logger.error(f"Erro ao configurar a API do Gemini: {e}")
        gemini_model = None
else:
    logger.warning("GEMINI_API_KEY não configurada. A funcionalidade de IA generativa estará desabilitada.")

# Caminho completo para o webhook (a parte do token que o Telegram vai enviar as atualizações)
WEBHOOK_PATH = f"/{TELEGRAM_BOT_TOKEN}"
# URL completa que o Telegram vai usar para enviar as atualizações
FULL_WEBHOOK_URL = f"{WEBHOOK_URL}{WEBHOOK_PATH}"

# Inicializa o Flask app que o Gunicorn vai procurar
# Esta é a instância 'app' que o Gunicorn espera
app = Flask(__name__)

# Carregar FAQ_DATA
FAQ_DATA = {}
try:
    with open("faq_data.json", "r", encoding="utf-8") as f:
        FAQ_DATA = json.load(f)
    logger.info("FAQ_DATA carregado com sucesso.")
except FileNotFoundError:
    logger.error("Arquivo faq_data.json não encontrado.")
except json.JSONDecodeError:
    logger.error("Erro ao decodificar faq_data.json. Verifique a sintaxe JSON.")
except Exception as e:
    logger.error(f"Erro inesperado ao carregar FAQ_DATA: {e}")

# Função para normalizar texto (remover acentos e converter para minúsculas)
def normalize_text(text):
    text = text.lower()
    text = ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )
    return text

# Função para encontrar a melhor resposta no FAQ
def find_faq_answer(user_message):
    normalized_user_message = normalize_text(user_message)
    best_match_answer = None
    max_matches = 0
    
    # Adicionando um limiar mínimo de palavras para considerar uma correspondência válida
    MIN_KEYWORDS_MATCH = 1 # Pelo menos uma palavra-chave deve corresponder

    for entry_id, entry_data in FAQ_DATA.items():
        if entry_id == "54": # Ignorar o FAQ de "não encontrei minha dúvida" aqui
            continue

        keywords = [normalize_text(kw) for kw in entry_data.get("palavras_chave", [])]
        current_matches = 0

        for keyword in keywords:
            if keyword in normalized_user_message:
                current_matches += 1
        
        # Se encontrou mais correspondências e tem correspondências válidas
        if current_matches > max_matches and current_matches >= MIN_KEYWORDS_MATCH:
            max_matches = current_matches
            best_match_answer = entry_data.get("resposta") # Pega a resposta
    
    # Se uma resposta foi encontrada e atende ao mínimo de palavras-chave, retorne-a
    if best_match_answer and max_matches >= MIN_KEYWORDS_MATCH:
        logger.info(f"FAQ encontrado para '{user_message}': {best_match_answer[:50]}...")
        return best_match_answer
    
    logger.info(f"Nenhum FAQ satisfatório encontrado para '{user_message}'.")
    return None # Nenhuma resposta de FAQ satisfatória encontrada

# Handlers do Telegram
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    welcome_message = FAQ_DATA.get("1", {}).get(
        "resposta",
        "Bem-vindo! Como posso ajudar?"
    )
    await update.message.reply_text(welcome_message)
    logger.info(f"Comando /start recebido. Boas-vindas enviadas.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_message = update.message.text
    if not user_message:
        await update.message.reply_text("Recebi algo, mas não entendi. Poderia digitar sua pergunta?")
        logger.warning("Mensagem do usuário vazia ou não textual.")
        return

    logger.info(f"Mensagem recebida: '{user_message}'")

    # 1. Tentar encontrar resposta no FAQ
    faq_answer = find_faq_answer(user_message)

    if faq_answer:
        await update.message.reply_text(faq_answer)
    elif gemini_model: # 2. Se não encontrou no FAQ e Gemini está configurado, usar Gemini
        try:
            logger.info(f"Nenhuma resposta no FAQ. Consultando Gemini para: '{user_message}'")
            # Adicione um prompt para o Gemini para contextualizar
            prompt = (
                f"Você é um garçom digital de uma loja de CHOPP. "
                f"Responda à seguinte pergunta sobre chopp, quantidades para eventos, "
                f"produtos disponíveis, preços, descontos, ou como entrar em contato. "
                f"Se a pergunta for sobre um assunto fora do contexto de chopp ou informações de contato da loja, "
                f"diga que você não consegue responder a isso. "
                f"Pergunta do usuário: '{user_message}'"
            )
            
            # Chama a API de forma assíncrona, rodando em um thread separado para não bloquear
            response = await asyncio.to_thread(gemini_model.generate_content, prompt)
            gemini_response = response.text
            
            await update.message.reply_text(gemini_response)
            logger.info(f"Resposta do Gemini enviada para '{user_message}': {gemini_response[:50]}...")
        except Exception as e:
            logger.error(f"Erro ao consultar Gemini para '{user_message}': {e}", exc_info=True)
            # 3. Fallback se Gemini falhar
            fallback_message = FAQ_DATA.get("54", {}).get(
                "resposta",
                "Desculpe, não consegui encontrar uma resposta para sua pergunta no momento. Por favor, tente reformular ou entre em contato direto."
            )
            await update.message.reply_text(fallback_message)
            logger.info(f"Fallback enviado devido a erro do Gemini para '{user_message}': {fallback_message[:50]}...")
    else: # 3. Fallback se Gemini não estiver configurado ou não houver resposta no FAQ
        fallback_message = FAQ_DATA.get("54", {}).get(
            "resposta",
            "Desculpe, não consegui encontrar uma resposta para sua pergunta no momento. Por favor, tente reformular ou entre em contato direto."
        )
        await update.message.reply_text(fallback_message)
        logger.info(f"Fallback enviado (Gemini desabilitado ou não aplicável) para '{user_message}': {fallback_message[:50]}...")


# --- Função para configurar a aplicação do python-telegram-bot ---
_bot_application_instance = None # Variável para armazenar a instância do Application

def get_telegram_application() -> Application:
    global _bot_application_instance
    if _bot_application_instance is None:
        logger.info("Construindo a aplicação do Telegram Bot...")
        builder = Application.builder().token(TELEGRAM_BOT_TOKEN)
        _bot_application_instance = builder.build()

        # Adiciona os handlers
        _bot_application_instance.add_handler(CommandHandler("start", start))
        _bot_application_instance.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Define o webhook para o Telegram.
        # Isso precisa ser feito APÓS o bot ser totalmente inicializado.
        # Usamos asyncio.run() para rodar a corrotina set_webhook de forma síncrona aqui,
        # pois estamos no contexto de inicialização que não é assíncrono.
        if TELEGRAM_BOT_TOKEN and WEBHOOK_URL:
            try:
                # O set_webhook agora envia a URL COMPLETA para o Telegram
                asyncio.run(
                    _bot_application_instance.bot.set_webhook(url=FULL_WEBHOOK_URL)
                )
                logger.info(f"Webhook configurado para: {FULL_WEBHOOK_URL}")
            except Exception as e:
                logger.error(f"Erro ao configurar o webhook com '{FULL_WEBHOOK_URL}': {e}", exc_info=True)
        else:
            logger.warning("Variáveis TELEGRAM_BOT_TOKEN ou WEBHOOK_URL não configuradas. Webhook pode não funcionar.")

    return _bot_application_instance

# --- Rota do Flask para o Webhook ---
@app.route(WEBHOOK_PATH, methods=['POST'])
async def telegram_webhook():
    # Obtém a instância do Application (ela será construída na primeira chamada)
    telegram_app = get_telegram_application()

    if request.method == 'POST':
        update_json = request.get_json()
        if not update_json:
            logger.error("Nenhum JSON recebido na requisição POST do webhook.")
            return jsonify({"status": "error", "message": "No JSON received"}), 400

        try:
            # Passa a instância do bot da Application para Update.de_json
            update = Update.de_json(update_json, telegram_app.bot)
            await telegram_app.process_update(update) # Processa a atualização assincronamente
            logger.info("Atualização do Telegram processada com sucesso pelo Application.")
            return jsonify({"status": "ok"}), 200
        except Exception as e:
            logger.error(f"Erro ao processar atualização do Telegram no webhook: {e}", exc_info=True)
            return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "error", "message": "Method not allowed"}), 405

@app.route('/')
def index():
    # Isso é útil para o Render saber que o serviço está ativo
    return 'Bot do Chopp está online e esperando updates do Telegram!'

# --- Ponto de entrada para o Gunicorn (e para execução local) ---
if __name__ == "__main__":
    logger.info("Iniciando o bot localmente (se executado diretamente)...")
    # Para garantir que a aplicação do telegram-bot seja configurada antes de rodar o Flask
    get_telegram_application() 
    port = int(os.environ.get("PORT", 5000)) 
    logger.info(f"Flask app rodando na porta {port}")
    app.run(host="0.0.0.0", port=port, debug=True)
