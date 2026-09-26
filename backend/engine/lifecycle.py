from __future__ import annotations

from typing import Any


async def start_if_supported(component: Any) -> bool:
    """
    Start a component when it exposes an async start() method.

    Returns True when start() was called.
    Returns False when the component has no lifecycle start method.
    """

    method = getattr(component, "start", None)

    if method is None:
        return False

    await method()

    return True


async def stop_if_supported(component: Any) -> bool:
    """
    Stop a component when it exposes an async stop() method.

    Returns True when stop() was called.
    Returns False when the component has no lifecycle stop method.
    """

    method = getattr(component, "stop", None)

    if method is None:
        return False

    await method()

    return True
