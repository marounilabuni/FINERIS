import os
from pathlib import Path
from pydantic import SecretStr


class Config:
    # --- Paths ---
    BASE_DIR = Path(__file__).parent
    STORAGE_DIR = BASE_DIR / "storage"
    PORTFOLIO_FILE = STORAGE_DIR / "portfolio.json"
    USER_PROFILE_FILE = STORAGE_DIR / "user_profile.json"
    SEEN_NEWS_FILE = STORAGE_DIR / "seen_news.json"
    NOTIFICATIONS_FILE = STORAGE_DIR / "notifications.log"

    # --- LLM ---
    MODEL = "RPRTHPB-gpt-5-mini"
    HAIKU_MODEL = "RPRTHPB-gpt-5-mini"
    TEMPERATURE = 1
    LLMOD_BASE_URL = "https://api.llmod.ai/v1"
    LLMOD_API_KEY: SecretStr = SecretStr(os.getenv("LLMOD_API_KEY", ""))
    AVAILABLE_MODELS: dict[str, str] = {
        "RPRTHPB-gpt-5-mini": "LLMod GPT-5 Mini",
    }

    # --- Guardian ---
    DROP_THRESHOLDS = {"low": 0.02, "medium": 0.03, "high": 0.05}
    COOLDOWN_HOURS = 0 # 4

    # --- Scout ---
    MOMENTUM_WINDOW_DAYS = 30
    CANDLE_WINDOW = 14

    # --- News Polling ---
    NEWS_POLL_INTERVAL_MINUTES = 1 # 30
    FILTER_SEEN_NEWS = False  # True = skip already-seen news (production); False = always process all news (demo/testing)
