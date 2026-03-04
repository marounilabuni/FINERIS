"""Test Guardian, Scout, and Supervisor agents with real yfinance data."""
from dotenv import load_dotenv
load_dotenv()

from datetime import datetime

from data.market import YFinanceSource
from models.market import HoldingSnapshot, MarketEvent
from models.user import UserProfile
from agents.supervisor import SupervisorAgent
from systems.guardian_system import GuardianSystem
from systems.scout_system import ScoutSystem

src = YFinanceSource()
supervisor = SupervisorAgent()
guardian_system = GuardianSystem()
scout_system = ScoutSystem()

HELD_TICKER = "TSLA"
WATCH_TICKER = "NVDA"

profile = UserProfile(
    name="Test User",
    risk_level="medium",
    watchlist=[WATCH_TICKER],
)

print("=" * 60)
print("FINERIS Agent Tests — Real Data")
print("=" * 60)

# --- 1. Supervisor: sentiment classification ---
print("\n[1] Supervisor — News Sentiment Classification (batch)")
news_items = src.get_news(HELD_TICKER)[:5]
sentiments = supervisor.classify_news_sentiments(news_items)
for item, sentiment in zip(news_items, sentiments):
    print(f"  [{sentiment}] {item.headline[:70]}")

# --- 2. Guardian ---
print(f"\n[2] GuardianSystem — {HELD_TICKER}")
snapshot = src.get_snapshot(HELD_TICKER)
holding_snapshot = HoldingSnapshot(
    ticker=HELD_TICKER,
    quantity=10,
    avg_buy_price=300.0,
    current_price=snapshot.current_price,
    current_value=10 * snapshot.current_price,
    unrealized_pnl=(snapshot.current_price - 300.0) * 10,
    portfolio_weight=0.4,
)
event = MarketEvent(
    ticker=HELD_TICKER,
    snapshot=snapshot,
    news=news_items,
)
guardian_signal = guardian_system.run(
    event=event,
    snapshot=holding_snapshot,
    profile=profile,
)
print(f"  Recommendation : {guardian_signal.recommendation}")
print(f"  Reasoning      : {guardian_signal.reasoning}")
print(f"  Historical     : {guardian_signal.historical_context}")

# --- 3. Scout ---
print(f"\n[3] ScoutSystem — {WATCH_TICKER}")
scout_signal = scout_system.run(
    ticker=WATCH_TICKER,
    profile=profile,
    budget=5000.0,
    portfolio_weights={HELD_TICKER: 0.4},
)
print(f"  Recommendation : {scout_signal.recommendation}")
print(f"  Reasoning      : {scout_signal.reasoning}")
print(f"  Momentum Score : {scout_signal.momentum_score:.1%}")

print("\n" + "=" * 60)
print("Done.")
print("=" * 60)
