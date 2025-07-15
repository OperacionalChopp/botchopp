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
# A importação abaixo assume que faq_data.py está dentro da pasta base_conhecimento/
# Certifique-se de que faq_data.py está realmente lá e que você removeu a versão da raiz.
from base_conhecimento.faq_data import faq_data 

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
    finally: # <-- Este 'finally' e o que vem depois estavam faltando!
        # Desativa o modo IA após a resposta do Gemini ou erro
        context.user_data['using_ai'] = False
        logger.info(f"Modo IA desativado para o usuário {user_id}.") # <-- Esta é a linha 140 que estava incompleta

async def unknown(update: Update, context):
    logger.info(f"Comando desconhecido recebido: {update.message.text}")
    await update.message.reply_text("Desculpe, não entendi esse comando. Tente `/start` para começar.")

# --- Configuração do Flask App ---
flask_app = Flask(__name__)

# Variável global para a aplicação do Telegram (será inicializada)
application = None

async def setup_bot():
    """Função para configurar a aplicação do Telegram bot."""
    global application
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN não está definido nas variáveis de ambiente. O bot não pode ser iniciado.")

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Adicionando Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    application.add_handler(MessageHandler(filters.COMMAND, unknown)) # Para comandos não reconhecidos

    # Inicializa a aplicação para processamento de webhook
    await application.initialize()
    logger.info("Aplicação Telegram inicializada para webhooks.")


@flask_app.route('/api/telegram/webhook', methods=['POST'])
async def webhook_handler():
    logger.info("Webhook endpoint hit! (Recebendo requisição do Telegram)")
    if request.method == "POST":
       if application is None: # Apenas verifica se a aplicação foi criada
            logger.error("A aplicação do Telegram não está inicializada. Tentando configurar novamente.")
            try:
                await setup_bot() # Tenta configurar se não estiver inicializada
            except Exception as e:
                logger.critical(f"Falha ao configurar o bot no webhook: {e}", exc_info=True)
                return jsonify({"status": "error", "message": "Bot initialization failed"}), 500

        try:
            update = Update.de_json(request.get_json(force=True), application.bot)
            await application.process_update(update)
            logger.debug(f"Update processado com sucesso para update_id: {update.update_id}")
            return jsonify({"status": "ok"}), 200
        except Exception as e:
            logger.error(f"Erro ao processar atualização do webhook: {e}", exc_info=True)
            return jsonify({"status": "error", "message": str(e)}), 500
    else:
        logger.warning(f"Requisição webhook com método HTTP inesperado: {request.method}")
        abort(400)

# --- Rota de Health Check ---
@flask_app.route('/health', methods=['GET'])
def health_check():
    logger.info("Rota /health acessada.")
    return "OK", 200

# Bloco de inicialização principal para o Gunicorn
if __name__ == '__main__':
    # No Render, o Gunicorn executa o `flask_app` diretamente.
    # Esta parte abaixo geralmente é para execução LOCAL via `python bot.py`.
    # Para garantir que o bot seja inicializado mesmo sem uma requisição inicial ao webhook,
    # podemos adicionar uma chamada para setup_bot() aqui, mas no contexto do Gunicorn,
    # a primeira requisição ao webhook normalmente acionaria a inicialização.
    # No entanto, para garantir, vamos usar um hack para executar setup_bot() ao iniciar.
    # IMPORTANTE: Em ambientes de produção (como o Render com Gunicorn), o __name__ == '__main__'
    # não é o ponto de entrada principal. O Gunicorn importa o `flask_app` diretamente.
    # A inicialização deve ser parte do processo de importação do módulo, ou ser acionada pela
    # primeira requisição.

    # Para Render/Gunicorn, a inicialização será feita na primeira requisição ao webhook
    # ou podemos usar um mecanismo de inicialização antes do binding do Gunicorn.
    # Uma forma comum é ter uma função `init_app` que o Gunicorn possa chamar se necessário,
    # mas para simplificar, a verificação dentro de `webhook_handler` é mais robusta.

    # Para garantir que o `setup_bot` seja executado uma vez no início,
    # podemos adicionar uma chamada a ele. O Render (ou Gunicorn) executa o script uma vez
    # para carregar o `flask_app`.
    import asyncio
    try:
        # Tenta executar setup_bot() ao carregar o módulo
        asyncio.run(setup_bot())
        logger.info("Bot Telegram configurado na inicialização do módulo.")
    except Exception as e:
        logger.critical(f"ERRO FATAL NA CONFIGURAÇÃO INICIAL DO BOT: {e}", exc_info=True)
        # Re-raise para que o Render saiba que a inicialização falhou
        raise

    pass # Mantenha o pass se você não tem código de execução local aqui.
