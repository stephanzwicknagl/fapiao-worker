"""WSGI entry point — re-exports app from fapiao.web for gunicorn (app:app)."""
from fapiao.web import app  # noqa: F401
