import logging
import os
import asyncio
import json
import threading
from flask import Flask, request, jsonify
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, CallbackQueryHandler, CommandHandler
from telegram.ext import ApplicationBuilder

# Para a fila com Redis
import redis
from rq import Queue, Worker
from rq.job import Job
from redis.exceptions import ConnectionError as RedisConnectionError # Importar o erro específico

# --- Configuração de Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Variáveis de Ambiente e Configurações ---
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
# REDIS_URL será automaticamente preenchido pelo Render. Fallback para desenvolvimento local.
# IMPORTANTE: Para testes locais, certifique-se de que o Redis esteja rodando em localhost:6379
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Verificação para garantir que o token foi carregado
if not TELEGRAM_BOT_TOKEN:
    logger.critical("ERRO CRÍTICO: A variável de ambiente 'BOT_TOKEN' não foi encontrada. Certifique-se de que está configurada no Render.")
    # Em um ambiente de produção, você pode querer parar a execução se o token for essencial.
    # raise ValueError("BOT_TOKEN não configurado. Impossível prosseguir.")

# Construção da URL do Webhook
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    WEBHOOK_URL = f"https://{RENDER_EXTERNAL_HOSTNAME}/api/telegram/webhook"
else:
    # Fallback para desenvolvimento local. Certifique-se de que esta URL seja acessível externamente se for para produção.
    # Para testes locais, esta URL precisa corresponder onde seu Flask estará rodando.
    WEBHOOK_URL = "http://localhost:5000/api/telegram/webhook"
    logger.warning(f"RENDER_EXTERNAL_HOSTNAME não encontrado. Usando fallback WEBHOOK_URL para desenvolvimento local: {WEBHOOK_URL}")

# --- Conexão ao Redis e Configuração da Fila RQ ---
redis_conn = None
q = None
try:
redis_conn = redis.from_url(REDIS_URL, ssl_cert_reqs=None)

# Teste de conexão simples
    redis_conn.ping()
    q = Queue(connection=redis_conn)
    logger.info(f"Conectado ao Redis em: {REDIS_URL}")
except RedisConnectionError as e: # Captura o erro específico de conexão do Redis
    logger.critical(f"ERRO CRÍTICO: Não foi possível conectar ao Redis em {REDIS_URL}. Verifique a URL e a disponibilidade do serviço Redis. Worker não poderá iniciar: {e}", exc_info=True)
    # `q` permanecerá None, e as rotas/funções verificarão isso.
except Exception as e:
    logger.critical(f"ERRO DESCONHECIDO ao conectar ao Redis: {e}", exc_info=True)


# --- Instância do Flask ---
flask_app = Flask(__name__)

# --- Dados do FAQ (mantido como está) ---
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

# --- Funções de Lógica do Bot (Assíncronas) ---
def buscar_faq(texto_usuario):
    matches = []
    texto_usuario_lower = texto_usuario.lower()
    for item in faq_data:
        # Verifica se alguma palavra-chave está contida no texto do usuário
        if any(palavra_chave in texto_usuario_lower for palavra_chave in item.get("palavras_chave", [])):
            matches.append(item)
    return matches

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
                # Fallback para a FAQ de "Não encontrei minha dúvida" (ID 54)
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
    await query.answer()  # Sempre responda ao callback_query

    faq_id = int(query.data)
    faq_item = next((item for item in faq_data if item["id"] == faq_id), None)

    try:
        if faq_item:
            # Usar edit_message_text para evitar enviar uma nova mensagem
            await query.edit_message_text(faq_item["resposta"], parse_mode='Markdown')
            logger.info(f"Botão de FAQ pressionado e resposta editada por {query.from_user.first_name}: ID {faq_id}")
        else:
            await query.edit_message_text("Desculpe, não consegui encontrar a resposta para esta opção.", parse_mode='Markdown')
            logger.warning(f"Botão de FAQ pressionado com ID inválido: {faq_id} por {query.from_user.first_name}")
    except Exception as e:
        logger.error(f"Erro ao processar callback de botão ou editar mensagem para {query.from_user.id}: {e}", exc_info=True)

# --- Setup do Application (global para o worker) ---
application = None
if TELEGRAM_BOT_TOKEN:
    # Use ApplicationBuilder para uma construção mais explícita
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    logger.info("Application do Telegram Bot construída e handlers adicionados.")
else:
    logger.critical("Não foi possível construir o aplicativo Telegram pois o token não foi carregado.")

# --- Funções de Processamento de Atualizações (RQ Worker) ---
# Esta função será enfileirada e executada pelo worker
async def process_telegram_update(update_json: dict):
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Não é possível processar a atualização: TOKEN do bot não está disponível.")
        return

    if not application:
        logger.critical("A aplicação do Telegram não foi inicializada. Impossível processar updates.")
        return

    try:
        # A instância do bot é necessária para o Update.de_json
        # É crucial que o bot_instance aqui seja criado dentro do contexto do worker
        # pois o Update.de_json precisa de um objeto Bot válido para operar.
        bot_instance = Bot(TELEGRAM_BOT_TOKEN)
        update = Update.de_json(update_json, bot_instance)
        logger.info(f"Processando update ID: {update.update_id} na fila do RQ.")
        await application.process_update(update)
        logger.info(f"Update ID: {update.update_id} processado com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao processar update {update_json.get('update_id', 'N/A')} na fila: {e}", exc_info=True)


# --- Rotas do Flask (Web Service) ---
@flask_app.route("/health", methods=["GET"])
def health_check():
    logger.info("Rota /health acessada.")
    # Adicionar uma verificação de saúde do Redis também
    if redis_conn: # Certifica-se de que a conexão não é None
        try:
            redis_conn.ping()
            logger.info("Health check: Conexão Redis OK.")
            return "OK - Redis Connected", 200
        except RedisConnectionError as e:
            logger.error(f"Health check falhou: Redis ConnectionError - {e}", exc_info=True)
            return "ERROR - Redis Disconnected", 500
    else:
        logger.error("Health check falhou: Objeto de conexão Redis é None. Possivelmente falha na inicialização.")
        return "ERROR - Redis Connection Not Initialized", 500

@flask_app.route("/api/telegram/webhook", methods=["POST"])
def telegram_webhook():
    logger.info("Webhook endpoint hit! (Recebendo requisição do Telegram)")
    if not q: # Verifica se a fila foi inicializada com sucesso
        logger.error("Requisição de webhook recebida, mas a fila do Redis não está disponível. Retornando 503.")
        return jsonify({"status": "error", "message": "Redis Queue not initialized"}), 503 # 503 Service Unavailable

    try:
        update_data = request.get_json(force=True)
        # Logar apenas o update_id ou uma parte para evitar logs muito grandes
        logger.info(f"Dados da atualização recebidos (ID: {update_data.get('update_id', 'N/A')}). Enfileirando...")

        # Enfileira a atualização para ser processada pelo worker
        # job_timeout deve ser adequado para o tempo máximo que um handler pode levar
        job = q.enqueue(process_telegram_update, update_data, job_timeout='5m')
        logger.info(f"Atualização enfileirada para o RQ. Job ID: {job.id}")

        return jsonify({"status": "ok", "job_id": job.id}), 200
    except Exception as e:
        logger.error(f"Erro ao enfileirar atualização do webhook: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

# --- Funções de Inicialização (para Procfile) ---

async def set_telegram_webhook_async():
    """Função assíncrona para configurar o webhook do Telegram."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Não é possível configurar o webhook: TOKEN do bot não está disponível.")
        return

    # Usamos o Bot diretamente para simplificar o ciclo de vida e evitar conflitos de Application
    bot_instance = Bot(TELEGRAM_BOT_TOKEN)

    try:
        webhook_info = await bot_instance.get_webhook_info()
        current_webhook_url = webhook_info.url

        if current_webhook_url != WEBHOOK_URL:
            logger.info(f"URL do webhook atual ({current_webhook_url}) é diferente da desejada ({WEBHOOK_URL}). Configurando...")
            await bot_instance.set_webhook(url=WEBHOOK_URL)
            logger.info(f"Webhook definido para: {WEBHOOK_URL}")
        else:
            logger.info("Webhook já está configurado corretamente. Nenhuma ação necessária.")
    except Exception as e:
        logger.error(f"Erro ao configurar webhook: {e}", exc_info=True)

def start_web_service():
    """
    Inicia o servidor Flask (via Gunicorn) e configura o webhook.
    Esta função é chamada pelo Procfile 'web:'.
    """
    logger.info("Iniciando setup do Web Service (Configuração de Webhook e Flask).")
    try:
        # Executa a função assíncrona de configuração do webhook em seu próprio loop de eventos.
        # Isso é executado ANTES do Gunicorn carregar e rodar a aplicação Flask.
        asyncio.run(set_telegram_webhook_async())
        logger.info("Configuração de webhook do Telegram concluída ou verificada com sucesso.")
    except Exception as e:
        logger.critical(f"ERRO CRÍTICO: Falha ao configurar o webhook na inicialização. Isso pode impedir o bot de receber mensagens: {e}", exc_info=True)

    logger.info("Servidor Flask pronto para ser iniciado pelo Gunicorn.")
    # flask_app.run() NÃO deve ser chamado aqui, pois o Gunicorn (do Procfile) fará isso.


def run_ptb_worker():
    """
    Inicia o worker RQ para processar as mensagens do Telegram.
    Esta função é chamada pelo Procfile 'worker:'.
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("Não foi possível iniciar o worker do Telegram: TOKEN do bot não está disponível.")
        return

    if not application:
        logger.critical("Não foi possível iniciar o worker do Telegram: Aplicação do Telegram não foi construída (possívelmente TOKEN ausente).")
        return

    if not q:
        logger.critical("Não foi possível iniciar o worker do Telegram: Fila do Redis não está disponível. Worker não pode iniciar.")
        return

    logger.info("Iniciando o worker RQ para processar updates do Telegram.")
    try:
        # O Worker precisa da conexão Redis que foi estabelecida globalmente.
        worker = Worker([q], connection=redis_conn)
        worker.work() # Isso inicia o loop do worker e bloqueia este processo
    except Exception as e:
        logger.critical(f"ERRO CRÍTICO no worker RQ: {e}", exc_info=True)


# --- Bloco de Execução Principal (para testes locais e entendimento do fluxo) ---
if __name__ == '__main__':
    logger.info("Executando bot.py no bloco __main__ (provavelmente para teste local).")
    # Para teste local:
    # 1. Certifique-se de ter um servidor Redis rodando localmente (ex: `docker run -p 6379:6379 redis`)
    # 2. Em um terminal, inicie o worker RQ:
    #    python -c "from bot import run_ptb_worker; run_ptb_worker()"
    # 3. Em *outro* terminal, inicie o servidor Flask (para o webhook):
    #    python -c "from bot import flask_app, start_web_service; start_web_service(); flask_app.run(host='0.0.0.0', port=5000, debug=True)"
    #    - `start_web_service()` configurará o webhook.
    #    - `flask_app.run()` iniciará o servidor web para receber os webhooks.
    # 4. **Importante para testes locais:** Você precisará de uma forma de expor seu `localhost:5000` para a internet
    #    (ex: ngrok, localtunnel) e configurar essa URL gerada como o webhook no BotFather do Telegram.

    logger.info("No ambiente Render, o Procfile irá chamar as funções `start_web_service` e `run_ptb_worker` separadamente.")
    logger.info("Certifique-se de que seu Procfile está configurado assim (ou similar):")
    logger.info("  web: gunicorn bot:flask_app --bind 0.0.0.0:$PORT --worker-class gevent --workers 2") # Ajuste --workers conforme sua necessidade
    logger.info("  worker: python -c \"from bot import run_ptb_worker; run_ptb_worker()\"")

    # Exemplo de como as funções seriam chamadas pelo Procfile no Render:
    # (Não descomente isto, é apenas para ilustrar o que o Procfile faz)
    # start_web_service()
    # flask_app.run(host='0.0.0.0', port=os.getenv("PORT", 5000)) # Gunicorn fará isso
    # run_ptb_worker()
