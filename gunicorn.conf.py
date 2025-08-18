"""Gunicorn configuration for the Trade Signal Bot.

This configuration starts a single worker and a single thread to ensure
that the Flask application and the Telethon client share a single
process.  Using additional workers or threads with SQLite will lead to
`database is locked` errors because SQLite allows only one writer at a
time.  You should not modify these values unless you migrate to a
different database backend.
"""

import os

# Bind to the port provided by Render or default to 10000 for local testing.
bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"

# Use a single worker and a single thread.
workers = 1
threads = 1

# Worker class: sync (one request at a time per worker).  This avoids
# asynchronous context switching that could interfere with Telethon's event loop.
worker_class = "sync"

# Timeouts.  The bot needs enough time to start the Telethon client and
# establish a connection to Telegram.  Adjust as necessary.
timeout = 120
graceful_timeout = 30
keepalive = 30

# Log to stdout/stderr so Render captures the logs.
accesslog = "-"
errorlog = "-"

# Do not preload the app.  Preloading would cause the Telethon event loop
# to be created in the parent process instead of the worker.
preload_app = False