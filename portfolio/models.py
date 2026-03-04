from pydantic import BaseModel


class Holding(BaseModel):
    ticker: str
    quantity: float
    avg_buy_price: float
