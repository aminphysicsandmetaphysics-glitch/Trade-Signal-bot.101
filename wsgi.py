"""WSGI entrypoint for Gunicorn.

This simply exposes the Flask application as `app` so that Gunicorn
can discover it.  Do not modify this file unless you rename the
Flask application in `app.py`.
"""

from app import app as app  # noqa: F401  (Gunicorn expects `app`)