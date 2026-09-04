from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_path: Path, verbose: bool = False) -> None:
    handlers: list[logging.Handler]
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers = [
            RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        ]
    except OSError:
        handlers = []
    if verbose:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
