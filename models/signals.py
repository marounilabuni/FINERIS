from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class GuardianSignal(BaseModel):
    ticker: str
    recommendation: Literal["HOLD", "SELL"]
    reasoning: str
    historical_context: str
    news_count: int = 0


class ScoutSignal(BaseModel):
    ticker: str
    recommendation: Literal["BUY", "PASS"]
    confidence: Literal["low", "medium", "high"] = "medium"
    reasoning: str
    momentum_score: float
    news_count: int = 0


class Notification(BaseModel):
    timestamp: datetime
    level: Literal["INFO", "WARNING", "ACTION"]
    agent: str
    message: str
