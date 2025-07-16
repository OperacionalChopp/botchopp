web: python -c "from bot import start_web_service; start_web_service()" && gunicorn bot:flask_app --bind 0.0.0.0:$PORT
worker: python -c "from bot import run_ptb_worker; run_ptb_worker()"
