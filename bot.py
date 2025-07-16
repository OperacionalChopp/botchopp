import logging
import os
from flask import Flask, request, jsonify
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, CallbackQueryHandler, CommandHandler
import asyncio
import json
import threading

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Seu TOKEN do Bot do Telegram
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")

# Verificação para garantir que o token foi carregado
if not TELEGRAM_BOT_TOKEN:
    logger.error("ERRO: A variável de ambiente 'BOT_TOKEN' não foi encontrada. Certifique-se de que está configurada no Render.")

WEBHOOK_URL = "https://botchopp.onrender.com/api/telegram/webhook" # Seu webhook do Render.com

# Instância do Flask
flask_app = Flask(__name__)

# Dados do FAQ (exemplo simplificado, você carregaria do seu JSON)
faq_data = [
    {
        "id": 1,
        "pergunta": "Mensagem de boas-vindas",
        "resposta": "Bem-vindo ao nosso serviço!",
        "palavras_chave": ["boas-vindas", "oi", "olá", "começar"]
    },
    {
        "id": 2,
        "pergunta": "Como saber quantos litros de chope preciso para o meu evento?",
        "resposta": "Para estimar a quantidade de chopp, considere 1,5 a 2 litros por pessoa para eventos de 4 horas.",
        "palavras_chave": ["litros", "quantidade", "evento", "chope", "cerveja"]
    },
    {
        "id": 3,
        "pergunta": "Qual é o horário de atendimento de vocês?",
        "resposta": "Nosso horário de atendimento é de segunda a sexta, das 9h às 18h.",
        "palavras_chave": ["horário", "atendimento", "abertura", "funciona"]
    },
    {
        "id": 53,
        "pergunta": "Como funciona a coleta/recolha do equipamento (chopeira, barril)?",
        "resposta": (
            "⚠️ AVISO INFORMATIVO — RECOLHA DO MATERIAL COMODATADO\n\n"
            "Este informativo orienta a coleta dos materiais (chopeira, barril, etc.) de acordo com a rota estabelecida durante o horário comercial.\n\n"
            "**CRITÉRIO:**\n"
            "As coletas seguem uma rota definida pela empresa para atender o maior número de clientes por região, podendo ser alterada semanalmente conforme a demanda.\n\n"
            "**HORÁRIO DE COLETA | ROTA:**\n"
            "Não realizamos coleta agendada. As coletas ocorrem por período:\n"
            "🕘 Manhã / Tarde\n"
            "📆 Segunda à Terça-feira — das 9h às 18h\n\n"
            "**REGIME DE EXCEÇÃO (ALTA DEMANDA):**\n"
            "Conforme critério da empresa, a coleta pode se estender para:\n"
            "📆 Quarta-feira — das 9h às 18h\n\n"
            "🚫 Não fazemos desvios de rota para atendimento personalizado.\n\n"
            "**COMUNICAÇÃO COM O CLIENTE:**\n"
            "- A empresa fará contato durante a rota para garantir a presença de um responsável.\n"
            "- Em caso de insucesso no contato, a rota será reavaliada e reprogramada até quarta-feira.\n"
            "- Se houver imprevistos, o cliente deve entrar em contato com a loja para entender a rota.\n"
            "- Caso a rota não atenda à necessidade, o cliente deve providenciar um substituto para liberar o material.\n\n"
            "**MULTA:**\n"
            "A partir de quinta-feira será cobrada taxa diária de R$100,00/dia pela não disponibilidade de recolha.\n\n"
            "**IMPORTANT!**\n"
            "- Todos os materiais devem estar prontos e em perfeita condição para recolha.\n"
            "- É necessário que haja um responsável no local para liberar o acesso.\n"
            "- A guarda dos materiais é responsabilidade do cliente, sujeito a cobrança em caso de perda ou dano.\n"
            "- Serão feitas fotos e filmagem dos materiais para respaldo.\n\n"
            "📦 Agradecemos a colaboração! Equipe de Logística — Chopp Brahma"
        ),
        "palavras_chave": [
            "coleta", "recolha", "recolhimento", "buscar", "retirada", "devolução",
            "horário coleta", "quando buscam", "rota coleta", "agendar coleta",
            "multa", "taxa", "material", "equipamento", "chopeira", "barril",
            "comodatado", "logística reversa", "responsabilidade", "aviso"
        ]
    },
    {
        "id": 54,
        "pergunta": "Não encontrei minha dúvida. Como posso ser atendido?",
        "resposta": (
            "Sentimos muito que você não tenha encontrado a resposta para sua dúvida em nosso FAQ. 😔\n\n"
            "Para um atendimento mais personalizado, por favor, clique no link abaixo para falar diretamente com nossa equipe via WhatsApp:\n\n"
            "📱 [**Clique aqui para falar conosco no WhatsApp!**](https://wa.me/556139717502) \n\n"
            "Ou, se preferir, você pode nos ligar no **(61) 3971-7502**.\n\n"
            "Estamos prontos para te ajudar!"
        ),
        "palavras_chave": [
            "não encontrei", "minha dúvida", "não achei", "falar com atendente", "contato",
            "suporte", "ajuda", "whatsapp", "fale conosco", "atendimento", "outro assunto",
            "telefone", "não consegui a resposta", "qual o numero", "falar com consultor",
            "não é isso que procuro", "preciso de mais ajuda", "não resolveu", "ainda tenho dúvidas",
            "falar com alguém", "atendimento humano", "chat", "direcionar", "onde ligo"
        ]
    },
    {
        "id": 55,
        "pergunta": "Quais dados preciso informar para fazer um cadastro ou pedido?",
        "resposta": (
            "Para que possamos processar seu pedido e emitir a Ordem de Serviço e Nota Fiscal, precisamos dos seguintes dados. Por favor, preencha-os com atenção:\n\n"
            "--- --- ---\n\n"
            "**DADOS DO EVENTO:**\n"
            "📅 *Data do evento:*\n"
            "⏰ *Horário do evento:*\n"
            "🗺️ *Endereço do evento:*\n"
            "✉️ *CEP do evento:*\n"
            "🗓️ *Data da entrega (do equipamento/chopp):*\n\n"
            "**DADOS PESSOAIS / EMPRESARIAIS:**\n"
            "📧 *E-mail:*\n"
            "👤 *Nome completo / Razão Social:*\n"
            "🏢 *Nome Fantasia (para CNPJ, se aplicável):*\n"
            "📞 *Telefone:*\n"
            "🆔 *CPF / CNPJ:*\n"
            "💳 *RG / Órgão Emissor (para CPF, se aplicável):*\n"
            "📝 *Inscrição Estadual (para CNPJ, se aplicável):*\n"
            "🏡 *Endereço da sua residência:*\n"
            "📮 *CEP da residência:*\n\n"
            "**DETALHES DO PEDIDO:**\n"
            "🍺 *Quantidade de Litros de Chopp:*\n"
            "💰 *Forma de Pagamento (Pix ou Cartão):*\n\n"
            "--- --- ---\n\n"
            "Agradecemos a sua colaboração! Assim que tivermos essas informações, agilizaremos seu pedido."
        ),
        "palavras_chave": [
            "cadastro", "pedido", "dados", "informar dados", "documentos", "o que preciso",
            "requisitos", "fazer pedido", "cadastro de cliente", "solicitar pedido",
            "informações para pedido", "lista de dados", "pedir chopp", "como pedir"
        ]
    }
]

# Função para buscar FAQ
def buscar_faq(texto_usuario):
    matches = []
    texto_usuario_lower = texto_usuario.lower()
    for item in faq_data:
        for palavra_chave in item.get("palavras_chave", []):
            if palavra_chave in texto_usuario_lower:
                matches.append(item)
                break
    return matches

# Handlers do Telegram Bot
async def start(update: Update, context):
    logger.info(f"Comando /start recebido de {update.effective_user.first_name} (ID: {update.effective_user.id})")
    try:
        await update.message.reply_text('Olá! Bem-vindo ao CHOPP Digital. Como posso te ajudar hoje?')
        logger.info(f"Resposta enviada para /start para {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Erro ao responder ao comando /start para {update.effective_user.id}: {e}", exc_info=True)

async def handle_message(update: Update, context):
    user_text = update.message.text
    if user_text:
        logger.info(f"Mensagem recebida de {update.effective_user.first_name} (ID: {update.effective_user.id}): {user_text}")
        logger.info(f"Buscando FAQ para o texto: '{user_text}'")

        try:
            found_faqs = buscar_faq(user_text)

            if found_faqs:
                faq_ids = [faq['id'] for faq in found_faqs]
                logger.info(f"FAQs encontradas: IDs {faq_ids}")

                if len(found_faqs) == 1:
                    faq_item = found_faqs[0]
                    await update.message.reply_text(faq_item["resposta"], parse_mode='Markdown')
                    logger.info(f"FAQ encontrada e enviada: ID {faq_item['id']} para {update.effective_user.id}")
                else:
                    keyboard = []
                    for faq_item in found_faqs:
                        keyboard.append([InlineKeyboardButton(faq_item["pergunta"], callback_data=str(faq_item["id"]))])
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.message.reply_text('Encontrei algumas opções. Qual delas você gostaria de saber?', reply_markup=reply_markup)
                    logger.info(f"Múltiplas FAQs encontradas. Oferecendo botões para: {[faq['pergunta'] for faq in found_faqs]} para {update.effective_user.id}")
            else:
                fallback_faq = next((item for item in faq_data if item["id"] == 54), None)
                if fallback_faq:
                    await update.message.reply_text(fallback_faq["resposta"], parse_mode='Markdown')
                    logger.info(f"Nenhuma FAQ encontrada. Enviando resposta de fallback (ID 54) para {update.effective_user.id}.")
                else:
                    await update.message.reply_text("Desculpe, não consegui encontrar uma resposta para sua pergunta. Por favor, tente reformular ou entre em contato diretamente.")
                    logger.info(f"Nenhuma FAQ encontrada e fallback (ID 54) não configurado para {update.effective_user.id}.")
        except Exception as e:
            logger.error(f"Erro ao processar mensagem ou enviar resposta para {update.effective_user.id}: {e}", exc_info=True)
    else:
        logger.warning(f"Mensagem recebida sem texto de {update.effective_user.first_name} (ID: {update.effective_user.id}). Ignorando.")


async def button_callback_handler(update: Update, context):
    query = update.callback_query
    await query.answer()

    faq_id = int(query.data)
    faq_item = next((item for item in faq_data if item["id"] == faq_id), None)

    try:
        if faq_item:
            await query.edit_message_text(faq_item["resposta"], parse_mode='Markdown')
            logger.info(f"Botão de FAQ pressionado e resposta enviada por {query.from_user.first_name}: ID {faq_id}")
        else:
            await query.edit_message_text("Desculpe, não consegui encontrar a resposta para esta opção.", parse_mode='Markdown')
            logger.warning(f"Botão de FAQ pressionado com ID inválido: {faq_id} por {query.from_user.first_name}")
    except Exception as e:
        logger.error(f"Erro ao processar callback de botão ou editar mensagem para {query.from_user.id}: {e}", exc_info=True)


# Setup do Application
application = None
if TELEGRAM_BOT_TOKEN:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    # Adicionar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
else:
    logger.critical("Não foi possível iniciar o aplicativo Telegram pois o token não foi carregado.")

# Rota para o health check do Render.com
@flask_app.route("/health", methods=["GET"])
def health_check():
    logger.info("Rota /health acessada.")
    return "OK", 200

# Rota do Webhook do Telegram
@flask_app.route("/api/telegram/webhook", methods=["POST"])
async def telegram_webhook():
    logger.info("Webhook endpoint hit! (Recebendo requisição do Telegram)")
    if TELEGRAM_BOT_TOKEN and application:
        try:
            bot_instance = Bot(TELEGRAM_BOT_TOKEN)
            update_data = request.get_json(force=True)
            logger.info(f"Dados da atualização recebidos: {json.dumps(update_data, indent=2)}")

            logger.info("Tentando colocar a atualização na fila da aplicação do Telegram.")
            # Coloca a atualização na fila para ser processada pela aplicação do PTB
            # Precisamos usar um loop de eventos para esta operação assíncrona
            if asyncio.get_event_loop().is_running():
                # Se já há um loop rodando (ex: Gunicorn com uvicorn workers), usa ele
                asyncio.create_task(application.update_queue.put(Update.de_json(update_data, bot_instance)))
            else:
                # Caso contrário, roda em um novo loop (menos comum em ambiente Gunicorn + Flask assíncrono)
                await application.update_queue.put(Update.de_json(update_data, bot_instance))

            logger.info("Atualização colocada na fila com sucesso.")

            return jsonify({"status": "ok"}), 200
        except Exception as e:
            logger.error(f"Erro ao processar atualização do webhook ou colocar na fila: {e}", exc_info=True)
            return jsonify({"status": "error", "message": str(e)}), 500
    else:
        if not TELEGRAM_BOT_TOKEN:
            logger.error("Requisição de webhook recebida, mas o TOKEN do bot não está configurado.")
            return jsonify({"status": "error", "message": "Bot token not configured"}), 500
        else: # application é None
            logger.error("Requisição de webhook recebida, mas a aplicação do Telegram não foi inicializada corretamente.")
            return jsonify({"status": "error", "message": "Telegram Application not initialized"}), 500

# Função para configurar o webhook na inicialização
async def set_webhook_on_startup():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Não é possível configurar o webhook: TOKEN do bot não está disponível.")
        return

    try:
        bot_instance = Bot(TELEGRAM_BOT_TOKEN)
        webhook_info = await bot_instance.get_webhook_info()
        current_webhook_url = webhook_info.url

        if current_webhook_url != WEBHOOK_URL:
            logger.info(f"URL do webhook atual ({current_webhook_url}) é diferente da desejada ({WEBHOOK_URL}). Configurando...")
            await bot_instance.set_webhook(url=WEBHOOK_URL)
            logger.info(f"Webhook definido para: {WEBHOOK_URL}")
        else:
            logger.info("Webhook já está configurado corretamente.")
    except Exception as e:
        logger.error(f"Erro ao configurar webhook: {e}", exc_info=True)

# Função para rodar a aplicação do python-telegram-bot em uma thread separada
def run_ptb_application():
    if application:
        # Pega ou cria um novo loop de eventos para esta thread.
        # Isso garante que a thread tem seu próprio ambiente assíncrono.
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        logger.info("Iniciando a execução da aplicação do python-telegram-bot (em thread separada com run_forever).")
        try:
            loop.run_until_complete(application.run_forever())
        except Exception as e:
            logger.error(f"ERRO CRÍTICO no loop de run_forever do PTB: {e}", exc_info=True)
        finally:
            # Garante que o loop é fechado quando a aplicação para
            if not loop.is_closed():
                loop.close()
        logger.info("Thread do python-telegram-bot encerrada.")
    else:
        logger.critical("Aplicação do python-telegram-bot não pode ser iniciada em thread separada pois o token não foi carregado.")


# Função a ser chamada pelo Procfile para iniciar o Flask
# e configurar o webhook do PTB
def run_bot_and_server():
    logger.info("Iniciando setup do ambiente para o bot e servidor Flask.")

    # 1. Configura o webhook uma vez ao iniciar o serviço
    try:
        # A configuração do webhook precisa ser executada no loop de eventos principal
        # se Gunicorn/Flask não tiver um loop já rodando.
        # No Render, o Gunicorn pode ter seu próprio loop. Vamos tentar isso:
        asyncio.run(set_webhook_on_startup())
        logger.info("Webhook configurado com sucesso (ou já estava configurado).")
    except RuntimeError:
        # Se um loop já estiver rodando (ex: por outro worker do Gunicorn ou Uvicorn),
        # agendamos a tarefa para ele.
        current_loop = asyncio.get_event_loop()
        if current_loop.is_running():
            current_loop.create_task(set_webhook_on_startup())
            logger.info("Webhook agendado para configuração no loop existente.")
        else:
            logger.error("Não foi possível configurar o webhook na inicialização: nenhum loop de eventos disponível e um RuntimeEror ocorreu.")
            raise # Re-lança o erro se for crítico

    # 2. Inicia o loop de eventos do python-telegram-bot em uma thread separada
    if application:
        ptb_thread = threading.Thread(target=run_ptb_application, daemon=True)
        ptb_thread.start()
        logger.info("Thread do python-telegram-bot iniciada para processar updates.")
    else:
        logger.critical("Não foi possível iniciar a thread do python-telegram-bot pois a aplicação não foi construída.")

    logger.info("Servidor Flask pronto para ser iniciado pelo Gunicorn.")

# Este bloco só é executado se o arquivo for rodado diretamente (para testes locais)
if __name__ == '__main__':
    logger.info("Executando bot.py no bloco __main__ (provavelmente para teste local).")
    # Para teste local SEM Gunicorn, você poderia usar:
    # asyncio.run(set_webhook_on_startup())
    # application.run_polling() # Para testar localmente via polling

    # No Render, o Procfile chamará run_bot_and_server() e o Gunicorn iniciará o Flask.
    # Portanto, não precisamos do flask_app.run() aqui.
    pass
