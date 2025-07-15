import os
from flask import Flask, request, jsonify
import logging

# Configuração de logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

flask_app = Flask(__name__) # Use flask_app, pois seu Procfile aponta para ele

@flask_app.route('/')
def home():
    logger.info("Rota / acessada - Servidor de Teste Bot Chopp no ar!")
    return "Bot Chopp Teste - Servidor no ar!", 200

@flask_app.route('/api/telegram/webhook', methods=['POST'])
def webhook_teste():
    logger.info("Rota do Webhook acessada - Recebendo POST do Telegram")
    try:
        # Tenta pegar o JSON, mesmo que não seja um objeto de atualização completo
        data = request.get_json(silent=True) # silent=True para não levantar erro se não for JSON
        if data:
            logger.info(f"Dados JSON recebidos no webhook: {data}")
        else:
            logger.info("Requisição webhook recebida, mas sem JSON válido ou corpo vazio.")
        
        # O Telegram espera um status 200 OK
        return jsonify({"status": "recebido", "message": "OK"}), 200
    except Exception as e:
        logger.error(f"Erro inesperado ao processar requisição webhook de teste: {e}", exc_info=True)
        return jsonify({"status": "erro", "message": str(e)}), 500

# Esta parte não será executada no Render, apenas para testes locais se necessário.
if __name__ == '__main__':
    # PORT = int(os.environ.get("PORT", 5000))
    # flask_app.run(host="0.0.0.0", port=PORT, debug=True)
    pass
