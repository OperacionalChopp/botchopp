import os
from flask import Flask, request, abort, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
import google.generativeai as genai
import logging
from base_conhecimento.faq_data import faq_data  # Importação ajustada para a pasta base_conhecimento

# --- Configuração de Logging (Mantenha este bloco no topo) ---
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
# --- Fim da Configuração de Logging ---

# --- Variáveis de Ambiente ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_BOT_TOKEN:
    logger.critical("TELEGRAM_BOT_TOKEN não encontrado nas variáveis de ambiente! O bot não pode iniciar.")
    # Não levante erro fatal aqui, deixe o try-except principal lidar com isso
if not GEMINI_API_KEY:
    logger.critical("GEMINI_API_KEY não encontrado nas variáveis de ambiente! A IA não funcionará.")

# Configura a API Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# Dicionário para armazenar o histórico de conversa do Gemini
conversations = {}

# --- Funções do Bot ---

async def start(update: Update, context):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    logger.info(f"Comando /start recebido de {user_name} (ID: {user_id})")

    # Inicia uma nova conversa Gemini para o usuário
    conversations[user_id] = model.start_chat(history=[])

    welcome_message = (
        "Fala, mestre! 🍺 Bem-vindo à Loja CHOPP! O garçom digital está aqui pra te ajudar. "
        "O que manda hoje?!\n\n"
        "🍺 - Onde fica a loja?\n"
        "🕒 - Qual nosso horário?\n"
        "📜 - Quero ver o cardápio!\n"
        "🧠 - Tirar uma dúvida com a IA!\n\n"
        "É só pedir que eu trago a informação geladinha!"
    )
    await update.message.reply_text(welcome_message)

async def handle_message(update: Update, context):
    user_text = update.message.text.lower()
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    logger.info(f"Mensagem recebida de {user_name} (ID: {user_id}): {user_text}")

    # Verifica se o usuário quer usar a IA
    if "tirar uma dúvida com a ia" in user_text:
        await update.message.reply_text(
            "Certo! Estou ativando minha mente para suas perguntas. Pode mandar sua dúvida para a IA!"
        )
        context.user_data['using_ai'] = True
        return

    # Se o usuário está no modo IA
    if context.user_data.get('using_ai', False):
        await send_to_gemini(update, context)
        return

    # Lógica de FAQ
    matched_faqs = []
    for item in faq_data:
        if any(keyword in user_text for keyword in item["palavras_chave"]):
            matched_faqs.append(item)

    if not matched_faqs:
        await update.message.reply_text("Desculpe, não entendi. Posso te ajudar com o cardápio, horários ou localização?")
        logger.info(f"Nenhuma FAQ encontrada para: {user_text}")
    elif len(matched_faqs) == 1:
        await update.message.reply_text(matched_faqs[0]["resposta"])
        logger.info(f"Resposta direta da FAQ: {matched_faqs[0]['pergunta']}")
    else:
        keyboard = []
        for faq in matched_faqs:
            # Use 'pergunta' como texto do botão e 'id' como callback_data
            keyboard.append([InlineKeyboardButton(faq["pergunta"], callback_data=str(faq["id"]))])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Encontrei algumas opções. Qual delas você gostaria de saber?", reply_markup=reply_markup
        )
        logger.info(f"Múltiplas FAQs encontradas. Oferecendo botões para: {[f['pergunta'] for f in matched_faqs]}")

async def button_callback_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    selected_faq_id = query.data
    user_name = update.effective_user.first_name
    logger.info(f"Botão de FAQ pressionado por {user_name}: ID {selected_faq_id}")

    for item in faq_data:
        if str(item["id"]) == selected_faq_id:
            await query.edit_message_text(text=item["resposta"])
            logger.info(f"Resposta da FAQ por botão: {item['pergunta']}")
            return
    logger.warning(f"ID de FAQ não encontrado para callback_data: {selected_faq_id}")
    await query.edit_message_text(text="Desculpe, não consegui encontrar a informação para essa opção.")


async def send_to_gemini(update: Update, context):
    user_id = update.effective_user.id
    user_message = update.message.text
    user_name = update.effective_user.first_name
    logger.info(f"Enviando para Gemini de {user_name} (ID: {user_id}): {user_message}")

    if user_id not in conversations:
        logger.info(f"Iniciando nova conversa Gemini para o usuário {user_id}")
        conversations[user_id] = model.start_chat(history=[])

    try:
        response = await conversations[user_id].send_message_async(user_message)
        gemini_response_text = response.text
        logger.info(f"Resposta do Gemini para {user_id}: {gemini_response_text}")
        await update.message.reply_text(gemini_response_text)
    except Exception as e:
        logger.error(f"Erro ao comunicar com a API Gemini para o usuário {user_id}: {e}", exc_info=True)
        await update.message.reply_text("Desculpe, não consegui processar sua pergunta com a IA no momento.")
    finally:
        # Desativa o modo IA após a resposta do Gemini ou erro
        context.user_data['using_ai'] = False
        logger.info(
