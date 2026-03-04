"""FINERIS entry point. Run one cycle or loop."""
import time

from dotenv import load_dotenv

load_dotenv()

from config import Config
from systems.fineris import FinerisSystem


def run_once() -> None:
    system = FinerisSystem()
    notifications = system.run_cycle()
    if not notifications:
        print("[FINERIS] Cycle complete — no actionable signals.")


def run_loop(interval_minutes: int = Config.NEWS_POLL_INTERVAL_MINUTES) -> None:
    system = FinerisSystem()
    print(f"[FINERIS] Starting loop — polling every {interval_minutes} minutes.")
    loop_count = 0
    while True:
        loop_count += 1
        print()
        print("-"*100)
        print()
        print(f"Loop {loop_count} — Running cycle...")
        print()
        print("-"*100)
        try:
            notifications = system.run_cycle()
            if not notifications:
                print("[FINERIS] No actionable signals this cycle.")
        except Exception as e:
            print(f"[FINERIS] Cycle error: {e}")
        time.sleep(interval_minutes * 60)


if __name__ == "__main__":
    #run_once()
    run_loop()