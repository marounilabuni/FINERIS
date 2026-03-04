from pathlib import Path


class Config:
    # --- Paths ---
    BASE_DIR = Path(__file__).parent
    STORAGE_DIR = BASE_DIR / "storage"
    PORTFOLIO_FILE = STORAGE_DIR / "portfolio.json"
    USER_PROFILE_FILE = STORAGE_DIR / "user_profile.json"
    SEEN_NEWS_FILE = STORAGE_DIR / "seen_news.json"
    NOTIFICATIONS_FILE = STORAGE_DIR / "notifications.log"

    # --- LLM ---
    MODEL = "claude-sonnet-4-6"
    HAIKU_MODEL = "claude-haiku-4-5-20251001"
    TEMPERATURE = 0.2
    AVAILABLE_MODELS: dict[str, str] = {
        "claude-haiku-4-5-20251001": "Haiku 4.5 (Fast)",
        "claude-sonnet-4-6":        "Sonnet 4.6 (Default)",
        "claude-opus-4-6":          "Opus 4.6 (Best)",
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
