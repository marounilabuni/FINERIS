"""CLI for managing portfolio and user profile."""
import argparse

from dotenv import load_dotenv

load_dotenv()

from portfolio.manager import PortfolioManager
from profile.manager import UserProfileManager


def portfolio_commands(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("action", choices=["add", "remove", "update", "list"])
    sub.add_argument("--ticker", "-t")
    sub.add_argument("--quantity", "-q", type=float)
    sub.add_argument("--price", "-p", type=float, help="Avg buy price")


def budget_commands(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("action", choices=["get", "set"])
    sub.add_argument("--amount", "-a", type=float)


def profile_commands(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("action", choices=["show", "set-risk", "add-watch", "remove-watch", "set-name"])
    sub.add_argument("--value", "-v")


def main() -> None:
    parser = argparse.ArgumentParser(description="FINERIS Management CLI")
    subs = parser.add_subparsers(dest="command")

    portfolio_commands(subs.add_parser("portfolio", help="Manage holdings"))
    budget_commands(subs.add_parser("budget", help="Manage budget"))
    profile_commands(subs.add_parser("profile", help="Manage user profile"))

    args = parser.parse_args()

    pm = PortfolioManager()
    pfm = UserProfileManager()

    if args.command == "portfolio":
        if args.action == "add":
            pm.add_holding(args.ticker.upper(), args.quantity, args.price)
            print(f"Added {args.ticker.upper()}: {args.quantity} @ ${args.price}")
        elif args.action == "remove":
            try:
                pm.remove_holding(args.ticker.upper())
                print(f"Removed {args.ticker.upper()}")
            except KeyError as e:
                print(f"Error: {e}")
        elif args.action == "update":
            try:
                pm.update_holding(args.ticker.upper(), args.quantity, args.price)
                print(f"Updated {args.ticker.upper()}: {args.quantity} @ ${args.price}")
            except KeyError as e:
                print(f"Error: {e}")
        elif args.action == "list":
            holdings = pm.get_all_holdings()
            if not holdings:
                print("No holdings.")
            for h in holdings:
                print(f"  {h.ticker}: {h.quantity} shares @ ${h.avg_buy_price:.2f}")

    elif args.command == "budget":
        if args.action == "get":
            print(f"Budget: ${pm.get_budget():.2f}")
        elif args.action == "set":
            pm.set_budget(args.amount)
            print(f"Budget set to ${args.amount:.2f}")

    elif args.command == "profile":
        if args.action == "show":
            p = pfm.get_profile()
            print(f"Name: {p.name}")
            print(f"Risk: {p.risk_level}")
            print(f"Watchlist: {', '.join(p.watchlist) or 'empty'}")
        elif args.action == "set-risk":
            pfm.set_risk_level(args.value)  # type: ignore
            print(f"Risk level set to {args.value}")
        elif args.action == "set-name":
            pfm.set_name(args.value)
            print(f"Name set to {args.value}")
        elif args.action == "add-watch":
            pfm.add_to_watchlist(args.value)
            print(f"Added {args.value.upper()} to watchlist")
        elif args.action == "remove-watch":
            pfm.remove_from_watchlist(args.value)
            print(f"Removed {args.value.upper()} from watchlist")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
