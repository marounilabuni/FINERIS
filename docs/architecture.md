# FINERIS Architecture

## Folder Structure
```
fineris/
├── .env
├── config.py                  # all constants (models, thresholds, paths)
├── utils.py                   # BaseJsonManager (load/save JSON)
├── manage.py                  # CLI for portfolio + profile CRUD
├── app.py                     # Flask entry point
├── notifier.py                # writes to notifications.log + console
├── models/
│   ├── user.py                # UserProfile, RiskLevel
│   ├── market.py              # StockSnapshot, NewsItem, MarketEvent, HoldingSnapshot
│   └── signals.py             # GuardianSignal, ScoutSignal, Notification
├── portfolio/
│   ├── models.py              # Holding
│   └── manager.py             # PortfolioManager (CRUD + budget + snapshots)
├── profile/
│   └── manager.py             # UserProfileManager (name, risk, watchlist)
├── data/
│   ├── base.py                # BaseDataSource ABC
│   └── market.py              # YFinanceSource (all market data)
├── agents/
│   ├── base.py                # BaseAgent ABC
│   ├── guardian.py            # GuardianAgent — HOLD/SELL decision
│   ├── scout.py               # ScoutAgent — BUY/PASS decision
│   ├── supervisor.py          # SupervisorAgent — sentiment + synthesize
│   └── prompt_parser.py       # PromptParser — Haiku extracts portfolio from prompt
├── systems/
│   ├── guardian_system.py     # wires GuardianAgent + data fetch
│   ├── scout_system.py        # wires ScoutAgent + data fetch + news summary
│   └── fineris.py             # LangGraph orchestrator
├── web/
│   ├── routes.py              # all Flask routes + /api/execute
│   └── templates/             # dashboard, portfolio, profile pages
└── storage/
    ├── portfolio.json
    ├── user_profile.json
    ├── seen_news.json
    ├── cooldowns.json
    └── notifications.log
```

---

## LangGraph Flow
```
[prepare] → [analyze] → [notify] → END
```

**prepare**: fetch prices, build snapshots, fetch + filter news, build MarketEvents
**analyze**: Supervisor decides → Guardian runs (parallel) + Scout runs (sequential)
**notify**: synthesize signals → Notifications → write to log

---

## Data Layer — YFinanceSource
All market data from yfinance only.

| Method | Returns |
|--------|---------|
| `get_price(ticker)` | latest close price |
| `get_snapshot(ticker)` | current price, % change today, volume |
| `get_news(ticker)` | headlines + summaries from Yahoo Finance |
| `get_history(ticker, period)` | daily OHLCV candles |
| `get_fundamentals(ticker)` | P/E, market cap, sector, earnings growth |
| `resolve_ticker(raw)` | validates ticker; tries `{X}-USD` first (crypto), then raw |

---

## Supervisor Agent
**No trading decisions** — orchestration + utilities only.

### `classify_news_sentiments(news_items)`
- Input: list of news items (any ticker)
- One LLM call (Sonnet, temp=0), all items batched
- Output: `["POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"]` per item

### `should_trigger_guardian(event, profile) → bool`
- Checks: `price_drop > DROP_THRESHOLD[risk]` OR any news is NEGATIVE
- No LLM call — uses sentiment results from above

### `synthesize(guardian_signals, scout_signals) → list[Notification]`
- No LLM call — maps signals to Notification levels:
  - Guardian SELL → ACTION | Guardian HOLD → WARNING
  - Scout BUY → ACTION | Scout PASS → INFO

---

## Guardian System + Agent
**Purpose:** Protect held positions. Only runs when Supervisor triggers it.

**GuardianSystem** fetches 30d price history → calls GuardianAgent.

**GuardianAgent prompt includes:**
- Holding: qty, avg buy price, current value, unrealized PnL, portfolio weight
- Today: price change %, news headlines + summaries
- History: last 10 daily candles

**Output:** `HOLD` or `SELL` + reasoning + historical context

**Runs in parallel** across all triggered tickers (ThreadPoolExecutor).

**Risk thresholds:** `low=2%, medium=3%, high=5%`

---

## Scout System + Agent
**Purpose:** Find buying opportunities on the watchlist.

**ScoutSystem** fetches: 30d history, fundamentals, news → runs sentiment on top 5 news → builds labeled news summary → calls ScoutAgent.

**ScoutAgent computes momentum locally:**
```python
momentum = (last_close - first_close) / first_close  # over 30d
```

**ScoutAgent prompt includes:**
- 30d momentum score
- Last 14 candles
- Fundamentals (P/E, market cap, sector, earnings growth)
- News summary with [SENTIMENT] labels
- Available budget + current portfolio weight of ticker
- Risk level

**Output:** `BUY` or `PASS` + reasoning

**Runs sequentially** over watchlist tickers.

---

## LangGraph State
```python
class FinerisState(TypedDict):
    user_profile: UserProfile
    portfolio_snapshot: list[HoldingSnapshot]
    available_budget: float
    market_events: list[MarketEvent]
    guardian_signals: list[GuardianSignal]
    scout_signals: list[ScoutSignal]
    notifications: list[Notification]
    errors: list[str]
```

---

## FinerisSystem — prepare_node detail
1. Read holdings + profile (from managers OR `_override` for API)
2. Fetch live prices for all holdings
3. Build HoldingSnapshots (`_build_snapshots`)
4. For each holding: fetch snapshot + news, filter seen news (dedup by URL/id)
5. Create MarketEvent only if: new unseen news OR price dropped past threshold
6. Save seen_news.json (skipped if ephemeral)

---

## Cooldowns
After Guardian fires for a ticker → that ticker is ignored for `COOLDOWN_HOURS` hours.
Prevents repeated alerts for the same event.

---

## Two Entry Points

### `run_cycle()`
- Reads from JSON files (portfolio, profile)
- Saves seen_news, cooldowns, writes to notifications.log
- Used by: web UI "Run" button, CLI main loop

### `run_cycle_with_data(holdings, budget, profile)`
- Bypasses JSON — uses injected data (`_override` flag)
- Ephemeral: no seen_news saved, no cooldowns set, no log written
- Used by: `POST /api/execute`

---

## API Execute Flow
```
POST /api/execute {"prompt": "..."}
  → PromptParser (Haiku) → ParsedPrompt (holdings, budget, risk, watchlist)
  → resolve_ticker() per ticker (validate + normalize)
  → validate quantity > 0 and avg_buy_price > 0
  → run_cycle_with_data()
      → prepare: fetch live prices + news
      → analyze: sentiment → Guardian (parallel) → Scout (sequential)
      → notify: synthesize (no log write)
  → return {"status": "ok", "response": "...", "steps": []}
```

---

## LLM Calls per Request (api/execute)

| Call | Model | Count |
|------|-------|-------|
| PromptParser | Haiku | 1 |
| Sentiment (Guardian path) | Sonnet | 1 per holding with news |
| Guardian | Sonnet | 1 per triggered holding |
| Scout news sentiment | Sonnet | 1 per watchlist ticker |
| Scout decision | Sonnet | 1 per watchlist ticker |

Typical (1 holding + 1 watchlist ticker): **4–5 calls**

---

## Flask Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Dashboard — notifications + summary |
| POST | `/run` | Trigger one cycle |
| GET | `/portfolio` | Holdings table |
| POST | `/portfolio/add` | Add holding (validates ticker) |
| POST | `/portfolio/update/<ticker>` | Edit qty/price |
| POST | `/portfolio/remove/<ticker>` | Remove holding |
| POST | `/portfolio/budget` | Set budget |
| GET | `/profile` | Profile page |
| POST | `/profile/update` | Update name/risk |
| POST | `/profile/watchlist/add` | Add to watchlist (validates ticker) |
| POST | `/profile/watchlist/remove/<ticker>` | Remove from watchlist |
| POST | `/api/execute` | Prompt-driven cycle (stateless) |
