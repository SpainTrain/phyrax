"""Structured logging setup for Phyrax."""

from __future__ import annotations

import logging
import os

from phyrax.config import STATE_DIR


def setup_logging() -> None:
    """Configure the 'phyrax' logger. Safe to call multiple times (idempotent)."""
    logger = logging.getLogger("phyrax")
    if logger.handlers:
        return  # already configured

    level_name = os.environ.get("PHYRAX_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    log_file = STATE_DIR / "phyrax.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setLevel(level)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(module)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(fmt)
    logger.addHandler(handler)
