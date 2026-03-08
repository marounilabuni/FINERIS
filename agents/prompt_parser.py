from typing import Literal

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from config import Config
from tracing import record_step


class _HoldingInput(BaseModel):
    ticker: str
    quantity: float
    avg_buy_price: float


class ParsedPrompt(BaseModel):
    name: str = "User"
    risk_level: Literal["low", "medium", "high"] = "medium"
    budget: float = 10000.0
    holdings: list[_HoldingInput] = Field(default_factory=list)
    watchlist: list[str] = Field(default_factory=list)


class PromptParser:
    """Uses Haiku to extract portfolio + profile from a natural language prompt."""

    def __init__(self) -> None:
        self._llm = ChatOpenAI(
            model=Config.HAIKU_MODEL,
            temperature=Config.TEMPERATURE,
            base_url=Config.LLMOD_BASE_URL,
            api_key=Config.LLMOD_API_KEY,
        ).with_structured_output(ParsedPrompt)

    def parse(self, prompt: str) -> ParsedPrompt:
        msg = (
            "Extract investor portfolio and profile information from the user message.\n"
            "Defaults when not mentioned: name='User', risk_level='medium', budget=10000.0, "
            "holdings=[], watchlist=[]\n"
            "risk_level must be exactly one of: low, medium, high\n"
            "For each holding extract: ticker symbol, quantity, avg_buy_price.\n"
            "Watchlist is a list of ticker symbols the user wants to monitor but does not hold.\n\n"
            f"User message: {prompt}"
        )
        result = self._llm.invoke([HumanMessage(content=msg)])  # type: ignore[return-value]
        record_step(
            module="PromptParser",
            prompt={"content": msg},
            response=result.model_dump() if hasattr(result, "model_dump") else result,  # type: ignore[union-attr]
        )
        return result
