from datetime import datetime

import yfinance as yf

from data.base import BaseDataSource
from models.market import NewsItem, StockSnapshot


class YFinanceSource(BaseDataSource):

    def resolve_ticker(self, raw: str) -> str:
        """Resolve user input to a valid yfinance ticker.
        Tries {raw}-USD first (crypto), then raw as-is (stocks).
        Returns the resolved ticker or raises ValueError.
        """
        upper = raw.upper()
        # Try crypto form first to avoid BTC resolving to an unrelated stock
        candidates = [f"{upper}-USD", upper] if "-" not in upper else [upper]
        for candidate in candidates:
            try:
                df = yf.Ticker(candidate).history(period="2d")
                if not df.empty:
                    return candidate
            except Exception:
                continue
        raise ValueError(f"Ticker '{upper}' not found. Please check the symbol.")

    def get_price(self, ticker: str) -> float:
        df = yf.Ticker(ticker).history(period="2d")
        if df.empty:
            return 0.0
        return float(df["Close"].iloc[-1])

    def get_snapshot(self, ticker: str) -> StockSnapshot:
        df = yf.Ticker(ticker).history(period="2d")
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
        raw_news = yf.Ticker(ticker).news or []
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
                    url=news_id or url,  # prefer id for deduplication
                ))
        return items

    def get_history(self, ticker: str, period: str = "30d") -> list[dict]:
        df = yf.Ticker(ticker).history(period=period)
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
        info = yf.Ticker(ticker).info
        return {
            "pe_ratio": info.get("trailingPE"),
            "market_cap": info.get("marketCap"),
            "earnings_growth": info.get("earningsGrowth"),
            "revenue_growth": info.get("revenueGrowth"),
            "sector": info.get("sector"),
        }
