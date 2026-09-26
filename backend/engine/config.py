from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .enums import EngineMode


@dataclass(slots=True)
class EngineConfig:
    """
    Configuration for the top-level AQE Engine.

    Credentials are intentionally excluded from this configuration.
    They are supplied to AQEEngine.start() at runtime.
    """

    mode: EngineMode = EngineMode.PAPER

    auto_reconcile_market_data: bool = True

    start_historical_synchronizer: bool = True

    start_live_tick_hub: bool = True

    disconnect_broker_on_stop: bool = True

    pause_strategies_on_pause: bool = True

    resume_strategies_on_resume: bool = True

    stop_on_component_failure: bool = True

    metadata: dict[str, Any] = field(default_factory=dict)