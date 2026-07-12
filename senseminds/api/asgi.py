"""ASGI entrypoint for uvicorn/gunicorn (``senseminds.api.asgi:app``).

Building the app does not open any connections; the composition root and DB pool
are created in the lifespan handler at startup.
"""

from senseminds.api.app import create_app

app = create_app()
