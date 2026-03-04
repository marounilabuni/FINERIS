import re

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from agents.prompt_parser import PromptParser
from config import Config
from tracing import get_steps, start_trace
from data.market import YFinanceSource
from models.user import UserProfile
from portfolio.manager import PortfolioManager
from portfolio.models import Holding
from profile.manager import UserProfileManager
from systems.fineris import FinerisSystem


# ── Notification log parser ──────────────────────────────────────────────────

def _parse_chunk(chunk: str) -> dict | None:
    """Parse one notification block (may be multi-line)."""
    m = re.match(
        r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] \[(\w+)\] \[(\w+)\]\s*(.*)',
        chunk.strip(),
        re.DOTALL,
    )
    if not m:
        return None

    timestamp, level, agent, rest = m.groups()

    # Handle both ":\n" and " — " separators
    msg_m = re.match(r'\[([^\]]+)\] (\w+)[:\s—]+\s*(.*)', rest.strip(), re.DOTALL)
    if msg_m:
        ticker, recommendation, reasoning = msg_m.groups()
    else:
        ticker, recommendation, reasoning = "", "", rest.strip()

    reasoning = reasoning.strip()
    news_m = re.search(r'\| News analyzed: (\d+)', reasoning)
    news_count = int(news_m.group(1)) if news_m else None

    conf_m = re.search(r'\| Confidence: (\w+)', reasoning)
    confidence = conf_m.group(1) if conf_m else None

    return {
        "timestamp": timestamp,
        "date": timestamp[:10],
        "time": timestamp[11:16],
        "level": level,
        "agent": agent,
        "ticker": ticker,
        "recommendation": recommendation.strip(),
        "reasoning": reasoning,
        "news_count": news_count,
        "confidence": confidence,
    }


def load_notifications() -> list[dict]:
    if not Config.NOTIFICATIONS_FILE.exists():
        return []
    content = Config.NOTIFICATIONS_FILE.read_text()
    # Split at each timestamp boundary to handle multi-line entries
    chunks = re.split(r'(?=\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\])', content)
    notifications = [n for chunk in chunks if (n := _parse_chunk(chunk))]
    return list(reversed(notifications))  # newest first


def group_by_date(notifications: list[dict]) -> list[tuple[str, list[dict]]]:
    grouped: dict[str, list] = {}
    for n in notifications:
        grouped.setdefault(n["date"], []).append(n)
    return sorted(grouped.items(), reverse=True)


# ── Route registration ───────────────────────────────────────────────────────

def register_routes(app: Flask) -> None:

    @app.route("/")
    def dashboard():
        notifications = load_notifications()
        pm = PortfolioManager()
        pfm = UserProfileManager()
        profile = pfm.get_profile()
        last_run = notifications[0]["timestamp"] if notifications else None
        return render_template(
            "dashboard.html",
            grouped=group_by_date(notifications),
            holdings_count=len(pm.get_all_holdings()),
            watchlist_count=len(profile.watchlist),
            budget=pm.get_budget(),
            last_run=last_run,
            available_models=Config.AVAILABLE_MODELS,
        )

    @app.route("/run", methods=["POST"])
    def run_cycle():
        requested = request.form.get("model", "")
        model = requested if requested in Config.AVAILABLE_MODELS else Config.MODEL
        print(f"[/run] Selected model: {model}")
        FinerisSystem(model=model).run_cycle()
        return redirect(url_for("dashboard"))

    # ── Portfolio ────────────────────────────────────────────────────────────

    @app.route("/analyze")
    def analyze():
        return render_template("analyze.html", available_models=Config.AVAILABLE_MODELS)

    @app.route("/portfolio")
    def portfolio():
        pm = PortfolioManager()
        return render_template(
            "portfolio.html",
            holdings=pm.get_all_holdings(),
            budget=pm.get_budget(),
        )

    @app.route("/portfolio/add", methods=["POST"])
    def portfolio_add():
        try:
            resolved = YFinanceSource().resolve_ticker(request.form["ticker"])
            PortfolioManager().add_holding(
                resolved,
                float(request.form["quantity"]),
                float(request.form["price"]),
            )
            flash(f"Added {resolved}", "success")
        except ValueError as e:
            flash(str(e), "danger")
        return redirect(url_for("portfolio"))

    @app.route("/portfolio/update/<ticker>", methods=["POST"])
    def portfolio_update(ticker: str):
        try:
            quantity = float(request.form["quantity"])
            price = float(request.form["price"])
            if quantity <= 0 or price <= 0:
                raise ValueError("Quantity and price must be greater than 0.")
            PortfolioManager().update_holding(ticker, quantity, price)
            flash(f"Updated {ticker}", "success")
        except (ValueError, KeyError) as e:
            flash(str(e), "danger")
        return redirect(url_for("portfolio"))

    @app.route("/portfolio/remove/<ticker>", methods=["POST"])
    def portfolio_remove(ticker: str):
        pm = PortfolioManager()
        try:
            pm.remove_holding(ticker)
            flash(f"Removed {ticker}", "success")
        except KeyError as e:
            flash(str(e), "danger")
        return redirect(url_for("portfolio"))

    @app.route("/portfolio/budget", methods=["POST"])
    def portfolio_budget():
        pm = PortfolioManager()
        pm.set_budget(float(request.form["amount"]))
        flash("Budget updated", "success")
        return redirect(url_for("portfolio"))

    # ── Profile ──────────────────────────────────────────────────────────────

    @app.route("/profile")
    def profile():
        pfm = UserProfileManager()
        return render_template("profile.html", profile=pfm.get_profile())

    @app.route("/profile/update", methods=["POST"])
    def profile_update():
        pfm = UserProfileManager()
        pfm.set_name(request.form["name"])
        pfm.set_risk_level(request.form["risk"])  # type: ignore
        flash("Profile updated", "success")
        return redirect(url_for("profile"))

    @app.route("/profile/watchlist/add", methods=["POST"])
    def watchlist_add():
        try:
            resolved = YFinanceSource().resolve_ticker(request.form["ticker"])
            UserProfileManager().add_to_watchlist(resolved)
            flash(f"Added {resolved} to watchlist", "success")
        except ValueError as e:
            flash(str(e), "danger")
        return redirect(url_for("profile"))

    @app.route("/profile/watchlist/remove/<ticker>", methods=["POST"])
    def watchlist_remove(ticker: str):
        pfm = UserProfileManager()
        pfm.remove_from_watchlist(ticker)
        flash(f"Removed {ticker} from watchlist", "success")
        return redirect(url_for("profile"))

    # ── API ──────────────────────────────────────────────────────────────────

    @app.route("/api/agent_info", methods=["GET"])
    def api_agent_info():
        return jsonify({
            "description": (
                "FINERIS is a multi-agent autonomous portfolio management system. "
                "It consists of three specialized LLM agents — PromptParser (Haiku), "
                "Supervisor (Sonnet), Guardian (Sonnet), and Scout (Sonnet) — "
                "orchestrated via a LangGraph state machine."
            ),
            "purpose": (
                "Given a natural-language investor prompt, FINERIS parses the portfolio, "
                "fetches live market data via yfinance, classifies news sentiment, "
                "evaluates held positions (Guardian: HOLD/SELL), "
                "and scans watchlist candidates (Scout: BUY/PASS), "
                "returning actionable investment alerts."
            ),
            "prompt_template": (
                "Extract investor portfolio and profile information from the user message.\n"
                "Defaults when not mentioned: name='User', risk_level='medium', budget=10000.0, "
                "holdings=[], watchlist=[]\n"
                "risk_level must be exactly one of: low, medium, high\n"
                "For each holding extract: ticker symbol, quantity, avg_buy_price.\n"
                "Watchlist is a list of ticker symbols the user wants to monitor but does not hold.\n\n"
                "User message: {prompt}"
            ),
            "prompt_examples": [
                {
                    "prompt": "I hold 10 TSLA at $200, watch NVDA, medium risk, $5000 budget",
                    "full_response": (
                        "[WARNING] [Guardian] [TSLA] HOLD: Strong unrealized gains (+95%), "
                        "today's decline is macro-driven (oil surge), price action stable. "
                        "No fundamental breakdown detected.\n"
                        "[INFO] [Scout] [NVDA] PASS: Recent high-volume selloff signals "
                        "distribution; wait for clearer technical base before entering."
                    ),
                    "steps": [
                        {
                            "module": "PromptParser",
                            "prompt": {
                                "content": (
                                    "Extract investor portfolio and profile information from the user message.\n"
                                    "Defaults when not mentioned: name='User', risk_level='medium', budget=10000.0, "
                                    "holdings=[], watchlist=[]\n"
                                    "risk_level must be exactly one of: low, medium, high\n"
                                    "For each holding extract: ticker symbol, quantity, avg_buy_price.\n"
                                    "Watchlist is a list of ticker symbols the user wants to monitor but does not hold.\n\n"
                                    "User message: I hold 10 TSLA at $200, watch NVDA, medium risk, $5000 budget"
                                )
                            },
                            "response": {
                                "name": "User",
                                "risk_level": "medium",
                                "budget": 5000.0,
                                "holdings": [{"ticker": "TSLA", "quantity": 10.0, "avg_buy_price": 200.0}],
                                "watchlist": ["NVDA"],
                            },
                        },
                        {
                            "module": "Supervisor.classify_news_sentiments",
                            "prompt": {"content": "Classify the sentiment of each financial news item as POSITIVE, NEGATIVE, or NEUTRAL.\n\n1. Headline: Tesla Stock Falls as Investors Wait for Its New Robot..."},
                            "response": {"sentiments": ["NEGATIVE", "MIXED", "NEGATIVE", "POSITIVE", "MIXED"]},
                        },
                        {
                            "module": "GuardianAgent",
                            "prompt": {"content": "You are a defensive financial analyst protecting a medium-risk investor's portfolio.\n\nHOLDING: TSLA\n- Quantity: 10 shares\n- Avg buy price: $200.00\n- Current price: $391.45\n..."},
                            "response": {
                                "recommendation": "HOLD",
                                "reasoning": "Strong unrealized gains (+95.7%), macro-driven decline, no fundamental breakdown.",
                                "historical_context": "TSLA has rewarded patient holders through prior volatility episodes.",
                            },
                        },
                        {
                            "module": "Supervisor.classify_news_sentiments",
                            "prompt": {"content": "Classify the sentiment of each financial news item as POSITIVE, NEGATIVE, or NEUTRAL.\n\n1. Headline: Nvidia Just Dumped Its Entire $182 Million Applied Digital Stake..."},
                            "response": {"sentiments": ["POSITIVE", "NEGATIVE", "NEUTRAL", "POSITIVE", "NEGATIVE"]},
                        },
                        {
                            "module": "ScoutAgent",
                            "prompt": {"content": "You are an opportunistic financial analyst hunting growth investments for a medium-risk investor.\n\nCANDIDATE: NVDA\n- Momentum (30d): 0.9%\n..."},
                            "response": {
                                "recommendation": "PASS",
                                "confidence": "medium",
                                "reasoning": "High-volume selloff signals distribution; wait for clearer technical base.",
                            },
                        },
                    ],
                }
            ],
        })

    @app.route("/api/execute", methods=["POST"])
    def api_execute():
        body = request.get_json(silent=True) or {}
        prompt = body.get("prompt", "").strip()
        if not prompt:
            return jsonify({"status": "error", "error": "prompt is required", "response": "", "steps": []}), 400

        # 1. Resolve model (optional — defaults to Config.MODEL if missing/invalid)
        requested_model = body.get("model", "")
        model = requested_model if requested_model in Config.AVAILABLE_MODELS else Config.MODEL

        start_trace()

        # 2. Parse prompt → profile + portfolio (always Haiku)
        try:
            parsed = PromptParser().parse(prompt)
        except Exception as e:
            return jsonify({"status": "error", "error": f"Parsing failed: {e}", "response": "", "steps": []}), 500

        # 3. Validate tickers (holdings + watchlist)
        market = YFinanceSource()
        holdings: list[Holding] = []
        invalid: list[str] = []

        for h in parsed.holdings:
            if h.quantity <= 0 or h.avg_buy_price <= 0:
                invalid.append(h.ticker)
                continue
            try:
                resolved = market.resolve_ticker(h.ticker)
                holdings.append(Holding(ticker=resolved, quantity=h.quantity, avg_buy_price=h.avg_buy_price))
            except ValueError:
                invalid.append(h.ticker)

        watchlist: list[str] = []
        for t in parsed.watchlist:
            try:
                watchlist.append(market.resolve_ticker(t))
            except ValueError:
                invalid.append(t)

        profile = UserProfile(
            name=parsed.name,
            risk_level=parsed.risk_level,
            watchlist=watchlist,
        )

        # 4. Run cycle
        try:
            notifications, cycle_errors = FinerisSystem(model=model).run_cycle_with_data(holdings, parsed.budget, profile)  # type: ignore[misc]
        except Exception as e:
            return jsonify({"status": "error", "error": f"Cycle failed: {e}", "response": "", "steps": []}), 500

        # 4. Build response
        response_lines = []
        if invalid:
            response_lines.append(f"Skipped invalid tickers: {', '.join(invalid)}")
        if cycle_errors:
            for err in cycle_errors:
                response_lines.append(f"[ERROR] {err}")
        if not notifications:
            response_lines.append("No alerts generated for the given portfolio/watchlist.")
        for n in notifications:
            response_lines.append(f"[{n.level}] [{n.agent}] {n.message}")

        return jsonify({
            "status": "ok",
            "error": None,
            "response": "\n".join(response_lines),
            "steps": get_steps(),
        })
