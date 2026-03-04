import time
from datetime import datetime

import yfinance as yf

from data.base import BaseDataSource
from models.market import NewsItem, StockSnapshot


def _yf_ticker(ticker: str) -> yf.Ticker:
    """Return a yfinance Ticker with a browser-like User-Agent to reduce rate limiting."""
    t = yf.Ticker(ticker)
    try:
        t.session.headers.update({  # type: ignore[union-attr]
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        })
    except Exception:
        pass
    return t


def _with_retry(fn, retries: int = 3, delay: float = 2.0):
    """Call fn(), retrying up to `retries` times on rate-limit errors."""
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            if attempt < retries - 1 and "too many requests" in str(e).lower():
                time.sleep(delay * (attempt + 1))
            else:
                raise


class YFinanceSource(BaseDataSource):

    def resolve_ticker(self, raw: str) -> str:
        upper = raw.upper()
        candidates = [f"{upper}-USD", upper] if "-" not in upper else [upper]
        for candidate in candidates:
            try:
                df = _with_retry(lambda c=candidate: _yf_ticker(c).history(period="2d"))
                if not df.empty:
                    return candidate
            except Exception:
                continue
        raise ValueError(f"Ticker '{upper}' not found. Please check the symbol.")

    def get_price(self, ticker: str) -> float:
        df = _with_retry(lambda: _yf_ticker(ticker).history(period="2d"))
        if df.empty:
            return 0.0
        return float(df["Close"].iloc[-1])

    def get_snapshot(self, ticker: str) -> StockSnapshot:
        df = _with_retry(lambda: _yf_ticker(ticker).history(period="2d"))
        if df.empty:
            raise ValueError(f"No price data available for {ticker}")
        current_price = float(df["Close"].iloc[-1])
        prev_close = float(df["Close"].iloc[-2]) if len(df) > 1 else current_price
        change_pct = (current_price - prev_close) / prev_close if prev_close else 0.0
        volume = float(df["Volume"].iloc[-1])
        return StockSnapshot(
            ticker=ticker,
            current_price=current_price,
            change_pct=change_pct,
            volume=volume,
            timestamp=datetime.now(),
        )

    def get_news(self, ticker: str) -> list[NewsItem]:
        raw_news = _with_retry(lambda: _yf_ticker(ticker).news) or []
        items = []
        for item in raw_news:
            content = item.get("content", {})
            title = content.get("title", "")
            summary = content.get("summary", "")
            pub_date = content.get("pubDate", "")
            news_id = item.get("id", "")
            url = content.get("canonicalUrl", {}).get("url", "") if isinstance(content.get("canonicalUrl"), dict) else ""
            try:
                published_at = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
            except Exception:
                published_at = datetime.now()
            if title:
                items.append(NewsItem(
                    ticker=ticker,
                    headline=title,
                    summary=summary,
                    published_at=published_at,
                    url=news_id or url,
                ))
        return items

    def get_history(self, ticker: str, period: str = "30d") -> list[dict]:
        df = _with_retry(lambda: _yf_ticker(ticker).history(period=period))
        if df.empty:
            return []
        df = df.reset_index()
        return [
            {
                "date": str(row["Date"])[:10],
                "open": row["Open"],
                "high": row["High"],
                "low": row["Low"],
                "close": row["Close"],
                "volume": row["Volume"],
            }
            for _, row in df.iterrows()
        ]

    def get_fundamentals(self, ticker: str) -> dict:
        info = _with_retry(lambda: _yf_ticker(ticker).info)
        return {
            "pe_ratio": info.get("trailingPE"),
            "market_cap": info.get("marketCap"),
            "earnings_growth": info.get("earningsGrowth"),
            "revenue_growth": info.get("revenueGrowth"),
            "sector": info.get("sector"),
        }
