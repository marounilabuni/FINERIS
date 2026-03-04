"""
Scout-only backtest on CSV data.
Slides a window over prices, skips steps with no news, runs Scout each step.
Results printed as a live table that refreshes after each batch.

Usage:
    python backtest_scout.py --prices eth_prices.csv --news eth_news.csv
    python backtest_scout.py --prices eth_prices.csv --news eth_news.csv --step 10 --threads 4
"""

import argparse
import csv
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.scout import ScoutAgent
from agents.supervisor import SupervisorAgent
from config import Config
from models.market import NewsItem
from models.user import UserProfile


# ── CSV loaders ───────────────────────────────────────────────────────────────

def load_prices(path: str) -> list[dict]:
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
    top = items[:5]
    sentiments = supervisor.classify_news_sentiments(top)
    lines = [f"- [{s}] {n.headline}: {n.summary}" for n, s in zip(top, sentiments)]
    return "\n".join(lines), len(top)


def prices_in_news_range(prices: list[dict], news: list[NewsItem]) -> list[dict]:
    first_news = news[0].published_at.strftime("%Y-%m-%d")
    last_news  = news[-1].published_at.strftime("%Y-%m-%d")
    return [p for p in prices if first_news <= p["date"] <= last_news]


def filter_by_date_range(
    prices: list[dict],
    all_news: list[NewsItem],
    start: str | None,
    end: str | None,
    news_window: int,
) -> tuple[list[dict], list[NewsItem]]:
    """Filter prices to [start, end] and news to [start - news_window, end]."""
    if not start:
        return prices, all_news
    news_start = (datetime.strptime(start, "%Y-%m-%d") - timedelta(days=news_window)).strftime("%Y-%m-%d")
    filtered_prices = [p for p in prices if start <= p["date"] <= end]  # type: ignore[operator]
    filtered_news   = [n for n in all_news if news_start <= n.published_at.strftime("%Y-%m-%d") <= end]  # type: ignore[operator]
    return filtered_prices, filtered_news


def clear_and_print(header: str, results: list[dict], total_jobs: int) -> None:
    os.system("clear")
    print(header)
    print(f"  Progress: {len(results)}/{total_jobs}")
    print(f"{'='*76}")
    print(f"  {'Date':<12} {'Price':>10}  {'Signal':<12}  {'News':>4}  Reasoning")
    print(f"  {'-'*72}")
    for r in results:
        if r.get("error"):
            print(f"  {r['date']:<12} {'ERROR':<24}  {r['error'][:40]}")
        else:
            short = r["reasoning"].replace("\n", " ")[:48]
            label = f"{r['recommendation']}/{r['confidence']}"
            print(f"  {r['date']:<12} ${r['price']:>10,.2f}  {label:<12}  {r['news_count']:>3}n  {short}…")
    print(f"{'='*76}\n")


# ── Step runner (called per thread) ──────────────────────────────────────────

def run_step(
    job: dict,
    scout: ScoutAgent,
    supervisor: SupervisorAgent,
    profile: UserProfile,
    budget: float,
) -> dict:
    try:
        news_summary, news_count = build_news_summary(job["news"], supervisor)
        signal = scout.run(
            ticker=job["ticker"],
            profile=profile,
            budget=budget,
            portfolio_weights={},
            history=job["history"],
            fundamentals={"pe_ratio": "N/A", "market_cap": "N/A",
                          "earnings_growth": "N/A", "sector": "Crypto"},
            news_summary=news_summary,
            news_count=news_count,
        )
        return {
            "date":           job["date"],
            "price":          job["price"],
            "recommendation": signal.recommendation,
            "confidence":     signal.confidence,
            "reasoning":      signal.reasoning,
            "news_count":     news_count,
            "error":          None,
        }
    except Exception as e:
        return {"date": job["date"], "price": job["price"], "error": str(e),
                "recommendation": "ERROR", "confidence": "", "reasoning": "", "news_count": 0}


# ── Backtest ──────────────────────────────────────────────────────────────────

def backtest(
    ticker: str,
    prices: list[dict],
    all_news: list[NewsItem],
    step: int,
    window: int,
    news_window: int,
    budget: float,
    risk: str,
    model: str,
    threads: int,
) -> None:
    profile    = UserProfile(name="Backtest", risk_level=risk, watchlist=[ticker])  # type: ignore  # Pydantic validates Literal["low","medium","high"]
    scout      = ScoutAgent(model=model)
    supervisor = SupervisorAgent(model=model)

    scoped = prices_in_news_range(prices, all_news)
    if len(scoped) < window:
        print(f"[ERROR] Not enough price rows ({len(scoped)}) for window={window}.")
        return

    # Pre-build all jobs (skip windows with no news)
    jobs: list[dict] = []
    i = window
    while i <= len(scoped):
        current = scoped[i - 1]
        win_end   = datetime.strptime(current["date"], "%Y-%m-%d").replace(hour=23, minute=59)
        win_start = win_end - timedelta(days=news_window)
        window_news = news_in_window(all_news, win_start, win_end)
        if window_news:
            jobs.append({
                "ticker":  ticker,
                "date":    current["date"],
                "price":   current["close"],
                "history": scoped[i - window : i],
                "news":    window_news,
            })
        i += step

    if not jobs:
        print("[ERROR] No steps with news found.")
        return

    header = (
        f"\n{'='*76}\n"
        f"  SCOUT BACKTEST — {ticker}  |  window={window}d  step={step}d  "
        f"news_window={news_window}d  threads={threads}  risk={risk}\n"
        f"  Date range: {scoped[0]['date']} → {scoped[-1]['date']}  "
        f"({len(jobs)} steps with news)"
    )

    results: list[dict] = []

    # Process in batches of `threads`, refresh table after each batch
    with ThreadPoolExecutor(max_workers=threads) as executor:
        for batch_start in range(0, len(jobs), threads):
            batch = jobs[batch_start : batch_start + threads]
            futures = {executor.submit(run_step, job, scout, supervisor, profile, budget): job
                       for job in batch}
            for future in as_completed(futures):
                results.append(future.result())
                results.sort(key=lambda r: r["date"])
                clear_and_print(header, results, len(jobs))

    print(f"  Done. {len(results)} Scout calls completed.\n")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scout-only backtest on CSV data")
    parser.add_argument("--ticker",      default="ETH-USD")
    parser.add_argument("--prices",      required=True)
    parser.add_argument("--news",        required=True)
    parser.add_argument("--step",        type=int,   default=90)
    parser.add_argument("--window",      type=int,   default=Config.MOMENTUM_WINDOW_DAYS)
    parser.add_argument("--news-window", type=int,   default=7)
    parser.add_argument("--budget",      type=float, default=10_000.0)
    parser.add_argument("--risk",        default="medium")  # choices=["low", "medium", "high"] — validated by Pydantic
    parser.add_argument("--model",       default=Config.MODEL)
    parser.add_argument("--threads",      type=int,   default=1,   help="Parallel Scout calls per batch (default: 1)")
    parser.add_argument("--start",        default=None,            help="Start date YYYY-MM-DD (filters prices)")
    parser.add_argument("--duration-days",type=int,   default=180, help="Days from start (default: 180, ignored if no --start)")
    args = parser.parse_args()

    prices = load_prices(args.prices)
    news   = load_news(args.news, args.ticker)

    # Apply date range filter if --start is given
    start = args.start
    end   = None
    if start:
        end = (datetime.strptime(start, "%Y-%m-%d") + timedelta(days=args.duration_days)).strftime("%Y-%m-%d")
        print(f"[Filter] {start} → {end} ({args.duration_days} days)")
        prices, news = filter_by_date_range(prices, news, start, end, args.news_window)
        if not prices:
            print("[ERROR] No price rows in given date range.")
            sys.exit(1)
        if not news:
            print("[ERROR] No news in given date range.")
            sys.exit(1)

    backtest(
        ticker=args.ticker,
        prices=prices,
        all_news=news,
        step=args.step,
        window=args.window,
        news_window=args.news_window,
        budget=args.budget,
        risk=args.risk,
        model=args.model,
        threads=args.threads,
    )
