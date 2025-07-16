#!/bin/bash

# Configura o webhook do Telegram
python -c "import asyncio; from bot import set_webhook_on_startup; asyncio.run(set_webhook_on_startup())"

# Inicia o servidor Gunicorn (WSGI)
gunicorn bot:flask_app --bind 0.0.0.0:$PORT
