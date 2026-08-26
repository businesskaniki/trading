from dataclasses import dataclass


@dataclass(frozen=True)
class EngineSettings:
    mode: str = "paper"
    config_dir: str = "configs"
