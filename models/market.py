from datetime import datetime
from pydantic import BaseModel


class StockSnapshot(BaseModel):
    ticker: str
    current_price: float
    change_pct: float
    volume: float
    timestamp: datetime


class HoldingSnapshot(BaseModel):
    ticker: str
    quantity: float
    avg_buy_price: float
    current_price: float
    current_value: float
    unrealized_pnl: float
    portfolio_weight: float


class NewsItem(BaseModel):
    ticker: str
    headline: str
    summary: str
    published_at: datetime
    url: str = ""


class MarketEvent(BaseModel):
    ticker: str
    snapshot: StockSnapshot
    news: list[NewsItem]
