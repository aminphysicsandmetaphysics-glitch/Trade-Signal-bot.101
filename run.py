import os
import asyncio
import threading
from flask import Flask
from signal_bot.web import setup_routes
from signal_bot.worker import start_worker

app = Flask(__name__)
setup_routes(app)

def _run_worker():
    asyncio.run(start_worker())

threading.Thread(target=_run_worker, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)
