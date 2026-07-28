"""Structured technical logging with size-based rotation."""

import logging
from logging.handlers import RotatingFileHandler

from app.config import get_settings


def configure_logging() -> None:
    """Configure console and rotating file handlers once."""

    settings = get_settings()
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if getattr(root, "_kanban_configured", False):
        return

    root.setLevel(settings.log_level)
    formatter = logging.Formatter(
        "%(asctime)sZ %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    formatter.converter = __import__("time").gmtime

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        settings.log_dir / "kanban-backend.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(console)
    root.addHandler(file_handler)
    root._kanban_configured = True  # type: ignore[attr-defined]

