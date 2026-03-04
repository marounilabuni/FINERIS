import json
from pathlib import Path
from typing import Any


class BaseJsonManager:
    def __init__(self, filepath: Path) -> None:
        self._filepath = filepath
        self._filepath.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Any:
        if not self._filepath.exists():
            return None
        with open(self._filepath, "r") as f:
            return json.load(f)

    def _save(self, data: Any) -> None:
        with open(self._filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)
