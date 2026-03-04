import json
import operator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from datetime import datetime, timedelta
from typing import Annotated

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from agents.supervisor import SupervisorAgent
from config import Config
from data.market import YFinanceSource
from models.market import HoldingSnapshot, MarketEvent
from models.signals import GuardianSignal, Notification, ScoutSignal
from models.user import UserProfile
from notifier import Notifier
from portfolio.manager import PortfolioManager
from portfolio.models import Holding
from profile.manager import UserProfileManager
from systems.guardian_system import GuardianSystem
from systems.scout_system import ScoutSystem


# --- State ---

class FinerisState(TypedDict):
    user_profile: UserProfile
    portfolio_snapshot: list[HoldingSnapshot]
    available_budget: float
    market_events: list[MarketEvent]
    guardian_signals: Annotated[list[GuardianSignal], operator.add]
    scout_signals: Annotated[list[ScoutSignal], operator.add]
    notifications: list[Notification]
    errors: Annotated[list[str], operator.add]


# --- System ---

class FinerisSystem:
    """Orchestrates Guardian + Scout + Supervisor via LangGraph."""

    def __init__(self, model: str = Config.MODEL) -> None:
        print(f"[FinerisSystem] Initializing with model: {model}")
        self._portfolio = PortfolioManager()
        self._profile_mgr = UserProfileManager()
        self._data = YFinanceSource()
        self._supervisor = SupervisorAgent(model=model)
        self._guardian_system = GuardianSystem(model=model)
        self._scout_system = ScoutSystem(model=model)
        self._notifier = Notifier()
        self._seen_news: set[str] = self._load_seen_news()
        self._cooldowns: dict[str, str] = self._load_cooldowns()
        self._graph = self._build_graph()
        self._override: dict | None = None  # set by run_cycle_with_data
        self._ephemeral: bool = False       # True = skip all persistence (API calls)

    # --- Persistence helpers ---

    def _load_seen_news(self) -> set[str]:
        path = Config.SEEN_NEWS_FILE
        if path.exists():
            return set(json.loads(path.read_text()))
        return set()

    def _save_seen_news(self) -> None:
        if not self._ephemeral:
            Config.SEEN_NEWS_FILE.write_text(json.dumps(list(self._seen_news), indent=2))

    def _load_cooldowns(self) -> dict[str, str]:
        path = Config.STORAGE_DIR / "cooldowns.json"
        if path.exists():
            return json.loads(path.read_text())
        return {}

    def _save_cooldowns(self) -> None:
        if not self._ephemeral:
            path = Config.STORAGE_DIR / "cooldowns.json"
            path.write_text(json.dumps(self._cooldowns, indent=2))

    def _is_on_cooldown(self, ticker: str) -> bool:
        if ticker not in self._cooldowns:
            return False
        last = datetime.fromisoformat(self._cooldowns[ticker])
        return datetime.now() - last < timedelta(hours=Config.COOLDOWN_HOURS)

    def _set_cooldown(self, ticker: str) -> None:
        self._cooldowns[ticker] = datetime.now().isoformat()
        self._save_cooldowns()

    # --- Helpers ---

    @staticmethod
    def _build_snapshots(holdings: list[Holding], current_prices: dict[str, float]) -> list[HoldingSnapshot]:
        total_value = sum(
            h.quantity * current_prices.get(h.ticker, h.avg_buy_price)
            for h in holdings
        )
        snapshots = []
        for h in holdings:
            price = current_prices.get(h.ticker, h.avg_buy_price)
            value = h.quantity * price
            snapshots.append(HoldingSnapshot(
                ticker=h.ticker,
                quantity=h.quantity,
                avg_buy_price=h.avg_buy_price,
                current_price=price,
                current_value=value,
                unrealized_pnl=(price - h.avg_buy_price) * h.quantity,
                portfolio_weight=value / total_value if total_value > 0 else 0.0,
            ))
        return snapshots

    # --- Graph nodes ---

    def _prepare_node(self, state: FinerisState) -> dict:
        """Fetch portfolio snapshot + market events for held tickers."""
        errors = []
        if self._override:
            profile = self._override["profile"]
            holdings = self._override["holdings"]
            available_budget = self._override["budget"]
        else:
            profile = self._profile_mgr.get_profile()
            holdings = self._portfolio.get_all_holdings()
            available_budget = self._portfolio.get_budget()

        # Build current prices map
        current_prices: dict[str, float] = {}
        for h in holdings:
            try:
                current_prices[h.ticker] = self._data.get_price(h.ticker)
            except Exception as e:
                errors.append(f"Price fetch failed for {h.ticker}: {e}")

        portfolio_snapshot = self._build_snapshots(holdings, current_prices)

        # Build market events for held tickers
        market_events: list[MarketEvent] = []
        for h in holdings:
            if h.ticker not in current_prices:
                continue
            try:
                snapshot = self._data.get_snapshot(h.ticker)
                news_items = self._data.get_news(h.ticker)
                # Filter unseen news (skipped in demo mode)
                if Config.FILTER_SEEN_NEWS:
                    new_news = [n for n in news_items if n.url not in self._seen_news]
                    for n in new_news:
                        if n.url:
                            self._seen_news.add(n.url)
                else:
                    new_news = news_items
                if new_news or snapshot.change_pct <= -Config.DROP_THRESHOLDS[profile.risk_level]:
                    market_events.append(MarketEvent(
                        ticker=h.ticker,
                        snapshot=snapshot,
                        news=new_news,
                    ))
            except Exception as e:
                errors.append(f"Event fetch failed for {h.ticker}: {e}")

        self._save_seen_news()

        return {
            "user_profile": profile,
            "portfolio_snapshot": portfolio_snapshot,
            "available_budget": available_budget,
            "market_events": market_events,
            "guardian_signals": [],
            "scout_signals": [],
            "notifications": [],
            "errors": errors,
        }

    def _analyze_node(self, state: FinerisState) -> dict:
        """Run Guardian (parallel) + Scout (sequential) for all signals."""
        guardian_signals: list[GuardianSignal] = []
        scout_signals: list[ScoutSignal] = []
        errors: list[str] = []

        snapshot_map = {s.ticker: s for s in state["portfolio_snapshot"]}
        profile = state["user_profile"]

        # --- Guardian: parallel across events ---
        events_to_guard = [
            event for event in state["market_events"]
            if not self._is_on_cooldown(event.ticker)
            and event.ticker in snapshot_map
            and self._supervisor.should_trigger_guardian(event, profile)
        ]

        def run_guardian(event: MarketEvent) -> GuardianSignal | None:
            try:
                return self._guardian_system.run(
                    event=event,
                    snapshot=snapshot_map[event.ticker],
                    profile=profile,
                )
            except Exception as e:
                errors.append(f"Guardian failed for {event.ticker}: {e}")
                return None

        ctx = copy_context()
        with ThreadPoolExecutor() as executor:
            futures = {executor.submit(ctx.run, run_guardian, event): event for event in events_to_guard}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    guardian_signals.append(result)
                    self._set_cooldown(result.ticker)

        # --- Scout: sequential over watchlist ---
        weights = {s.ticker: s.portfolio_weight for s in state["portfolio_snapshot"]}
        for ticker in profile.watchlist:
            try:
                signal = self._scout_system.run(
                    ticker=ticker,
                    profile=profile,
                    budget=state["available_budget"],
                    portfolio_weights=weights,
                )
                scout_signals.append(signal)
            except Exception as e:
                errors.append(f"Scout failed for {ticker}: {e}")

        return {
            "guardian_signals": guardian_signals,
            "scout_signals": scout_signals,
            "errors": errors,
        }

    def _notify_node(self, state: FinerisState) -> dict:
        """Synthesize all signals into notifications and fire them."""
        notifications = self._supervisor.synthesize(
            guardian_signals=state["guardian_signals"],
            scout_signals=state["scout_signals"],
        )
        for notification in notifications:
            if not self._ephemeral:
                self._notifier.send(notification)
        return {"notifications": notifications}

    # --- Graph wiring ---

    def _build_graph(self):
        graph = StateGraph(FinerisState)
        graph.add_node("prepare", self._prepare_node)
        graph.add_node("analyze", self._analyze_node)
        graph.add_node("notify", self._notify_node)
        graph.set_entry_point("prepare")
        graph.add_edge("prepare", "analyze")
        graph.add_edge("analyze", "notify")
        graph.add_edge("notify", END)
        return graph.compile()

    # --- Public API ---

    def run_cycle(self) -> list[Notification]:
        """Run one full FINERIS cycle. Call this from your loop."""
        holdings = self._portfolio.get_all_holdings()
        profile = self._profile_mgr.get_profile()

        if not holdings and not profile.watchlist:
            print("[FINERIS] Nothing to do — no holdings and no watchlist.")
            print("  Add a holding : python manage.py portfolio add -t TICKER -q QTY -p PRICE")
            print("  Add to watchlist: python manage.py profile add-watch -v TICKER")
            return []

        result = self._graph.invoke({
            "user_profile": None,
            "portfolio_snapshot": [],
            "available_budget": 0.0,
            "market_events": [],
            "guardian_signals": [],
            "scout_signals": [],
            "notifications": [],
            "errors": [],
        })
        if result.get("errors"):
            for err in result["errors"]:
                print(f"[ERROR] {err}")
        return result.get("notifications", [])

    def run_cycle_with_data(
        self,
        holdings: list[Holding],
        budget: float,
        profile: UserProfile,
    ) -> list[Notification]:
        """Run one FINERIS cycle with injected portfolio/profile (no JSON storage reads)."""
        if not holdings and not profile.watchlist:
            return []
        self._override = {"holdings": holdings, "budget": budget, "profile": profile}
        self._ephemeral = True
        try:
            result = self._graph.invoke({
                "user_profile": None,
                "portfolio_snapshot": [],
                "available_budget": 0.0,
                "market_events": [],
                "guardian_signals": [],
                "scout_signals": [],
                "notifications": [],
                "errors": [],
            })
        finally:
            self._override = None
            self._ephemeral = False
        return result.get("notifications", [])
