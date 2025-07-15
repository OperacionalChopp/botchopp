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
import asyncio

# --- Monkey Patching para Gevent e Asyncio ---
# Esta linha DEVE vir antes de qualquer outra importação que possa
# ser afetada pelo monkey patching (como 'requests', 'httpx', 'asyncio').
# Colocá-la logo após as importações básicas e antes do logging/outras importações
# garante que tudo seja "patchado" corretamente para funcionar com gevent.
from gevent import monkey
monkey.patch_all()
# --- Fim do Monkey Patching ---

# --- Configuração de Logging (Mantenha este bloco no topo) ---
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
# --- Fim da Configuração de Logging ---

# A importação abaixo assume que faq_data.py está dentro da pasta base_conhecimento/
from base_conhecimento.faq_data import faq_data

# --- Variáveis de Ambiente ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_BOT_TOKEN:
    logger.critical("TELEGRAM_BOT_TOKEN não encontrado nas variáveis de ambiente! O bot não pode iniciar.")
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
    if user_id not in conversations:
        conversations[user_id] = model.start_chat(history=[])
    else:
        # Reinicia a conversa se o usuário já tinha uma (opcional, pode ser mantido o histórico)
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
        
        # Opcional: Remova o teclado de FAQ se estiver presente e o usuário mudar para o modo IA
        if update.message.reply_markup and isinstance(update.message.reply_markup, InlineKeyboardMarkup):
            try:
                # Tenta editar a mensagem anterior do bot para remover os botões
                # ou edita a própria mensagem do usuário se for a última do bot
                # Nota: edit_reply_markup só funciona se a mensagem foi enviada pelo bot.
                # Como essa é uma nova mensagem do usuário, não há mensagem do bot para editar,
                # então essa parte é mais para cenários onde o bot enviou os botões por último.
                pass # Não fazemos nada aqui, a nova mensagem já "esconde" os botões
            except Exception as e:
                logger.warning(f"Não foi possível remover o teclado inline ao ativar IA: {e}")
        return

    # Se o usuário está no modo IA
    if context.user_data.get('using_ai', False):
        await send_to_gemini(update, context)
        return

    # Lógica de FAQ
    saudacoes = ["olá", "ola", "oi", "bom dia", "boa tarde", "boa noite", "e aí"]
    if any(saudacao in user_text for saudacao in saudacoes):
        await start(update, context)
        logger.info(f"Saudação detectada: '{user_text}'. Enviando mensagem de boas-vindas.")
        return

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
            await query.message.reply_text(text=item["resposta"])
            logger.info(f"Resposta da FAQ por botão (nova mensagem): {item['pergunta']}")
            return
    logger.warning(f"ID de FAQ não encontrado para callback_data: {selected_faq_id}")
    await query.message.reply_text(text="Desculpe, não consegui encontrar a informação para essa opção.")


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
        logger.info(f"Modo IA desativado para o usuário {user_id}.")


async def unknown(update: Update, context):
    logger.info(f"Comando desconhecido recebido: {update.message.text}")
    await update.message.reply_text("Desculpe, não entendi esse comando. Tente `/start` para começar.")

# --- Configuração do Flask App ---
flask_app = Flask(__name__)

# Variável global para a aplicação do Telegram (será inicializada uma vez por processo Gunicorn worker)
application_instance = None

async def get_telegram_application():
    """Retorna ou cria uma instância da aplicação do Telegram Bot."""
    global application_instance
    if application_instance is None:
        if not TELEGRAM_BOT_TOKEN:
            logger.critical("TELEGRAM_BOT_TOKEN não está definido. Não é possível criar a aplicação do Telegram.")
            raise ValueError("TELEGRAM_BOT_TOKEN not set.")

        application_instance = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        # Adicionando Handlers
        application_instance.add_handler(CommandHandler("start", start))
        application_instance.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application_instance.add_handler(CallbackQueryHandler(button_callback_handler))
        application_instance.add_handler(MessageHandler(filters.COMMAND, unknown))

        await application_instance.initialize()
        webhook_url = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
        if webhook_url:
            full_webhook_url = f"https://{webhook_url}/api/telegram/webhook"
            await application_instance.bot.set_webhook(url=full_webhook_url)
            logger.info(f"Webhook definido para: {full_webhook_url}")
        else:
            logger.warning("RENDER_EXTERNAL_HOSTNAME não definido. Webhook não será configurado automaticamente.")
        logger.info("Nova instância do Bot Telegram configurada.")
    return application_instance

@flask_app.route('/api/telegram/webhook', methods=['POST'])
async def webhook_handler():
    logger.info("Webhook endpoint hit! (Recebendo requisição do Telegram)")
    if request.method == "POST":
        try:
            # Obtém a instância da aplicação do Telegram.
            # Isso garante que cada worker do Gunicorn tenha sua própria instância
            # ou que a mesma instância seja reutilizada se já estiver configurada.
            application = await get_telegram_application()

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

# Este bloco não é mais necessário para inicializar a aplicação globalmente
# fora da rota do webhook, pois get_telegram_application() fará isso on-demand.
# O Gunicorn vai carregar o flask_app, e a primeira requisição vai configurar o bot.
# A única coisa que podemos fazer aqui é um logging para garantir que o TELEGRAM_BOT_TOKEN exista.
if not TELEGRAM_BOT_TOKEN:
    logger.critical("TELEGRAM_BOT_TOKEN não encontrado nas variáveis de ambiente! O bot não pode iniciar corretamente.")

# O `if __name__ == '__main__'` não é estritamente necessário para o Render/Gunicorn
# mas pode ser útil para testes locais.
if __name__ == '__main__':
    # Para testar localmente, você pode querer adicionar:
    # Este bloco executaria o Flask em modo de desenvolvimento.
    # Em produção com Gunicorn, este bloco não será executado.
    logger.info("Executando Flask localmente. Isso não acontece no Render com Gunicorn.")
    # No entanto, a inicialização assíncrona requer um loop de eventos.
    # asyncio.run(get_telegram_application()) # Para configurar o webhook uma vez
    # flask_app.run(debug=True, port=5000)
    pass
