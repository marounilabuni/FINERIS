"""
Backtest FINERIS Guardian + Scout agents on historical CSV data.

Prices CSV: date,close,volume          (date as YYYY-MM-DD)
News CSV:   published_at,headline,summary,ticker   (published_at as YYYY-MM-DD or ISO datetime)

Logic:
  - Sliding window over price history (size=WINDOW days, step=STEP days)
  - If NOT holding → run Scout → BUY signal buys with full budget
  - If holding     → run Guardian → SELL signal exits the position
  - Prints a row per step + final P&L summary

Usage:
    python backtest.py --ticker BTC-USD --prices btc_prices.csv --news btc_news.csv
    python backtest.py --ticker ETH-USD --prices eth.csv --news eth_news.csv --step 3 --risk high
"""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

# Allow imports from inside fineris/
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.guardian import GuardianAgent
from agents.scout import ScoutAgent
from agents.supervisor import SupervisorAgent
from config import Config
from models.market import HoldingSnapshot, MarketEvent, NewsItem, StockSnapshot
from models.user import UserProfile


# ── CSV loaders ───────────────────────────────────────────────────────────────

def load_prices(path: str) -> list[dict]:
    """Load prices CSV. Required columns: date, close, volume."""
    rows = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            rows.append({
                "date":   row["date"],
                "close":  float(row["close"]),
                "volume": float(row.get("volume", 0)),
            })
    rows.sort(key=lambda r: r["date"])
    return rows


def load_news(path: str, ticker: str) -> list[NewsItem]:
    """Load news CSV. Required columns: published_at, headline, summary."""
    items = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                raw = row["published_at"]
                try:
                    dt = datetime.fromisoformat(raw)
                except ValueError:
                    dt = datetime.strptime(raw[:10], "%Y-%m-%d")
                items.append(NewsItem(
                    ticker=ticker,
                    headline=row["headline"],
                    summary=row.get("summary", ""),
                    url=row.get("url", ""),
                    published_at=dt,
                ))
            except Exception as e:
                print(f"[WARN] Skipping news row: {e}")
    items.sort(key=lambda n: n.published_at)
    return items


# ── Helpers ───────────────────────────────────────────────────────────────────

def news_in_window(all_news: list[NewsItem], start: datetime, end: datetime) -> list[NewsItem]:
    return [n for n in all_news if start <= n.published_at <= end]


def build_news_summary(items: list[NewsItem], supervisor: SupervisorAgent) -> tuple[str, int]:
    if not items:
        return "No recent news.", 0
    top = items[:5]
    sentiments = supervisor.classify_news_sentiments(top)
    lines = [f"- [{s}] {n.headline}: {n.summary}" for n, s in zip(top, sentiments)]
    return "\n".join(lines), len(top)


# ── Backtest ──────────────────────────────────────────────────────────────────

def backtest(
    ticker: str,
    prices: list[dict],
    all_news: list[NewsItem],
    step: int,
    window: int,
    initial_budget: float,
    risk: str,
    model: str,
) -> None:
    profile  = UserProfile(name="Backtest", risk_level=risk, watchlist=[ticker])  # type: ignore
    guardian = GuardianAgent(model=model)
    scout    = ScoutAgent(model=model)
    supervisor = SupervisorAgent(model=model)

    holding       = False
    avg_buy_price = 0.0
    quantity      = 0.0
    budget        = initial_budget

    print(f"\n{'='*72}")
    print(f"  FINERIS BACKTEST — {ticker}  |  window={window}d  step={step}d  "
          f"budget=${initial_budget:,.0f}  risk={risk}")
    print(f"{'='*72}")
    print(f"{'Date':<12} {'Price':>10}  {'Signal':<6}  {'Reasoning (truncated)'}")
    print(f"{'-'*72}")

    i = window
    while i <= len(prices):
        history       = prices[i - window : i]
        current       = prices[i - 1]
        prev          = prices[i - 2] if i >= 2 else current
        current_price = current["close"]
        change_pct    = (current["close"] - prev["close"]) / prev["close"] if prev["close"] else 0.0
        date_str      = current["date"]

        win_start = datetime.strptime(history[0]["date"], "%Y-%m-%d")
        win_end   = datetime.strptime(current["date"], "%Y-%m-%d").replace(hour=23, minute=59)
        window_news = news_in_window(all_news, win_start, win_end)

        if holding:
            # ── Guardian: protect the position ──
            snapshot = HoldingSnapshot(
                ticker=ticker,
                quantity=quantity,
                avg_buy_price=avg_buy_price,
                current_price=current_price,
                current_value=quantity * current_price,
                unrealized_pnl=(current_price - avg_buy_price) * quantity,
                portfolio_weight=1.0,
            )
            stock_snap = StockSnapshot(
                ticker=ticker,
                current_price=current_price,
                change_pct=change_pct,
                volume=current["volume"],
                timestamp=win_end,
            )
            event  = MarketEvent(ticker=ticker, snapshot=stock_snap, news=window_news)
            signal = guardian.run(event=event, snapshot=snapshot, profile=profile, history=history)

            short = signal.reasoning.replace("\n", " ")[:55]
            print(f"{date_str:<12} ${current_price:>10,.2f}  {signal.recommendation:<6}  {short}…")

            if signal.recommendation == "SELL":
                proceeds = quantity * current_price
                pnl      = proceeds - (quantity * avg_buy_price)
                budget  += proceeds
                print(f"  → SOLD {quantity:.6f} @ ${current_price:,.2f} | "
                      f"PnL: ${pnl:+,.2f} | Budget: ${budget:,.2f}")
                holding = False
                quantity = avg_buy_price = 0.0

        else:
            # ── Scout: hunt for a buy opportunity ──
            news_summary, news_count = build_news_summary(window_news, supervisor)
            signal = scout.run(
                ticker=ticker,
                profile=profile,
                budget=budget,
                portfolio_weights={},
                history=history,
                fundamentals={"pe_ratio": "N/A", "market_cap": "N/A",
                              "earnings_growth": "N/A", "sector": "Crypto"},
                news_summary=news_summary,
                news_count=news_count,
            )

            short = signal.reasoning.replace("\n", " ")[:55]
            print(f"{date_str:<12} ${current_price:>10,.2f}  {signal.recommendation:<6}  {short}…")

            if signal.recommendation == "BUY":
                quantity      = budget / current_price
                avg_buy_price = current_price
                budget        = 0.0
                holding       = True
                print(f"  → BOUGHT {quantity:.6f} @ ${current_price:,.2f}")

        i += step

    # ── Summary ──
    final_price = prices[-1]["close"]
    final_value = quantity * final_price + budget
    total_return = (final_value - initial_budget) / initial_budget * 100
    print(f"\n{'='*72}")
    print(f"  Started:  ${initial_budget:>12,.2f}")
    print(f"  Final:    ${final_value:>12,.2f}  ({total_return:+.1f}%)")
    if holding:
        print(f"  Position: holding {quantity:.6f} {ticker} @ ${final_price:,.2f} (unrealized)")
    else:
        print(f"  Position: cash")
    print(f"{'='*72}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest FINERIS on CSV data")
    parser.add_argument("--ticker",  default="BTC-USD",       help="Ticker symbol (default: BTC-USD)")
    parser.add_argument("--prices",  required=True,           help="Prices CSV path (date,close,volume)")
    parser.add_argument("--news",    required=True,           help="News CSV path (published_at,headline,summary)")
    parser.add_argument("--step",    type=int,   default=7,   help="Days per step (default: 7)")
    parser.add_argument("--window",  type=int,   default=Config.MOMENTUM_WINDOW_DAYS, help="Window size in days")
    parser.add_argument("--budget",  type=float, default=10_000.0)
    parser.add_argument("--risk",    default="medium",        choices=["low", "medium", "high"])
    parser.add_argument("--model",   default=Config.MODEL)
    args = parser.parse_args()

    prices = load_prices(args.prices)
    news   = load_news(args.news, args.ticker)

    if len(prices) < args.window:
        print(f"[ERROR] Not enough price rows ({len(prices)}) for window={args.window}. Need at least {args.window}.")
        sys.exit(1)

    backtest(
        ticker=args.ticker,
        prices=prices,
        all_news=news,
        step=args.step,
        window=args.window,
        initial_budget=args.budget,
        risk=args.risk,
        model=args.model,
    )
