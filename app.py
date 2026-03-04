"""FINERIS Flask web app."""
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from flask import Flask
from web.routes import register_routes

_BASE = Path(__file__).parent

def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(_BASE / "web/templates"),
        static_folder=str(_BASE / "web/static"),
    )
    app.secret_key = "fineris-dev-key"
    register_routes(app)
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
