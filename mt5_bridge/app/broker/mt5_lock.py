
from __future__ import annotations

from functools import wraps
from threading import RLock
from typing import Any, Callable, ParamSpec, TypeVar


P = ParamSpec("P")
R = TypeVar("R")

# One process-wide reentrant lock for the MT5 Python API.
#
# RLock allows a synchronized operation to call another synchronized
# operation in the same thread without deadlocking.
MT5_API_LOCK = RLock()


def mt5_synchronized(
    function: Callable[P, R],
) -> Callable[P, R]:
    """
    Serialize a synchronous operation that accesses the MT5 API.

    Use this decorator on complete logical operations, not merely
    individual MT5 calls, so connection recovery cannot interrupt
    a protected sequence of MT5 operations.
    """

    @wraps(function)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with MT5_API_LOCK:
            return function(*args, **kwargs)

    return wrapper
