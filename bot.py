import os
import logging
import json
from flask import Flask, request, jsonify # Import Flask (mesmo que não inicializemos globalmente como 'app')
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from dotenv import load_dotenv
import unicodedata # Para normalize_text

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
REDIS_URL = os.getenv("REDIS_URL")

# Caminho completo para o webhook (parte que o Telegram vai enviar as atualizações)
# Isso deve ser a parte final da sua WEBHOOK_URL no Render (ex: /SEU_TOKEN_DO_BOT)
WEBHOOK_PATH = f"/{TELEGRAM_BOT_TOKEN}"
FULL_WEBHOOK_URL = f"{WEBHOOK_URL}{WEBHOOK_PATH}"

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

    for entry_id, entry_data in FAQ_DATA.items():
        # Ignorar o FAQ de "não encontrei minha dúvida" aqui, será o fallback
        if entry_id == "54":
            continue

        keywords = [normalize_text(kw) for kw in entry_data.get("palavras_chave", [])]
        current_matches = 0

        for keyword in keywords:
            if keyword in normalized_user_message:
                current_matches += 1

        if current_matches > max_matches:
            max_matches = current_matches
            best_match_answer = entry_data.get("resposta", "Desculpe, não consegui encontrar uma resposta específica para sua pergunta.")
            if max_matches > 0: # Se encontrar alguma correspondência, retorna logo
                return best_match_answer

    # Se não encontrar nenhuma correspondência ou a correspondência for fraca
    # Retorna a resposta padrão do FAQ (ID 54) ou uma mensagem genérica
    if best_match_answer is None or max_matches == 0:
        return FAQ_DATA.get("54", {}).get(
            "resposta",
            "Desculpe, não consegui encontrar uma resposta para sua pergunta no momento. Por favor, tente reformular ou entre em contato direto."
        )
    return best_match_answer

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # A resposta de boas-vindas deve vir do FAQ_DATA com ID 1
    welcome_message = FAQ_DATA.get("1", {}).get(
        "resposta",
        "Bem-vindo! Como posso ajudar?"
    )
    await update.message.reply_text(welcome_message)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_message = update.message.text
    if user_message:
        faq_answer = find_faq_answer(user_message)
        await update.message.reply_text(faq_answer)
    else:
        await update.message.reply_text("Recebi algo, mas não entendi. Poderia digitar sua pergunta?")

async def post_init(application: Application) -> None:
    """Configura o webhook após a inicialização do aplicativo."""
    if TELEGRAM_BOT_TOKEN and WEBHOOK_URL:
        # Importante: o URL enviado para o Telegram DEVE ser a base URL
        # O url_path na run_webhook define a parte do token.
        await application.bot.set_webhook(url=FULL_WEBHOOK_URL) # <-- Corrigido o 'await' e a URL
        logger.info(f"Webhook configurado para: {FULL_WEBHOOK_URL}")
    else:
        logger.warning("Variáveis TELEGRAM_BOT_TOKEN ou WEBHOOK_URL não configuradas. Webhook pode não funcionar.")

def main() -> None:
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)  # Chama post_init de forma assíncrona
        .build()
    )

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Iniciar o bot como um webhook
    # Esta parte configura o servidor web que vai ouvir as requisições do Telegram
    # O Gunicorn (rodando 'gunicorn bot:app') espera uma variável 'app'
    # mas 'python-telegram-bot' cuida do servidor web internamente com run_webhook
    # Se 'bot:app' não for encontrado pelo Gunicorn, ele pode falhar.
    # No entanto, esta era a versão anterior.
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", "10000")), # Render usa a porta 10000
        url_path=WEBHOOK_PATH.lstrip("/"), # O caminho sem a barra inicial para o run_webhook
        webhook_url=WEBHOOK_URL, # A URL base para o telegram
    )

if __name__ == "__main__":
    main()
