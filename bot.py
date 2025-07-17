import os
import json
import logging
import ssl  # NOVO: Importa o módulo ssl
import sys
from flask import Flask, request, abort
from redis import Redis
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, MessageHandler, filters, Application
from rq import Queue
import asyncio

# --- Configuração de Logging (Melhorado) ---
# Nível de log para DEBUG durante o desenvolvimento, INFO para produção
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL)
)
logger = logging.getLogger(__name__)

# --- Variáveis de Ambiente e Configurações ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") # Usado para o Gemini, se implementado
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
REDIS_URL = os.getenv("REDIS_URL")

# --- Chat ID do Administrador (para alertas) ---
# SUBSTITUA 'SEU_CHAT_ID_DO_ADMIN' PELO SEU ID DE CHAT REAL!
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", SEU_CHAT_ID_DO_ADMIN)) # Certifique-se que SEU_CHAT_ID_DO_ADMIN é um número ou setado no Render

# SUBSTITUA 'SEU_NOME_DE_USUARIO_DO_BOT' PELO NOME DE USUÁRIO REAL DO SEU BOT!
BOT_USERNAME = os.getenv("BOT_USERNAME", 'SEU_NOME_DE_USUARIO_DO_BOT')

# --- Verificações de Variáveis Essenciais ---
if not BOT_TOKEN:
    logger.critical("ERRO CRÍTICO: A variável de ambiente 'BOT_TOKEN' NÃO foi encontrada. O bot não pode iniciar.")
    sys.exit(1)

if not WEBHOOK_URL:
    logger.warning("AVISO: A variável de ambiente 'WEBHOOK_URL' não foi encontrada. O bot pode não funcionar corretamente em produção. Certifique-se de que está configurada no Render.")

if not REDIS_URL:
    logger.critical("ERRO CRÍTICO: A variável de ambiente 'REDIS_URL' NÃO foi encontrada. O bot não pode iniciar sem o Redis.")
    sys.exit(1)

# --- Conexão Redis e RQ (Melhorado) ---
try:
    # NOVO: Adiciona ssl_cert_reqs para lidar com conexões SSL
    redis_conn = Redis.from_url(REDIS_URL, ssl_cert_reqs=ssl.CERT_NONE)
    redis_conn.ping() # Testa a conexão
    queue = Queue(connection=redis_conn)
    logger.info("Conexão Redis estabelecida com sucesso!")
except Exception as e:
    logger.critical(f"ERRO CRÍTICO: Não foi possível conectar ao Redis em {REDIS_URL}. Verifique a URL e a disponibilidade do serviço Redis. O bot não poderá iniciar: {e}.")
    sys.exit(1) # Sai do programa se não conseguir conectar ao Redis

# --- Carregamento da Base de Conhecimento (FAQ) ---
FAQ_DATA = {}
script_dir = os.path.dirname(os.path.abspath(__file__))
faq_path = os.path.join(script_dir, 'base_conhecimento', 'faq_data.json')

logger.info(f"Caminho absoluto do diretório do script: {script_dir}")
logger.info(f"Tentando carregar faq_data.json de: {faq_path}")

try:
    with open(faq_path, 'r', encoding='utf-8') as f:
        FAQ_DATA = json.load(f)
    logger.info("faq_data.json carregado com sucesso!")
except FileNotFoundError:
    logger.critical(f"ERRO CRÍTICO: O arquivo faq_data.json NÃO foi encontrado em {faq_path}. Verifique se o arquivo foi commitado e enviado para o repositório Git na pasta 'base_conhecimento'.")
    sys.exit(1) # Aborta o deploy se o arquivo não for encontrado
except json.JSONDecodeError as e:
    logger.critical(f"ERRO CRÍTICO: Erro ao decodificar JSON em {faq_path}. Verifique a formatação do JSON: {e}")
    sys.exit(1)
except Exception as e:
    logger.critical(f"ERRO CRÍTICO: Um erro inesperado ocorreu ao carregar faq_data.json: {e}")
    sys.exit(1)

# --- Instância do Flask App ---
app = Flask(__name__)

# --- Funções do Bot ---
def find_answer(question):
    question_lower = question.lower()
    best_match = None
    best_score = 0

    for key, item in FAQ_DATA.items():
        keywords = [kw.lower() for kw in item.get('palavras_chave', [])]
        for keyword in keywords:
            if keyword in question_lower:
                if len(keyword) > best_score: # Prioriza keywords mais longas ou mais específicas
                    best_score = len(keyword)
                    best_match = item['resposta']
                # Se múltiplas palavras-chave, pode somar scores ou usar outra lógica
                break # Para evitar contar a mesma pergunta várias vezes com a mesma keyword

    if best_match:
        return best_match
    return "Desculpe, não entendi sua pergunta. Poderia reformulá-la?"


async def start_command(update: Update, context):
    logger.info(f"Comando /start recebido de {update.effective_user.id}")
    await update.message.reply_text("Olá! Eu sou o Bot Chopp. Como posso ajudar você hoje?")


async def help_command(update: Update, context):
    logger.info(f"Comando /help recebido de {update.effective_user.id}")
    await update.message.reply_text("Posso responder perguntas sobre nosso chopp, horários de funcionamento e mais. Basta perguntar!")

async def handle_message(update: Update, context):
    user_message = update.message.text
    user_id = update.effective_user.id
    logger.info(f"Mensagem de {user_id}: {user_message}")

    # Ignorar mensagens de canal ou outros tipos não-privados que não sejam comandos específicos
    if update.message.chat.type != 'private' and not user_message.startswith('/'):
        # Verifica se o bot foi mencionado em um grupo
        if BOT_USERNAME.lower() in user_message.lower():
            response_text = find_answer(user_message.replace(f"@{BOT_USERNAME}", "").strip())
            await update.message.reply_text(response_text)
            return
        else:
            return # Ignora mensagens de grupo que não mencionam o bot

    response = find_answer(user_message)
    await update.message.reply_text(response)


# --- Envio de Mensagem para o Admin (Exemplo de uso futuro) ---
async def send_admin_message(message: str):
    bot = Bot(token=BOT_TOKEN)
    try:
        await bot.send_message(chat_id=ADMIN_CHAT_ID, text=message)
        logger.info(f"Mensagem de admin enviada: {message}")
    except Exception as e:
        logger.error(f"Falha ao enviar mensagem para o admin {ADMIN_CHAT_ID}: {e}")

# --- Configuração do Application do PTB (para o Webhook) ---
application = Application.builder().token(BOT_TOKEN).build()

# Adiciona os handlers
application.add_handler(MessageHandler(filters.COMMAND, start_command)) # Trata /start e /help
application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)) # Trata mensagens de texto que não são comandos

# --- Rotas do Flask para o Webhook ---
@app.route('/webhook', methods=['POST'])
async def webhook():
    if not BOT_TOKEN:
        logger.error("Webhook recebido, mas BOT_TOKEN não está configurado.")
        abort(500) # Internal Server Error se o token não estiver presente

    # Cria uma nova instância do bot para processar a atualização
    bot_instance = Bot(token=BOT_TOKEN)
    update_data = request.get_json()

    if not update_data:
        logger.warning("Webhook recebido sem dados JSON.")
        abort(400) # Bad Request

    update = Update.de_json(update_data, bot_instance)
    logger.debug(f"Webhook: Recebida atualização - {update.update_id}")

    # Processa a atualização de forma assíncrona
    # A maneira mais robusta para ambientes de produção é colocar isso em uma fila (RQ)
    # ou usar `await application.process_update(update)` se o Flask app for async.
    # Por enquanto, vamos processar diretamente para depuração.
    try:
        # ATENÇÃO: Se o volume de mensagens for muito alto, esta linha pode causar timeouts no Render.
        # Nesses casos, o uso de RQ (com o worker separado) é essencial.
        await application.process_update(update)
    except Exception as e:
        logger.error(f"Erro ao processar atualização do Telegram: {e}")
        # Envia para o admin em caso de erro crítico no processamento de uma atualização
        # asyncio.create_task(send_admin_message(f"Erro crítico no bot ao processar atualização: {e}"))
        abort(500) # Erro interno

    return 'ok'

@app.route('/')
def hello_world():
    return 'Bot is running!'

# --- Configuração e Início do Webhook ---
# Esta função será chamada pelo Gunicorn quando o bot iniciar
# Ela configura o webhook no Telegram
async def setup_webhook():
    logger.info(f"Configurando webhook para: {WEBHOOK_URL}")
    bot = Bot(token=BOT_TOKEN)
    try:
        await bot.set_webhook(url=WEBHOOK_URL, allowed_updates=["message"])
        logger.info("Webhook configurado com sucesso!")
        # Envia uma mensagem para o admin quando o bot inicia com sucesso
        asyncio.create_task(send_admin_message(f"Bot '{BOT_USERNAME}' iniciado e webhook configurado com sucesso no Render!"))
    except Exception as e:
        logger.critical(f"ERRO CRÍTICO: Falha ao configurar o webhook no Telegram: {e}")
        asyncio.create_task(send_admin_message(f"ERRO CRÍTICO: Bot '{BOT_USERNAME}' falhou ao configurar o webhook: {e}"))
        sys.exit(1) # Sai se não conseguir configurar o webhook

# Adiciona o setup_webhook para ser executado quando o aplicativo Flask é carregado
# Nota: Com Gunicorn, isso pode ser um pouco tricky, pois cada worker pode tentar configurar.
# Uma forma mais robusta é ter um script de pre-deploy ou um worker de startup dedicado.
# Para simplicidade, vamos tentar executá-lo no início do worker.
# Mas a rota '/' ou qualquer outra pode ser acessada para disparar.
# Com o gunicorn e uvicorn worker, a forma mais garantida é garantir que esta parte rode apenas uma vez.
# Como alternativa, podemos chamar isso de dentro da função `hello_world` ou em uma rota de "health check"
# que seja acessada uma vez após o deploy.
# Para este setup simples, vamos deixar que o bot tente configurar o webhook no Flask app boot.
# O problema é que Flask não é realmente async, então o setup_webhook precisa ser await-able
# e rodar em um loop de evento. O gunicorn/uvicorn lida com o app, não com handlers de startup.
# A melhor prática é ter o `worker.py` fazendo isso, ou um "pre-deploy command" no Render.

# Para fins de teste inicial e depuração, podemos forçar a execução ao iniciar a aplicação.
# O `application.run_webhook()` é para o modo de polling, não para o Flask + Gunicorn.
# Para webhook, o PTB apenas espera que a rota POST seja chamada.
# A configuração do webhook em si deve ser feita via bot.set_webhook().
# Uma boa prática seria um script separado ou um pré-deploy command no Render.

# Por enquanto, se você já tem um worker.py configurado para fazer isso, o bot.py não precisa.
# Se não, vamos adicionar uma forma de garantir que o webhook seja configurado.
# A maneira mais direta é colocar essa chamada para setup_webhook no worker.py (no serviço de background)
# ou fazer um POST para a rota '/set_webhook' que chamaria o setup_webhook().

# Para simplificar aqui e garantir que o webhook seja configurado se você não tem um worker.py dedicado a isso:
@app.route('/set_webhook', methods=['GET'])
async def set_webhook_route():
    try:
        await setup_webhook()
        return 'Webhook setup initiated successfully!'
    except Exception as e:
        logger.error(f"Erro ao iniciar setup do webhook pela rota: {e}")
        return f"Erro ao iniciar setup do webhook: {e}", 500

# Se você não tem um worker separado para configurar o webhook:
# Você pode chamar `set_webhook_route` manualmente uma vez após o deploy (acessando a URL /set_webhook).
# Ou, de forma mais automática, mas menos robusta (pode rodar múltiplas vezes com Gunicorn):
# asyncio.create_task(setup_webhook()) # Isso seria para um bot que roda em um único processo

# Com o setup atual, você tem um worker.py que deve lidar com filas RQ.
# O setup do webhook precisa ser feito por um bot.set_webhook()
# Isso geralmente é feito fora do loop principal do bot, talvez uma única vez
# por um script de setup ou pelo worker.

# Vou assumir que você tem um worker.py que pode lidar com o setup do webhook
# ou que você irá acessar a rota `/set_webhook` uma vez após o deploy.
# Caso contrário, o bot.py vai rodar, mas o Telegram não saberá para onde enviar as mensagens.


# A execução principal da aplicação Flask
if __name__ == '__main__':
    # Em produção com Gunicorn, o Gunicorn que inicia o app Flask.
    # No desenvolvimento local, você pode usar:
    # app.run(debug=True, port=os.getenv("PORT", 5000))

    # Para garantir que o webhook seja configurado *apenas uma vez* no Render:
    # Uma abordagem mais robusta para o set_webhook é ter um script separado
    # ou usar o `rq worker` para enfileirar uma tarefa de set_webhook.
    # Com Gunicorn, cada worker pode tentar fazer isso, o que é ineficiente.

    # POR SEGURANÇA E ROBUSTEZ:
    # A função `setup_webhook` deve ser chamada APENAS UMA VEZ
    # preferencialmente por um serviço separado (como o `worker.py` via RQ),
    # ou como um "Pre-Deploy Command" no Render se ele puder rodar tarefas assíncronas.
    # Para este setup que temos, o `worker.py` é o lugar ideal para agendar isso.

    # Se você ainda não tem o worker.py fazendo o set_webhook,
    # considere adicionar uma tarefa RQ para isso.
    # Por exemplo, no worker.py:
    # from bot import setup_webhook
    # q = Queue(connection=redis_conn)
    # q.enqueue(setup_webhook) # Isso enfileira a tarefa para ser executada pelo worker

    # Se você não tem um worker separado para isso, então o bot vai rodar,
    # mas o webhook não será configurado automaticamente no Telegram
    # a menos que você acesse a rota /set_webhook manualmente após o deploy.

    # Para o Render/Gunicorn, a porta é fornecida pela variável de ambiente $PORT
    port = int(os.getenv("PORT", 5000))
    # Gunicorn já cuida de iniciar a aplicação.
    # Esta parte do código (if __name__ == '__main__') só rodaria se você executasse
    # python bot.py diretamente, sem Gunicorn.
    # Não há necessidade de app.run() aqui com o Gunicorn.
    pass # Deixa vazio, Gunicorn cuida do start.
