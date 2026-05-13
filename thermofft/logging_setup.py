from __future__ import annotations

import logging
from pathlib import Path

from rich.logging import RichHandler


def setup_logging(level: str = "INFO", log_file: Path | None = None) -> logging.Logger:
    """Настроить root logger: RichHandler + опциональный file handler."""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level.upper())

    rich_handler = RichHandler(rich_tracebacks=True, show_path=False, show_time=True)
    rich_handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(rich_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        root.addHandler(fh)

    return logging.getLogger("thermofft")
