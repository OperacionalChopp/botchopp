import os
import logging
import json
import asyncio # Mantenha asyncio, é usado internamente pelo PTB

from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from telegram.error import NetworkError

# --- Configuração de Logging (Mantenha este bloco no topo) ---
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
# --- Fim da Configuração de Logging ---

# Carregar dados do FAQ de um arquivo JSON
try:
    with open('base_conhecimento/faq_data.json', 'r', encoding='utf-8') as f:
        FAQ_DATA = json.load(f)
    logger.info("FAQ_DATA carregado com sucesso.")
except FileNotFoundError:
    logger.error("Arquivo faq_data.json não encontrado. Certifique-se de que está no diretório correto.")
    FAQ_DATA = {}
except json.JSONDecodeError:
    logger.error("Erro ao decodificar faq_data.json. Verifique a sintaxe do JSON.")
    FAQ_DATA = {}


# --- Funções do Bot (Sem alterações aqui) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia uma mensagem de boas-vindas quando o comando /start é emitido."""
    logger.info(f"Comando /start recebido de {update.effective_user.full_name} (ID: {update.effective_user.id})")
    await update.message.reply_text(
        'Olá! Sou o CHOPP Digital. Em que posso ajudar hoje? '
        'Você pode me perguntar sobre nossos produtos, horários de funcionamento ou como fazer seu pedido.'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia uma mensagem de ajuda quando o comando /help é emitido."""
    logger.info(f"Comando /help recebido de {update.effective_user.full_name} (ID: {update.effective_user.id})")
    await update.message.reply_text(
        'Aqui estão algumas coisas que posso fazer:\n'
        '- Perguntar sobre produtos\n'
        '- Saber sobre os horários de funcionamento\n'
        '- Tirar dúvidas gerais\n'
        'Seja específico em sua pergunta para eu poder ajudar melhor!'
    )

def find_faq_answers(user_message: str) -> list:
    """
    Procura por respostas no FAQ_DATA com base na mensagem do usuário.
    Retorna uma lista de dicionários com 'pergunta' e 'resposta'.
    """
    found_answers = []
    message_lower = user_message.lower()

    for item in FAQ_DATA.values():
        keywords = [kw.lower() for kw in item.get("keywords", [])]
        question_lower = item.get("pergunta", "").lower()

        if any(keyword in message_lower for keyword in keywords) or question_lower in message_lower:
            found_answers.append(item)
    return found_answers

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa mensagens de texto e tenta encontrar respostas no FAQ."""
    user_message = update.message.text
    chat_id = update.effective_chat.id
    user_full_name = update.effective_user.full_name
    logger.info(f"Mensagem recebida de {user_full_name} (ID: {chat_id}): {user_message}")

    found_faqs = find_faq_answers(user_message)

    if found_faqs:
        if len(found_faqs) == 1:
            faq_item = found_faqs[0]
            logger.info(f"FAQ encontrado para '{user_message}': {faq_item['pergunta']}")
            await update.message.reply_text(f"Resposta: {faq_item['resposta']}")
        else:
            keyboard = []
            for faq_item in found_faqs:
                callback_data = str(faq_item.get("id"))
                if callback_data:
                    keyboard.append([InlineKeyboardButton(faq_item['pergunta'], callback_data=callback_data)])
                else:
                    logger.warning(f"FAQ sem ID encontrado: {faq_item.get('pergunta', 'N/A')}")

            reply_markup = InlineKeyboardMarkup(keyboard)
            logger.info(f"Múltiplas FAQs encontradas. Oferecendo botões para: {[faq['pergunta'] for faq in found_faqs]}")
            await update.message.reply_text("Encontrei algumas opções. Qual delas você gostaria de saber?", reply_markup=reply_markup)
    else:
        logger.info(f"Nenhuma FAQ encontrada para '{user_message}'.")
        await update.message.reply_text(
            "Desculpe, não entendi. Posso te ajudar com o cardápio, horários ou localização?"
        )

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lida com as interações de botões inline."""
    query = update.callback_query
    user_full_name = update.effective_user.full_name
    logger.info(f"Botão de FAQ pressionado por {user_full_name}: ID {query.data}")

    try:
        await query.answer()
    except NetworkError as e:
        logger.error(f"NetworkError ao responder ao callback query para {user_full_name} (ID: {query.data}): {e}")
        await query.edit_message_text(text="Desculpe, houve um erro ao processar sua solicitação. Por favor, tente novamente.")
        return
    except Exception as e:
        logger.error(f"Ocorreu um erro inesperado ao responder ao callback query para {user_full_name} (ID: {query.data}): {e}")
        await query.edit_message_text(text="Ocorreu um erro inesperado. Por favor, tente novamente mais tarde.")
        return

    selected_faq_id = query.data

    selected_faq = None
    for item in FAQ_DATA.values():
        if str(item.get("id")) == selected_faq_id:
            selected_faq = item
            break

    if selected_faq:
        logger.info(f"Respondendo à FAQ selecionada: {selected_faq['pergunta']}")
        await query.edit_message_text(text=f"Resposta: {selected_faq['resposta']}")
    else:
        logger.warning(f"FAQ com ID {selected_faq_id} não encontrada após clique no botão.")
        await query.edit_message_text(text="Desculpe, a informação selecionada não foi encontrada.")


# --- Configuração do Flask e do Bot ---

PORT = int(os.environ.get('PORT', 5000))
TOKEN = os.environ.get('BOT_TOKEN')

if not TOKEN:
    logger.critical("Variável de ambiente 'BOT_TOKEN' não definida. O bot não pode iniciar.")
    exit(1)

flask_app = Flask(__name__)

# --- INICIALIZAÇÃO ÚNICA DO BOT TELEGRAM ---
# Cria a instância do Application UMA VEZ
application = Application.builder().token(TOKEN).build()
logger.info("Instância do Bot Telegram criada.")

# Adiciona handlers UMA VEZ
application.add_handler(MessageHandler(filters.COMMAND, help_command)) # Primeiro, para comandos desconhecidos
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
application.add_handler(CallbackQueryHandler(button_callback_handler))

# Define o webhook UMA VEZ na inicialização do aplicativo
# Usamos uma função assíncrona para chamar set_webhook
async def set_telegram_webhook():
    webhook_url = os.environ.get('WEBHOOK_URL')
    if not webhook_url:
        logger.warning("Variável de ambiente 'WEBHOOK_URL' não definida. Tentando inferir para o Render.")
        # Para o Render, use RENDER_EXTERNAL_HOSTNAME
        webhook_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/api/telegram/webhook"
        logger.info(f"Webhook URL inferida: {webhook_url}")

    if webhook_url:
        # ATENÇÃO: set_webhook deve ser chamado APENAS UMA VEZ no início.
        # Ele é assíncrono, então precisamos de um loop de evento para executá-lo.
        # No ambiente Gunicorn, isso pode ser um pouco complicado.
        # A forma mais segura é garantir que seja chamado antes do loop de eventos principal do Gunicorn.
        # Para Render, que usa gunicorn, o ideal é que esta configuração seja feita na inicialização.
        # O `initialize()` também deve ser chamado antes de processar qualquer update.
        await application.bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook definido para: {webhook_url}")
    else:
        logger.critical("Não foi possível determinar a WEBHOOK_URL. O bot pode não receber atualizações.")

    # IMPORTANTE: Chame initialize() AQUI para garantir que o Application esteja pronto.
    application.initialize()
    logger.info("Application do Bot Telegram inicializado.")

# Antes de iniciar o servidor Flask, execute a configuração do webhook
# Como set_telegram_webhook é assíncrono, precisamos executá-lo em um loop de eventos.
# Para Gunicorn, que gerencia seu próprio loop, isso é um desafio.
# Uma forma comum é usar um truque ou garantir que o Gunicorn execute esta parte.
# No Render, que está rodando seu app via `gunicorn bot:flask_app`, a inicialização
# das variáveis globais acima e a chamada ao initialize() ocorrerão uma vez por worker.

# Se você notar problemas de inicialização com Gunicorn/Render, pode ser necessário
# mover a lógica de `set_webhook` para um ponto de entrada que é garantido
# ser executado apenas uma vez por processo worker, ou para um script de deploy.
# No entanto, a causa do erro original era o `initialize()`, então vamos focar nisso.

# --- Rotas do Flask (Sem alterações aqui, exceto o uso do 'application' global) ---

@flask_app.route('/health', methods=['GET'])
def health_check():
    """Endpoint para verificação de saúde."""
    logger.info("Rota /health acessada.")
    return jsonify({"status": "ok"}), 200

@flask_app.route('/api/telegram/webhook', methods=['POST'])
async def telegram_webhook():
    """Recebe e processa as atualizações do Telegram."""
    logger.info("Webhook endpoint hit! (Recebendo requisição do Telegram)")

    # O 'application' já está globalmente inicializado. Não precisa mais do setup_bot_application aqui.
    # O telegram.ext.Application espera um objeto Update
    # Convertemos o JSON da requisição para um objeto Update
    try:
        update_json = request.get_json()
        if update_json:
            # Passamos o 'application.bot' para o Update.de_json
            update = Update.de_json(update_json, application.bot)
            logger.debug(f"Update recebido: {update.update_id}")
            # Processa o update usando a instância global 'application'
            await application.process_update(update) # Erro original era aqui
            logger.debug(f"Update processado com sucesso para update_id: {update.update_id}")
            return jsonify({"status": "ok"}), 200
        else:
            logger.warning("Requisição POST ao webhook sem JSON.")
            return jsonify({"status": "bad request", "message": "No JSON payload"}), 400
    except Exception as e:
        logger.error(f"Erro ao processar update do Telegram: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

# --- Execução Local (Para desenvolvimento) ---
if __name__ == "__main__":
    logger.info("Iniciando bot localmente (modo de desenvolvimento).")
    # Para testes locais, você ainda precisará de um loop de evento para o set_webhook
    # e para rodar o bot em polling (se não estiver usando ngrok/webhooks locais).
    # Aqui, vamos garantir que a inicialização assíncrona seja chamada.

    # Configura o loop de eventos para o set_webhook
    loop = asyncio.get_event_loop()
    loop.run_until_complete(set_telegram_webhook())

    # Quando rodando localmente com `python bot.py`, você pode querer rodar o Flask
    # e o polling do Telegram se não estiver usando webhooks.
    # Para o Render, Gunicorn vai lidar com isso.
    # Se você quiser testar localmente com Flask e webhooks (ex: com ngrok),
    # remova a parte do run_polling e execute o Flask normalmente.
    flask_app.run(host='0.0.0.0', port=PORT)
