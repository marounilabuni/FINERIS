"""Test PortfolioManager and UserProfileManager as classes."""
from dotenv import load_dotenv
load_dotenv()

from config import Config

# Use test storage files to avoid overwriting real data
Config.PORTFOLIO_FILE = Config.STORAGE_DIR / "test_portfolio.json"
Config.USER_PROFILE_FILE = Config.STORAGE_DIR / "test_user_profile.json"

# Clean up test files before starting
for f in [Config.PORTFOLIO_FILE, Config.USER_PROFILE_FILE]:
    if f.exists():
        f.unlink()

from portfolio.manager import PortfolioManager
from profile.manager import UserProfileManager

PASS = "✅ PASS"
FAIL = "❌ FAIL"

def check(label: str, condition: bool, got=None, expected=None) -> None:
    status = PASS if condition else FAIL
    print(f"  {status} | {label}")
    if not condition:
        print(f"         expected: {expected}")
        print(f"         got:      {got}")

print("=" * 60)
print("PortfolioManager Tests")
print("=" * 60)

pm = PortfolioManager()

# 1. Initial state
print("\n[1] Initial state")
check("No holdings", pm.get_all_holdings() == [])
check("Budget is 0", pm.get_budget() == 0.0)

# 2. Add holdings
print("\n[2] Add holdings")
pm.add_holding("TSLA", 10, 200.0)
pm.add_holding("AAPL", 5, 150.0)
holdings = pm.get_all_holdings()
tickers = [h.ticker for h in holdings]
check("TSLA added", "TSLA" in tickers)
check("AAPL added", "AAPL" in tickers)
check("2 holdings total", len(holdings) == 2, got=len(holdings), expected=2)

# 3. Get specific holding
print("\n[3] Get holding")
tsla = pm.get_holding("TSLA")
check("TSLA quantity=10", tsla.quantity == 10, got=tsla.quantity, expected=10)
check("TSLA buy_price=200", tsla.avg_buy_price == 200.0, got=tsla.avg_buy_price, expected=200.0)
check("Non-existent returns None", pm.get_holding("ZZZZ") is None)

# 4. Update holding
print("\n[4] Update holding")
pm.update_holding("TSLA", 15, 180.0)
tsla = pm.get_holding("TSLA")
check("TSLA quantity updated to 15", tsla.quantity == 15, got=tsla.quantity, expected=15)
check("TSLA price updated to 180", tsla.avg_buy_price == 180.0, got=tsla.avg_buy_price, expected=180.0)

# 5. Budget
print("\n[5] Budget")
pm.set_budget(5000.0)
check("Budget set to 5000", pm.get_budget() == 5000.0, got=pm.get_budget(), expected=5000.0)
pm.set_budget(3000.0)
check("Budget updated to 3000", pm.get_budget() == 3000.0, got=pm.get_budget(), expected=3000.0)

# 6. Derived: get_snapshots
print("\n[6] Derived snapshots")
prices = {"TSLA": 411.71, "AAPL": 220.0}
snapshots = pm.get_snapshots(prices)
tsla_snap = next(s for s in snapshots if s.ticker == "TSLA")
aapl_snap = next(s for s in snapshots if s.ticker == "AAPL")

expected_tsla_value = 15 * 411.71
expected_tsla_pnl = (411.71 - 180.0) * 15
total_value = expected_tsla_value + (5 * 220.0)
expected_tsla_weight = expected_tsla_value / total_value

check("TSLA current_value correct", abs(tsla_snap.current_value - expected_tsla_value) < 0.001,
      got=round(tsla_snap.current_value, 2), expected=round(expected_tsla_value, 2))
check("TSLA unrealized_pnl correct", abs(tsla_snap.unrealized_pnl - expected_tsla_pnl) < 0.001,
      got=round(tsla_snap.unrealized_pnl, 2), expected=round(expected_tsla_pnl, 2))
check("Weights sum to 1.0", abs(sum(s.portfolio_weight for s in snapshots) - 1.0) < 0.001,
      got=round(sum(s.portfolio_weight for s in snapshots), 4), expected=1.0)
check("TSLA weight correct", abs(tsla_snap.portfolio_weight - expected_tsla_weight) < 0.001,
      got=round(tsla_snap.portfolio_weight, 4), expected=round(expected_tsla_weight, 4))

# 7. Remove holding
print("\n[7] Remove holding")
pm.remove_holding("AAPL")
check("AAPL removed", pm.get_holding("AAPL") is None)
check("1 holding remaining", len(pm.get_all_holdings()) == 1, got=len(pm.get_all_holdings()), expected=1)

# 8. Remove non-existent raises KeyError
print("\n[8] Error handling")
try:
    pm.remove_holding("ZZZZ")
    check("Remove non-existent raises KeyError", False)
except KeyError:
    check("Remove non-existent raises KeyError", True)

try:
    pm.update_holding("ZZZZ", 5, 100.0)
    check("Update non-existent raises KeyError", False)
except KeyError:
    check("Update non-existent raises KeyError", True)

# 9. Persistence: reload from file
print("\n[9] Persistence")
pm2 = PortfolioManager()
check("Holdings persist after reload", len(pm2.get_all_holdings()) == 1,
      got=len(pm2.get_all_holdings()), expected=1)
check("Budget persists after reload", pm2.get_budget() == 3000.0,
      got=pm2.get_budget(), expected=3000.0)


print("\n" + "=" * 60)
print("UserProfileManager Tests")
print("=" * 60)

pfm = UserProfileManager()

# 1. Default state
print("\n[1] Default state")
profile = pfm.get_profile()
check("Default risk is medium", profile.risk_level == "medium", got=profile.risk_level, expected="medium")
check("Default watchlist empty", profile.watchlist == [], got=profile.watchlist, expected=[])

# 2. Set name and risk
print("\n[2] Set name and risk")
pfm.set_name("Maroun")
pfm.set_risk_level("high")
profile = pfm.get_profile()
check("Name set correctly", profile.name == "Maroun", got=profile.name, expected="Maroun")
check("Risk set to high", profile.risk_level == "high", got=profile.risk_level, expected="high")

# 3. Watchlist operations
print("\n[3] Watchlist")
pfm.add_to_watchlist("nvda")       # lowercase — should normalize
pfm.add_to_watchlist("MSFT")
pfm.add_to_watchlist("NVDA")       # duplicate — should not add again
watchlist = pfm.get_profile().watchlist
check("NVDA normalized to uppercase", "NVDA" in watchlist)
check("MSFT added", "MSFT" in watchlist)
check("No duplicates", watchlist.count("NVDA") == 1, got=watchlist.count("NVDA"), expected=1)
check("2 items in watchlist", len(watchlist) == 2, got=len(watchlist), expected=2)

pfm.remove_from_watchlist("NVDA")
watchlist = pfm.get_profile().watchlist
check("NVDA removed", "NVDA" not in watchlist)
check("1 item remaining", len(watchlist) == 1, got=len(watchlist), expected=1)

# 4. Set full watchlist
print("\n[4] Set full watchlist")
pfm.set_watchlist(["amzn", "googl", "META"])
watchlist = pfm.get_profile().watchlist
check("All tickers uppercase", all(t == t.upper() for t in watchlist))
check("3 items", len(watchlist) == 3, got=len(watchlist), expected=3)

# 5. Persistence
print("\n[5] Persistence")
pfm2 = UserProfileManager()
profile2 = pfm2.get_profile()
check("Name persists", profile2.name == "Maroun", got=profile2.name, expected="Maroun")
check("Risk persists", profile2.risk_level == "high", got=profile2.risk_level, expected="high")
check("Watchlist persists", len(profile2.watchlist) == 3, got=len(profile2.watchlist), expected=3)

# Cleanup test files
Config.PORTFOLIO_FILE.unlink(missing_ok=True)
Config.USER_PROFILE_FILE.unlink(missing_ok=True)

print("\n" + "=" * 60)
print("All tests complete. Test files cleaned up.")
print("=" * 60)
