"""Quick sanity test — run before anything else."""
from dotenv import load_dotenv
load_dotenv()

from data.market import YFinanceSource

src = YFinanceSource()
TICKER = "TSLA"

print("=" * 50)
print(f"Testing YFinanceSource with {TICKER}")
print("=" * 50)

# 1. Snapshot
print("\n[1] get_snapshot")
snap = src.get_snapshot(TICKER)
print(snap)

# 2. News
print("\n[2] get_news")
news = src.get_news(TICKER)
print(f"  Got {len(news)} news items")
for n in news[:2]:
    print(f"  - {n.headline[:80]}")
    print(f"    sentiment_ready: {bool(n.summary)}")

# 3. History
print("\n[3] get_history (30d)")
history = src.get_history(TICKER, period="30d")
print(f"  Got {len(history)} candles")
if history:
    print(f"  First: {history[0]}")
    print(f"  Last:  {history[-1]}")

# 4. Fundamentals
print("\n[4] get_fundamentals")
fundamentals = src.get_fundamentals(TICKER)
print(f"  {fundamentals}")

print("\n" + "=" * 50)
print("Done. Check output above for any None/empty values.")
print("=" * 50)
