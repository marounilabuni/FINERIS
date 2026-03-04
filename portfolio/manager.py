from config import Config
from models.market import HoldingSnapshot
from portfolio.models import Holding
from utils import BaseJsonManager


class PortfolioManager(BaseJsonManager):
    def __init__(self) -> None:
        super().__init__(Config.PORTFOLIO_FILE)
        self._data = self._load() or {"holdings": {}, "budget": 0.0}

    # --- Holdings CRUD ---

    def add_holding(self, ticker: str, quantity: float, avg_buy_price: float) -> None:
        self._data["holdings"][ticker] = {
            "ticker": ticker,
            "quantity": quantity,
            "avg_buy_price": avg_buy_price,
        }
        self._save(self._data)

    def remove_holding(self, ticker: str) -> None:
        if ticker not in self._data["holdings"]:
            raise KeyError(f"Holding '{ticker}' not found.")
        
        self._data["holdings"].pop(ticker, None)
        self._save(self._data)

    def update_holding(self, ticker: str, quantity: float, avg_buy_price: float) -> None:
        if ticker not in self._data["holdings"]:
            raise KeyError(f"Holding '{ticker}' not found.")
        self._data["holdings"][ticker] = {
            "ticker": ticker,
            "quantity": quantity,
            "avg_buy_price": avg_buy_price,
        }
        self._save(self._data)

    def get_holding(self, ticker: str) -> Holding | None:
        raw = self._data["holdings"].get(ticker)
        return Holding(**raw) if raw else None

    def get_all_holdings(self) -> list[Holding]:
        return [Holding(**h) for h in self._data["holdings"].values()]

    # --- Budget ---

    def get_budget(self) -> float:
        return float(self._data["budget"])

    def set_budget(self, amount: float) -> None:
        self._data["budget"] = amount
        self._save(self._data)

    # --- Derived (requires live prices) ---

    def get_snapshots(self, current_prices: dict[str, float]) -> list[HoldingSnapshot]:
        # TODO: Handle case where current_prices is empty or missing some tickers
        
        holdings = self.get_all_holdings()
        
        for h in holdings:
            if h.ticker not in current_prices:
                print(f"[!] WARNING: No price data available for {h.ticker}, using average buy price instead")
        
        
        total_value = sum(
            h.quantity * current_prices.get(h.ticker, h.avg_buy_price)
            for h in holdings
        )
        snapshots = []
        for h in holdings:
            price = current_prices.get(h.ticker, h.avg_buy_price)
            value = h.quantity * price
            pnl = (price - h.avg_buy_price) * h.quantity
            weight = value / total_value if total_value > 0 else 0.0
            snapshots.append(HoldingSnapshot(
                ticker=h.ticker,
                quantity=h.quantity,
                avg_buy_price=h.avg_buy_price,
                current_price=price,
                current_value=value,
                unrealized_pnl=pnl,
                portfolio_weight=weight,
            ))
        return snapshots
