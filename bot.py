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
# Certifique-se de que faq_data.py está realmente lá e que você removeu a versão da raiz.
from base_conhecimento.faq_data import faq_data

# --- Variáveis de Ambiente ---
# Renomeie as variáveis no Render para TELEGRAM_BOT_TOKEN e GEMINI_API_KEY
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
        
        # Opcional: Remova o teclado de FAQ se estiver presente e o usuário mudar para o modo IA
        # Isso evita que os botões de FAQ fiquem poluindo a tela quando a interação for com a IA
        if update.message.reply_markup and isinstance(update.message.reply_markup, InlineKeyboardMarkup):
            try:
                # Tenta editar a mensagem anterior do bot para remover os botões
                # ou edita a própria mensagem do usuário se for a última do bot
                await update.message.edit_reply_markup(reply_markup=None) 
                # Nota: edit_reply_markup só funciona se a mensagem foi enviada pelo bot.
                # Se for a mensagem do usuário, você pode ter que editar a última mensagem do bot
                # que continha os botões, se tiver o ID dela. Para simplificar,
                # a nova mensagem acima já "empurra" a antiga para cima.
            except Exception as e:
                logger.warning(f"Não foi possível remover o teclado inline ao ativar IA: {e}")
        return

    # Se o usuário está no modo IA
    if context.user_data.get('using_ai', False):
        await send_to_gemini(update, context)
        return

    # Lógica de FAQ
    # Adicionando tratamento para saudações básicas que devem ativar o /start ou uma saudação simples
    saudacoes = ["olá", "ola", "oi", "bom dia", "boa tarde", "boa noite", "e aí"]
    if any(saudacao in user_text for saudacao in saudacoes):
        await start(update, context) # Chama a função start para enviar a mensagem de boas-vindas
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
            # Use 'pergunta' como texto do botão e 'id' como callback_data
            keyboard.append([InlineKeyboardButton(faq["pergunta"], callback_data=str(faq["id"]))])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Encontrei algumas opções. Qual delas você gostaria de saber?", reply_markup=reply_markup
        )
        logger.info(f"Múltiplas FAQs encontradas. Oferecendo botões para: {[f['pergunta'] for f in matched_faqs]}")

async def button_callback_handler(update: Update, context):
    query = update.callback_query
    await query.answer() # Importante para parar o loading no botão
    selected_faq_id = query.data
    user_name = update.effective_user.first_name
    logger.info(f"Botão de FAQ pressionado por {user_name}: ID {selected_faq_id}")

    for item in faq_data:
        if str(item["id"]) == selected_faq_id:
            # === ALTERAÇÃO AQUI: USAR reply_text EM VEZ DE edit_message_text ===
            # Isso fará com que a resposta apareça como uma NOVA mensagem,
            # deixando os botões originais intactos.
            await query.message.reply_text(text=item["resposta"])
            logger.info(f"Resposta da FAQ por botão (nova mensagem): {item['pergunta']}")
            return
    logger.warning(f"ID de FAQ não encontrado para callback_data: {selected_faq_id}")
    # Se o ID não for encontrado, ainda podemos editar a mensagem de "opções"
    # para indicar o erro, mas manter os botões se houver outros.
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
        # Se você quer que o usuário continue no modo IA para várias perguntas,
        # remova ou comente a linha abaixo.
        context.user_data['using_ai'] = False
        logger.info(f"Modo IA desativado para o usuário {user_id}.")


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
    # Handler para saudações e texto livre que não são comandos
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    application.add_handler(MessageHandler(filters.COMMAND, unknown)) # Para comandos não reconhecidos

    # Inicializa a aplicação para processamento de webhook
    await application.initialize()
    # Adiciona o webhook explicitamente.
    # Certifique-se de que a URL do seu Render esteja configurada para /api/telegram/webhook
    webhook_url = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if webhook_url:
        full_webhook_url = f"https://{webhook_url}/api/telegram/webhook"
        await application.bot.set_webhook(url=full_webhook_url)
        logger.info(f"Webhook definido para: {full_webhook_url}")
    else:
        logger.warning("RENDER_EXTERNAL_HOSTNAME não definido. Webhook não será configurado automaticamente.")


@flask_app.route('/api/telegram/webhook', methods=['POST'])
async def webhook_handler():
    logger.info("Webhook endpoint hit! (Recebendo requisição do Telegram)")
    if request.method == "POST":
        global application # Garante que estamos usando a variável global
        if application is None: # Verifica se a aplicação foi criada (deve ter sido no setup_bot())
            logger.error("A aplicação do Telegram não está inicializada. Tentando configurar novamente.")
            try:
                await setup_bot() # Tenta configurar se não estiver inicializada
                logger.info("Aplicação Telegram re-inicializada no webhook.")
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
# Isso será executado quando o módulo for importado pelo Gunicorn
try:
    # Cria um novo loop de eventos e executa setup_bot()
    # Isso garante que setup_bot() seja chamado uma vez quando o Gunicorn carrega o app.
    # É importante usar um novo loop aqui para evitar conflitos se houver um loop existente.
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # Se um loop já estiver rodando (ex: em ambientes de teste ou IDEs),
        # agendamos a tarefa. No Gunicorn/Render, isso não deve ser um problema.
        loop.create_task(setup_bot())
        logger.info("Agendando setup_bot para o loop de eventos existente.")
    else:
        loop.run_until_complete(setup_bot())
        logger.info("Bot Telegram configurado na inicialização do módulo (novo loop).")
except RuntimeError as e:
    # Catch the "Event loop is already running" in specific scenarios,
    # and just log it, assuming it will be handled by the webhook.
    if "Event loop is already running" in str(e):
        logger.warning("RuntimeError: Event loop is already running. "
                       "Bot setup will likely occur on the first webhook request.")
    else:
        logger.critical(f"ERRO FATAL NA CONFIGURAÇÃO INICIAL DO BOT: {e}", exc_info=True)
        raise # Re-raise para que o Render saiba que a inicialização falhou
except Exception as e:
    logger.critical(f"ERRO FATAL NA CONFIGURAÇÃO INICIAL DO BOT: {e}", exc_info=True)
    raise # Re-raise para que o Render saiba que a inicialização falhou

# O `if __name__ == '__main__'` não é estritamente necessário para o Render/Gunicorn
# mas pode ser útil para testes locais.
if __name__ == '__main__':
    # Esta parte é mais para execução local (python bot.py)
    # No Render, o Gunicorn executa o `flask_app` diretamente.
    # A inicialização do bot já foi feita fora deste bloco `if __name__ == '__main__'`
    # para garantir que ocorra quando o Gunicorn carrega o módulo.
    # Para testar localmente, você pode querer adicionar:
    # flask_app.run(debug=True, port=5000)
    pass
