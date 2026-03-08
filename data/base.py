from abc import ABC, abstractmethod

from models.market import NewsItem, StockSnapshot


class BaseDataSource(ABC):

    @abstractmethod
    def resolve_ticker(self, raw: str) -> str:
        pass

    @abstractmethod
    def get_price(self, ticker: str) -> float:
        pass

    @abstractmethod
    def get_snapshot(self, ticker: str) -> StockSnapshot:
        pass

    @abstractmethod
    def get_news(self, ticker: str) -> list[NewsItem]:
        pass

    @abstractmethod
    def get_history(self, ticker: str, period: str) -> list[dict]:
        pass

    @abstractmethod
    def get_fundamentals(self, ticker: str) -> dict:
        pass
