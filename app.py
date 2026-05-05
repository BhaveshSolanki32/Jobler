import logging
import os
from pathlib import Path

from flask import Flask

from ui.routes.config_routes import config_bp
from ui.routes.search_routes import search_bp
from ui.routes.apply_routes import apply_bp

# ── Logging setup ──────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "app.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="ui/templates",
        static_folder="ui/static",
    )
    app.secret_key = os.urandom(24)

    # Register blueprints
    app.register_blueprint(config_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(apply_bp)

    # Attach orchestrator as app attribute (one instance for the process lifetime)
    from core.orchestrator import Orchestrator
    app.orchestrator = Orchestrator()  # type: ignore[attr-defined]
    logger.info("Orchestrator initialised")

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", '127.0.0.1')

    logger.info(f"Starting Jobler on {host}:{port}")
    app.run(debug=False, host=host, port=port, threaded=True)
