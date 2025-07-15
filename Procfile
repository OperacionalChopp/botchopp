#!/bin/bash

# Configura o webhook
# Este comando executa a função set_webhook_on_startup uma vez
python -c "import asyncio; from bot import set_webhook_on_startup; asyncio.run(set_webhook_on_startup())"

# Inicia o servidor Uvicorn
uvicorn bot:flask_app --host 0.0.0.0 --port $PORT --workers 1
