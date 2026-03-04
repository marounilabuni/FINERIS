from agents.guardian import GuardianAgent
from config import Config
from data.market import YFinanceSource
from models.market import HoldingSnapshot, MarketEvent
from models.signals import GuardianSignal
from models.user import UserProfile


class GuardianSystem:
    """Wires GuardianAgent with its data source. Runnable standalone."""

    def __init__(self, model: str = Config.MODEL) -> None:
        self._agent = GuardianAgent(model=model)
        self._data = YFinanceSource()

    def run(
        self,
        event: MarketEvent,
        snapshot: HoldingSnapshot,
        profile: UserProfile,
    ) -> GuardianSignal:
        history = self._data.get_history(
            event.ticker,
            period=f"{Config.MOMENTUM_WINDOW_DAYS}d",
        )
        return self._agent.run(
            event=event,
            snapshot=snapshot,
            profile=profile,
            history=history,
        )
