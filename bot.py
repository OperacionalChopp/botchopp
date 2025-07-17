import logging
import os
import redis
from rq import Worker, Queue, Connection
from telegram import Bot
import asyncio

# --- Configuração de Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Variáveis de Ambiente ---
REDIS_URL = os.getenv("REDIS_URL")

if not REDIS_URL:
    logger.critical("ERRO CRÍTICO: 'REDIS_URL' não encontrada para o worker. Certifique-se de que está configurada.")
    exit(1)

# --- Conexão Redis para o Worker ---
try:
    conn = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=10)
    conn.ping()
    logger.info("Conexão Redis para o worker estabelecida.")
except Exception as e:
    logger.critical(f"ERRO CRÍTICO: Não foi possível conectar ao Redis para o worker: {e}")
    exit(1)

# --- Função que será executada pelo Worker ---
async def process_ai_query(job_data):
    """
    Processa a consulta de IA e envia a resposta de volta ao usuário do Telegram.
    Recebe um dicionário com os dados necessários.
    """
    user_id = job_data['user_id']
    chat_id = job_data['chat_id']
    message_text = job_data['message_text']
    thinking_message_id = job_data['thinking_message_id']
    telegram_bot_token = job_data['telegram_bot_token'] 

    logger.info(f"Worker recebeu query para AI: '{message_text}' para chat_id {chat_id}")

    bot = Bot(token=telegram_bot_token)

    try:
        # --- AQUI É ONDE VOCÊ INTEGRA SUA LÓGICA DE IA ---
        # Exemplo:
        # from your_ai_module import get_ai_response
        # response_from_ai = get_ai_response(message_text)
        
        # Simulação de processamento da IA
        await asyncio.sleep(5) # Simula um tempo de processamento
        response_from_ai = f"🤖 Resposta da IA para '{message_text}': Ainda estou aprendendo a responder a essa pergunta!"

        # Edita a mensagem "Pensando..." com a resposta final
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=thinking_message_id,
            text=response_from_ai
        )
        logger.info(f"Resposta da IA enviada para chat_id {chat_id}")

    except Exception as e:
        logger.error(f"Erro ao processar query de IA para chat_id {chat_id}: {e}")
        # Envia uma mensagem de erro ao usuário se algo der errado
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=thinking_message_id,
                text="Desculpe, tive um problema ao gerar sua resposta com IA. Por favor, tente novamente."
            )
        except Exception as edit_error:
            logger.error(f"Erro ao tentar editar a mensagem de erro no Telegram: {edit_error}")


# --- Início do RQ Worker ---
if __name__ == '__main__':
    logger.info("Iniciando RQ Worker...")
    # O worker escuta a fila 'default'. Se você usar outro nome de fila no bot.py, mude aqui.
    with Connection(conn):
        worker = Worker(list(Queue.all())) # Escuta todas as filas disponíveis
        worker.work()
