from agents.scout import ScoutAgent
from agents.supervisor import SupervisorAgent
from config import Config
from data.market import YFinanceSource
from models.signals import ScoutSignal
from models.user import UserProfile


class ScoutSystem:
    """Wires ScoutAgent with its data source. Runnable standalone."""

    def __init__(self, model: str = Config.MODEL) -> None:
        self._agent = ScoutAgent(model=model)
        self._supervisor = SupervisorAgent(model=model)
        self._data = YFinanceSource()

    def run(
        self,
        ticker: str,
        profile: UserProfile,
        budget: float,
        portfolio_weights: dict[str, float],
    ) -> ScoutSignal:
        history = self._data.get_history(ticker, period=f"{Config.MOMENTUM_WINDOW_DAYS}d")
        fundamentals = self._data.get_fundamentals(ticker)
        news_items = self._data.get_news(ticker)

        news_summary = self._build_news_summary(news_items)

        return self._agent.run(
            ticker=ticker,
            profile=profile,
            budget=budget,
            portfolio_weights=portfolio_weights,
            history=history,
            fundamentals=fundamentals,
            news_summary=news_summary,
            news_count=min(len(news_items), 5),
        )

    def _build_news_summary(self, news_items: list) -> str:
        if not news_items:
            return "No recent news."
        items = news_items[:5]
        sentiments = self._supervisor.classify_news_sentiments(items)
        lines = [
            f"- [{sentiment}] {item.headline}: {item.summary}"
            for item, sentiment in zip(items, sentiments)
        ]
        return "\n".join(lines)
