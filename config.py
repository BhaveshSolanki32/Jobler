import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "user_config.json"


def get_config() -> dict:
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    cfg["_env"] = {
        "openrouter_api_key": os.getenv("OPENROUTER_API_KEY", ""),
        "capmonster_api_key": os.getenv("CAPMONSTER_API_KEY", ""),
    }
    cfg["_base_dir"] = str(BASE_DIR)
    return cfg


def save_config(cfg: dict) -> None:
    clean = {k: v for k, v in cfg.items() if not k.startswith("_")}
    with open(CONFIG_PATH, "w") as f:
        json.dump(clean, f, indent=2)
