from contextvars import ContextVar
from typing import Any

_steps_var: ContextVar[list[dict] | None] = ContextVar("_steps", default=None)


def start_trace() -> None:
    _steps_var.set([])


def record_step(module: str, prompt: Any, response: Any) -> None:
    steps = _steps_var.get()
    if steps is not None:
        steps.append({
            "module": module,
            "prompt": prompt if isinstance(prompt, dict) else {"content": str(prompt)},
            "response": response if isinstance(response, dict) else {"content": str(response)},
        })


def get_steps() -> list[dict]:
    return list(_steps_var.get() or [])
