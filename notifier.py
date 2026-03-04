from config import Config
from models.signals import Notification


class Notifier:

    def send(self, notification: Notification) -> None:
        line = (
            f"[{notification.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"[{notification.level}] "
            f"[{notification.agent}]\n"
            f"{notification.message}"
        )
        print(line)
        print()
        print('-'*100)
        print()
        self._write(line)

    def _write(self, line: str) -> None:
        Config.NOTIFICATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(Config.NOTIFICATIONS_FILE, "a") as f:
            f.write(line + "\n")
