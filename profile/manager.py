from config import Config
from models.user import RiskLevel, UserProfile
from utils import BaseJsonManager


class UserProfileManager(BaseJsonManager):
    def __init__(self) -> None:
        super().__init__(Config.USER_PROFILE_FILE)
        raw = self._load()
        self._data = raw or {"name": "", "risk_level": "medium", "watchlist": []}

    def get_profile(self) -> UserProfile:
        return UserProfile(**self._data)

    def set_name(self, name: str) -> None:
        self._data["name"] = name
        self._save(self._data)

    def set_risk_level(self, risk_level: RiskLevel) -> None:
        self._data["risk_level"] = risk_level
        self._save(self._data)

    def set_watchlist(self, tickers: list[str]) -> None:
        self._data["watchlist"] = [t.upper() for t in tickers]
        self._save(self._data)

    def add_to_watchlist(self, ticker: str) -> None:
        ticker = ticker.upper()
        if ticker not in self._data["watchlist"]:
            self._data["watchlist"].append(ticker)
            self._save(self._data)

    def remove_from_watchlist(self, ticker: str) -> None:
        ticker = ticker.upper()
        self._data["watchlist"] = [t for t in self._data["watchlist"] if t != ticker]
        self._save(self._data)
