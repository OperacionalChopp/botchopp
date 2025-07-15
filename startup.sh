#!/bin/bash

# Configura o webhook do Telegram
python -c "import asyncio; from bot import set_webhook_on_startup; asyncio.run(set_webhook_on_startup())"

# Inicia o servidor Uvicorn
uvicorn bot:flask_app --host 0.0.0.0 --port $PORT --workers 1
