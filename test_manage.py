"""Test manage.py CLI commands via subprocess."""
import subprocess
import sys
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
STORAGE_DIR = BASE_DIR / "storage"
PORTFOLIO_FILE = STORAGE_DIR / "portfolio.json"
PROFILE_FILE = STORAGE_DIR / "user_profile.json"
BACKUP_PORTFOLIO = STORAGE_DIR / "_backup_portfolio.json"
BACKUP_PROFILE = STORAGE_DIR / "_backup_user_profile.json"

PASS = "✅ PASS"
FAIL = "❌ FAIL"


# ── helpers ─────────────────────────────────────────────────────────────────

def run(*args: str) -> tuple[str, int]:
    """Run manage.py with the given args. Returns (stdout, returncode)."""
    result = subprocess.run(
        [sys.executable, "manage.py", *args],
        capture_output=True,
        text=True,
        cwd=BASE_DIR,
    )
    return result.stdout.strip(), result.returncode


def check(label: str, condition: bool, got=None, expected=None) -> None:
    status = PASS if condition else FAIL
    print(f"  {status} | {label}")
    if not condition:
        print(f"         expected: {expected}")
        print(f"         got:      {got}")


def backup_real_files() -> None:
    """Move real storage files out of the way so tests start clean."""
    if PORTFOLIO_FILE.exists():
        PORTFOLIO_FILE.rename(BACKUP_PORTFOLIO)
    if PROFILE_FILE.exists():
        PROFILE_FILE.rename(BACKUP_PROFILE)


def restore_real_files() -> None:
    """Delete test files and restore backed-up real files."""
    PORTFOLIO_FILE.unlink(missing_ok=True)
    PROFILE_FILE.unlink(missing_ok=True)
    if BACKUP_PORTFOLIO.exists():
        BACKUP_PORTFOLIO.rename(PORTFOLIO_FILE)
    if BACKUP_PROFILE.exists():
        BACKUP_PROFILE.rename(PROFILE_FILE)


# ── setup ───────────────────────────────────────────────────────────────────
backup_real_files()

print("=" * 60)
print("manage.py CLI Tests")
print("=" * 60)


# ── [1] Portfolio: initial list is empty ─────────────────────────────────────
print("\n[1] Initial state")
out, _ = run("portfolio", "list")
check("Empty portfolio prints 'No holdings.'", out == "No holdings.", got=out)


# ── [2] Add holdings ─────────────────────────────────────────────────────────
print("\n[2] Add holdings")
out, _ = run("portfolio", "add", "-t", "tsla", "-q", "10", "-p", "200.0")
check("Add TSLA (lowercase ticker normalized)", "TSLA" in out, got=out)

out, _ = run("portfolio", "add", "-t", "AAPL", "-q", "5", "-p", "150.0")
check("Add AAPL", "AAPL" in out, got=out)

out, _ = run("portfolio", "list")
check("List shows TSLA", "TSLA" in out, got=out)
check("List shows AAPL", "AAPL" in out, got=out)
check("TSLA price shows 200.00", "200.00" in out, got=out)


# ── [3] Update holding ───────────────────────────────────────────────────────
print("\n[3] Update holding")
out, _ = run("portfolio", "update", "-t", "TSLA", "-q", "15", "-p", "180.0")
check("Update TSLA success message", "Updated TSLA" in out, got=out)

out, _ = run("portfolio", "list")
check("Updated quantity 15.0 in list", "15.0" in out, got=out)
check("Updated price 180.00 in list", "180.00" in out, got=out)


# ── [4] Budget ───────────────────────────────────────────────────────────────
print("\n[4] Budget")
out, _ = run("budget", "set", "-a", "5000.0")
check("Set budget prints confirmation", "5000.00" in out, got=out)

out, _ = run("budget", "get")
check("Get budget shows $5000.00", "$5000.00" in out, got=out)

out, _ = run("budget", "set", "-a", "3000.0")
out, _ = run("budget", "get")
check("Update budget to 3000.00", "$3000.00" in out, got=out)


# ── [5] Remove holding ───────────────────────────────────────────────────────
print("\n[5] Remove holding")
out, _ = run("portfolio", "remove", "-t", "AAPL")
check("Remove AAPL success message", "Removed AAPL" in out, got=out)

out, _ = run("portfolio", "list")
check("AAPL no longer listed", "AAPL" not in out, got=out)
check("TSLA still listed", "TSLA" in out, got=out)


# ── [6] Error handling ───────────────────────────────────────────────────────
print("\n[6] Error handling")
out, _ = run("portfolio", "remove", "-t", "ZZZZ")
check("Remove non-existent prints Error (no crash)", out.startswith("Error:"), got=out)

out, _ = run("portfolio", "update", "-t", "ZZZZ", "-q", "1", "-p", "100")
check("Update non-existent prints Error (no crash)", out.startswith("Error:"), got=out)


# ── [7] Profile: name and risk ───────────────────────────────────────────────
print("\n[7] Profile — name and risk")
out, _ = run("profile", "set-name", "-v", "Maroun")
check("set-name confirmation", "Maroun" in out, got=out)

out, _ = run("profile", "set-risk", "-v", "high")
check("set-risk confirmation", "high" in out, got=out)

out, _ = run("profile", "show")
check("show: name is Maroun", "Maroun" in out, got=out)
check("show: risk is high", "high" in out, got=out)


# ── [8] Watchlist ────────────────────────────────────────────────────────────
print("\n[8] Watchlist")
out, _ = run("profile", "add-watch", "-v", "nvda")   # lowercase → normalized
check("add-watch NVDA (lowercase input normalized)", "NVDA" in out, got=out)

out, _ = run("profile", "add-watch", "-v", "MSFT")
check("add-watch MSFT", "MSFT" in out, got=out)

out, _ = run("profile", "show")
check("show: NVDA in watchlist", "NVDA" in out, got=out)
check("show: MSFT in watchlist", "MSFT" in out, got=out)

out, _ = run("profile", "remove-watch", "-v", "NVDA")
check("remove-watch NVDA confirmation", "NVDA" in out, got=out)

out, _ = run("profile", "show")
check("show: NVDA removed", "NVDA" not in out, got=out)
check("show: MSFT still there", "MSFT" in out, got=out)


# ── [9] Persistence across processes ─────────────────────────────────────────
print("\n[9] Persistence (each run is a fresh process)")
out, _ = run("portfolio", "list")
check("TSLA persists across processes", "TSLA" in out, got=out)
check("AAPL removed persists", "AAPL" not in out, got=out)

out, _ = run("budget", "get")
check("Budget $3000.00 persists", "$3000.00" in out, got=out)

out, _ = run("profile", "show")
check("Name Maroun persists", "Maroun" in out, got=out)
check("Risk high persists", "high" in out, got=out)
check("MSFT watchlist persists", "MSFT" in out, got=out)


# ── cleanup ──────────────────────────────────────────────────────────────────
restore_real_files()

print("\n" + "=" * 60)
print("All CLI tests complete. Storage restored to original state.")
print("=" * 60)
