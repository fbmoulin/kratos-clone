"""WSGI entrypoint for production (Gunicorn).

`gunicorn wsgi:app` — invokes the factory so janitor + boot cleanup run.

For tests: `from app import app, create_app, _reset_state` and call
`create_app(start_janitor=False, run_boot_cleanup=False)` for a side-effect-free
instance.
"""

from app import create_app

app = create_app()
