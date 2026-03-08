from typing import Literal

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from agents.base import BaseAgent
from config import Config
from tracing import record_step
from models.signals import ScoutSignal
from models.user import UserProfile


class _ScoutResponse(BaseModel):
    recommendation: Literal["BUY", "PASS"]
    confidence: Literal["low", "medium", "high"]
    reasoning: str


class ScoutAgent(BaseAgent):

    def __init__(self, model: str = Config.MODEL) -> None:
        print(f"[ScoutAgent] Using model: {model}")
        self._llm = ChatOpenAI(
            model=model,
            temperature=Config.TEMPERATURE,
            base_url=Config.LLMOD_BASE_URL,
            api_key=Config.LLMOD_API_KEY,
        ).with_structured_output(_ScoutResponse)

    def run(
        self,
        ticker: str,
        profile: UserProfile,
        budget: float,
        portfolio_weights: dict[str, float],
        history: list[dict],
        fundamentals: dict,
        news_summary: str,
        news_count: int = 0,
    ) -> ScoutSignal:
        momentum_score = self._compute_momentum(history)
        prompt = self._build_prompt(
            ticker, profile, budget, portfolio_weights,
            history, fundamentals, news_summary, momentum_score,
        )
        response: _ScoutResponse = self._llm.invoke([HumanMessage(content=prompt)])  # type: ignore
        record_step(
            module="ScoutAgent",
            prompt={"content": prompt},
            response=response.model_dump() if hasattr(response, "model_dump") else response,  # type: ignore[union-attr]
        )
        return ScoutSignal(
            ticker=ticker,
            recommendation=response.recommendation,
            confidence=response.confidence,
            reasoning=response.reasoning,
            momentum_score=momentum_score,
            news_count=news_count,
        )

    def _compute_momentum(self, history: list[dict]) -> float:
        if len(history) < 2:
            return 0.0
        first_close = history[0]["close"]
        last_close = history[-1]["close"]
        if first_close == 0:
            return 0.0
        return (last_close - first_close) / first_close

    def _build_prompt(
        self,
        ticker: str,
        profile: UserProfile,
        budget: float,
        portfolio_weights: dict[str, float],
        history: list[dict],
        fundamentals: dict,
        news_summary: str,
        momentum_score: float,
    ) -> str:
        candles_text = "\n".join(
            f"  {h['date']}: close={h['close']:.2f}, volume={h['volume']:.0f}"
            for h in history[-14:]
        )
        already_held = ticker in portfolio_weights
        current_weight = portfolio_weights.get(ticker, 0.0)

        return f"""You are an opportunistic financial analyst hunting growth investments for a {profile.risk_level}-risk investor.

CANDIDATE: {ticker}
- Momentum ({Config.MOMENTUM_WINDOW_DAYS}d): {momentum_score:.1%}
- Already held: {already_held} (current weight: {current_weight:.1%})
- Available budget: ${budget:.2f}

FUNDAMENTALS:
- P/E ratio: {fundamentals.get('pe_ratio', 'N/A')}
- Market cap: {fundamentals.get('market_cap', 'N/A')}
- Earnings growth: {fundamentals.get('earnings_growth', 'N/A')}
- Sector: {fundamentals.get('sector', 'N/A')}

RECENT NEWS:
{news_summary}

LAST {Config.CANDLE_WINDOW} CANDLES:
{candles_text}

TASK: Should the investor BUY or PASS on this stock?
Consider: momentum, fundamentals, news, available budget, and risk level ({profile.risk_level}).
Do not recommend BUY if budget is insufficient or if the stock is already over-concentrated (>30% weight).
Also rate your confidence in the decision as low, medium, or high."""
