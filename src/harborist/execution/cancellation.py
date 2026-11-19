"""Cooperative interruption in the synchronous executor and process adapter."""

from collections.abc import Callable
from contextvars import ContextVar

cancellation_check: ContextVar[Callable[[], bool] | None] = ContextVar(
    "cancellation_check", default=None
)


def check_cancellation() -> None:
    check = cancellation_check.get()
    if check is not None and check():
        raise KeyboardInterrupt
