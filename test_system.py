"""End-to-end test for FinerisSystem, Notifier, cooldown, and seen-news dedup."""
import json
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from config import Config

# ── backup real storage files ────────────────────────────────────────────────
STORAGE = Config.STORAGE_DIR
REAL_FILES = [
    Config.PORTFOLIO_FILE,
    Config.USER_PROFILE_FILE,
    Config.SEEN_NEWS_FILE,
    Config.NOTIFICATIONS_FILE,
    STORAGE / "cooldowns.json",
]
BACKUPS: dict[Path, Path] = {}

def backup_all() -> None:
    for f in REAL_FILES:
        if f.exists():
            backup = f.with_name("_backup_" + f.name)
            f.rename(backup)
            BACKUPS[f] = backup

def restore_all() -> None:
    for f in REAL_FILES:
        f.unlink(missing_ok=True)
    for original, backup in BACKUPS.items():
        if backup.exists():
            backup.rename(original)

backup_all()

# ── imports after backup so managers start fresh ─────────────────────────────
from models.signals import Notification
from notifier import Notifier
from portfolio.manager import PortfolioManager
from profile.manager import UserProfileManager
from systems.fineris import FinerisSystem

PASS = "✅ PASS"
FAIL = "❌ FAIL"

def check(label: str, condition: bool, got=None, expected=None) -> None:
    status = PASS if condition else FAIL
    print(f"  {status} | {label}")
    if not condition:
        print(f"         expected: {expected}")
        print(f"         got:      {got}")


# ── [1] Notifier ─────────────────────────────────────────────────────────────
print("=" * 60)
print("Notifier Tests")
print("=" * 60)

notifier = Notifier()
test_notif = Notification(
    timestamp=datetime(2025, 1, 1, 12, 0, 0),
    level="ACTION",
    agent="Guardian",
    message="[TSLA] SELL — test notification",
)
notifier.send(test_notif)

log_exists = Config.NOTIFICATIONS_FILE.exists()
check("notifications.log created after send()", log_exists)

if log_exists:
    content = Config.NOTIFICATIONS_FILE.read_text()
    check("log contains timestamp",    "2025-01-01 12:00:00" in content, got=content[:80])
    check("log contains level ACTION", "[ACTION]"            in content, got=content[:80])
    check("log contains agent name",   "[Guardian]"          in content, got=content[:80])
    check("log contains message",      "[TSLA] SELL"         in content, got=content[:80])

    notifier.send(test_notif)
    import re as _re
    blocks = [b for b in _re.split(r'(?=\[\d{4}-\d{2}-\d{2})', Config.NOTIFICATIONS_FILE.read_text()) if b.strip()]
    check("send() appends (2 blocks after 2 calls)", len(blocks) == 2, got=len(blocks), expected=2)


# ── [2] Cooldown logic ───────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("Cooldown Tests")
print("=" * 60)

# Inject a fresh cooldown for TSLA
# Force COOLDOWN_HOURS=4 for this test regardless of demo mode
Config.COOLDOWN_HOURS = 4
cooldowns_path = STORAGE / "cooldowns.json"
cooldowns_path.write_text(json.dumps({"TSLA": datetime.now().isoformat()}))

system = FinerisSystem()
check("TSLA on cooldown when timestamp is now",
      system._is_on_cooldown("TSLA"), got=False, expected=True)
check("AAPL not on cooldown (not in file)",
      not system._is_on_cooldown("AAPL"), got=True, expected=True)

# Inject an expired cooldown (5 hours ago — beyond COOLDOWN_HOURS=4)
expired_time = (datetime.now() - timedelta(hours=5)).isoformat()
cooldowns_path.write_text(json.dumps({"TSLA": expired_time}))
system2 = FinerisSystem()
check("TSLA NOT on cooldown when timestamp is 5h ago",
      not system2._is_on_cooldown("TSLA"), got=True, expected=True)
Config.COOLDOWN_HOURS = 0  # restore demo mode

# Clean up cooldown file before full run
cooldowns_path.unlink(missing_ok=True)


# ── [3] Full run_cycle() ─────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("FinerisSystem.run_cycle() — End-to-End")
print("=" * 60)

# Set up test portfolio and profile
pm = PortfolioManager()
pm.add_holding("TSLA", 10, 200.0)
pm.set_budget(5000.0)

pfm = UserProfileManager()
pfm.set_name("TestUser")
pfm.set_risk_level("medium")
pfm.add_to_watchlist("NVDA")

print("\n  Portfolio: TSLA (10 shares @ $200), Budget: $5000")
print("  Watchlist: NVDA")
print("  Running cycle (may take ~30s)...\n")

fresh_system = FinerisSystem()
notifications = fresh_system.run_cycle()

check("run_cycle() returns a list",
      isinstance(notifications, list), got=type(notifications), expected=list)
check("all items are Notification objects",
      all(isinstance(n, Notification) for n in notifications),
      got=[type(n) for n in notifications])

seen_news_exists = Config.SEEN_NEWS_FILE.exists()
check("seen_news.json created after cycle", seen_news_exists)

if seen_news_exists:
    seen = json.loads(Config.SEEN_NEWS_FILE.read_text())
    check("seen_news.json is a list", isinstance(seen, list), got=type(seen))

cooldowns_exist = cooldowns_path.exists()
check("cooldowns.json exists after cycle", cooldowns_exist)

print(f"\n  Notifications produced: {len(notifications)}")
for n in notifications:
    print(f"    [{n.level}] [{n.agent}] {n.message[:80]}")


# ── [4] Seen-news deduplication ──────────────────────────────────────────────
print("\n" + "=" * 60)
print("Seen-News Deduplication Test")
print("=" * 60)

seen_after_first = set(json.loads(Config.SEEN_NEWS_FILE.read_text())) if seen_news_exists else set()
print(f"\n  Seen news after cycle 1: {len(seen_after_first)} items")
print("  Running cycle 2 (same portfolio, same news window)...\n")

system3 = FinerisSystem()
notifications2 = system3.run_cycle()

seen_after_second = set(json.loads(Config.SEEN_NEWS_FILE.read_text()))
print(f"  Seen news after cycle 2: {len(seen_after_second)} items")

check("seen_news count does not decrease (dedup running)",
      len(seen_after_second) >= len(seen_after_first),
      got=len(seen_after_second), expected=f">= {len(seen_after_first)}")
check("cycle 2 returns a list", isinstance(notifications2, list))


# ── cleanup ──────────────────────────────────────────────────────────────────
restore_all()

print("\n" + "=" * 60)
print("All system tests complete. Storage restored.")
print("=" * 60)
