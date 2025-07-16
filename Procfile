web: python -c "import asyncio; from bot import set_webhook_on_startup; asyncio.run(set_webhook_on_startup())" && gunicorn bot:flask_app --bind 0.0.0.0:$PORT --workers 2
worker: python -c "from bot import run_ptb_worker; run_ptb_worker()"
