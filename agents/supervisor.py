from datetime import datetime
from typing import Literal

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from agents.base import BaseAgent
from config import Config
from tracing import record_step
from models.market import MarketEvent
from models.signals import GuardianSignal, Notification, ScoutSignal
from models.user import UserProfile


class _SentimentResponse(BaseModel):
    sentiments: list[Literal["POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"]]


class SupervisorAgent(BaseAgent):

    def __init__(self, model: str = Config.MODEL) -> None:
        print(f"[SupervisorAgent] Using model: {model}")
        self._llm = ChatOpenAI(
            model=model,
            temperature=Config.TEMPERATURE,
            base_url=Config.LLMOD_BASE_URL,
            api_key=Config.LLMOD_API_KEY,
        )
        self._sentiment_llm = ChatOpenAI(
            model=model,
            temperature=Config.TEMPERATURE,
            base_url=Config.LLMOD_BASE_URL,
            api_key=Config.LLMOD_API_KEY,
        ).with_structured_output(_SentimentResponse).with_retry(stop_after_attempt=3)

    def classify_news_sentiments(self, news_items: list) -> list[Literal["POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"]]:
        """One LLM call for all items. Returns POSITIVE/NEGATIVE/NEUTRAL per item."""
        if not news_items:
            return []
        items_text = "\n".join(
            f"{i + 1}. Headline: {item.headline}\n   Summary: {item.summary}"
            for i, item in enumerate(news_items)
        )
        prompt = (
            f"Classify the sentiment of each financial news item as POSITIVE, NEGATIVE, or NEUTRAL.\n\n"
            f"{items_text}"
        )
        response: _SentimentResponse = self._sentiment_llm.invoke([HumanMessage(content=prompt)])  # type: ignore
        record_step(
            module="Supervisor.classify_news_sentiments",
            prompt={"content": prompt},
            response=response.model_dump() if hasattr(response, "model_dump") else response,  # type: ignore[union-attr]
        )
        return response.sentiments  # type: ignore[return-value]

    def should_trigger_guardian(
        self,
        event: MarketEvent,
        profile: UserProfile,
    ) -> bool:
        threshold = Config.DROP_THRESHOLDS[profile.risk_level]
        price_drop = event.snapshot.change_pct <= -threshold
        negative_news = False
        if event.news:
            sentiments = self.classify_news_sentiments(event.news)
            negative_news = "NEGATIVE" in sentiments
        return price_drop or negative_news

    def synthesize(
        self,
        guardian_signals: list[GuardianSignal],
        scout_signals: list[ScoutSignal],
    ) -> list[Notification]:
        notifications = []

        for signal in guardian_signals:
            level = "ACTION" if signal.recommendation == "SELL" else "WARNING"
            notifications.append(Notification(
                timestamp=datetime.now(),
                level=level,
                agent="Guardian",
                message=(
                    f"[{signal.ticker}] {signal.recommendation}:\n{signal.reasoning} "
                    f"\n| Historical: {signal.historical_context}"
                    f"\n| News analyzed: {signal.news_count}"
                ),
            ))

        for signal in scout_signals:
            level = "ACTION" if signal.recommendation == "BUY" else "INFO"  # PASS → INFO
            notifications.append(Notification(
                timestamp=datetime.now(),
                level=level,
                agent="Scout",
                message=(
                    f"[{signal.ticker}] {signal.recommendation}:\n{signal.reasoning} "
                    f"\n| Confidence: {signal.confidence}"
                    f"\n| Momentum: {signal.momentum_score:.1%}"
                    f"\n| News analyzed: {signal.news_count}"
                ),
            ))

        return notifications

    def run(self, **kwargs) -> list[Notification]:
        # Supervisor orchestration lives in FinerisSystem (LangGraph).
        # This method is a passthrough for standalone use.
        guardian_signals = kwargs.get("guardian_signals", [])
        scout_signals = kwargs.get("scout_signals", [])
        return self.synthesize(guardian_signals, scout_signals)
