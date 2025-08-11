"""
Gunicorn configuration for running the Flask app.

This configuration uses a modest number of workers and threads to handle
concurrent requests without overwhelming free hosting resources.  It also
increases the default timeout to allow the Telegram bot to start before
Gunicorn considers the worker unresponsive.
"""

# Number of worker processes handling requests.  For free Render plan,
# two workers should suffice.
workers = 2

# Threads per worker.  Using a small number of threads improves I/O
# performance in asynchronous environments without consuming too much memory.
threads = 2

# Bind address.  Render exposes the application via $PORT environment
# variable, but gunicorn will be invoked by `startCommand` with this
# configuration and the environment variable will override the default port
# binding via the `PORT` env var.
bind = "0.0.0.0:5000"

# Logging configuration.  Direct logs to stdout/stderr for easy access in
# Render's log viewer.  The access log prints each HTTP request, and the
# error log captures exceptions.
accesslog = "-"
errorlog = "-"

# Allow more time for the worker to start and handle long‑running tasks
# related to Telegram connections.  Without this, Gunicorn may prematurely
# restart the worker if the bot startup takes longer than the default 30
# seconds.
timeout = 120
