from typing import Literal

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from agents.base import BaseAgent
from config import Config
from tracing import record_step
from models.market import HoldingSnapshot, MarketEvent
from models.signals import GuardianSignal
from models.user import UserProfile


class _GuardianResponse(BaseModel):
    recommendation: Literal["HOLD", "SELL"]
    reasoning: str
    historical_context: str


class GuardianAgent(BaseAgent):

    def __init__(self, model: str = Config.MODEL) -> None:
        print(f"[GuardianAgent] Using model: {model}")
        self._llm = ChatOpenAI(
            model=model,
            temperature=Config.TEMPERATURE,
            base_url=Config.LLMOD_BASE_URL,
            api_key=Config.LLMOD_API_KEY,
        ).with_structured_output(_GuardianResponse).with_retry(stop_after_attempt=3)

    def run(
        self,
        event: MarketEvent,
        snapshot: HoldingSnapshot,
        profile: UserProfile,
        history: list[dict],
    ) -> GuardianSignal:
        prompt = self._build_prompt(event, snapshot, profile, history)
        response: _GuardianResponse = self._llm.invoke([HumanMessage(content=prompt)])  # type: ignore
        record_step(
            module="GuardianAgent",
            prompt={"content": prompt},
            response=response.model_dump() if hasattr(response, "model_dump") else response,  # type: ignore[union-attr]
        )
        return GuardianSignal(
            ticker=event.ticker,
            recommendation=response.recommendation,
            reasoning=response.reasoning,
            historical_context=response.historical_context,
            news_count=len(event.news),
        )

    def _build_prompt(
        self,
        event: MarketEvent,
        snapshot: HoldingSnapshot,
        profile: UserProfile,
        history: list[dict],
    ) -> str:
        news_text = "\n".join(
            f"- [{n.published_at.strftime('%Y-%m-%d %H:%M')}] {n.headline}: {n.summary}"
            for n in event.news
        )
        history_text = "\n".join(
            f"  {h['date']}: close={h['close']:.2f}, volume={h['volume']:.0f}"
            for h in history[-10:]
        )
        return f"""You are a defensive financial analyst protecting a {profile.risk_level}-risk investor's portfolio.

HOLDING: {snapshot.ticker}
- Quantity: {snapshot.quantity} shares
- Avg buy price: ${snapshot.avg_buy_price:.2f}
- Current price: ${snapshot.current_price:.2f}
- Current value: ${snapshot.current_value:.2f}
- Unrealized PnL: ${snapshot.unrealized_pnl:.2f}
- Portfolio weight: {snapshot.portfolio_weight:.1%}

TODAY'S EVENT:
- Price change: {event.snapshot.change_pct:.1%}

RECENT NEWS:
{news_text}

PRICE HISTORY (last 10 days):
{history_text}

TASK: Based on the news, price action, and historical context, should the investor HOLD or SELL?
Bias toward HOLD unless the situation is fundamentally broken. The investor is {profile.risk_level}-risk."""
