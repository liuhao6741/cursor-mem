"""Configuration management, path constants, and logging."""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.environ.get("CURSOR_MEM_DATA_DIR", Path.home() / ".cursor-mem"))
DB_PATH = DATA_DIR / "cursor-mem.db"
CONFIG_PATH = DATA_DIR / "config.json"
PID_FILE = DATA_DIR / "worker.pid"
LOG_DIR = DATA_DIR / "logs"

DEFAULT_PORT = 37800


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class AIConfig:
    enabled: bool = False
    base_url: str = ""
    api_key: str = ""
    model: str = ""


@dataclass
class Config:
    port: int = DEFAULT_PORT
    context_budget: int = 4000
    max_sessions_in_context: int = 3
    log_level: str = "INFO"
    ai: AIConfig = field(default_factory=AIConfig)

    # ---- persistence ----

    @classmethod
    def load(cls) -> "Config":
        if CONFIG_PATH.exists():
            try:
                raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                ai_raw = raw.pop("ai", {})
                ai = AIConfig(**{k: v for k, v in ai_raw.items() if k in AIConfig.__dataclass_fields__})
                return cls(
                    **{k: v for k, v in raw.items() if k in cls.__dataclass_fields__},
                    ai=ai,
                )
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        d = asdict(self)
        CONFIG_PATH.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")

    def set_nested(self, key: str, value: Any) -> None:
        """Set a dotted key like 'ai.enabled'."""
        parts = key.split(".")
        if len(parts) == 1:
            if parts[0] in self.__dataclass_fields__:
                ftype = self.__dataclass_fields__[parts[0]].type
                if ftype == "int":
                    value = int(value)
                elif ftype == "bool":
                    value = value.lower() in ("true", "1", "yes")
                setattr(self, parts[0], value)
        elif len(parts) == 2 and parts[0] == "ai":
            attr = parts[1]
            if attr in AIConfig.__dataclass_fields__:
                ftype = AIConfig.__dataclass_fields__[attr].type
                if ftype == "bool":
                    value = value.lower() in ("true", "1", "yes")
                elif ftype == "int":
                    value = int(value)
                setattr(self.ai, attr, value)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(level: str | None = None) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = Config.load() if level is None else None
    log_level = level or (cfg.log_level if cfg else "INFO")

    logger = logging.getLogger("cursor_mem")
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    fh = logging.FileHandler(LOG_DIR / "cursor-mem.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    if sys.stderr.isatty():
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)

    return logger
