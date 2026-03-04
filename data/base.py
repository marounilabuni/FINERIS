from abc import ABC, abstractmethod


class BaseDataSource(ABC):

    @abstractmethod
    def get_price(self, ticker: str) -> float:
        pass

    @abstractmethod
    def get_news(self, ticker: str) -> list[dict]:
        pass

    @abstractmethod
    def get_history(self, ticker: str, period: str) -> list[dict]:
        pass

    @abstractmethod
    def get_fundamentals(self, ticker: str) -> dict:
        pass
