from __future__ import annotations

import logging
import sys

_LOGGER_NAME = "compras_crawler"
_configured = False


def configure_logging(level: str | int = "INFO") -> logging.Logger:
    global _configured
    numeric_level = getattr(logging, str(level).upper(), logging.INFO) if isinstance(level, str) else level
    if not _configured:
        logging.basicConfig(
            level=numeric_level,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            stream=sys.stderr,
        )
        _configured = True
    else:
        logging.getLogger().setLevel(numeric_level)
    return logging.getLogger(_LOGGER_NAME)


def get_logger(name: str | None = None) -> logging.Logger:
    if name:
        return logging.getLogger(f"{_LOGGER_NAME}.{name}")
    return logging.getLogger(_LOGGER_NAME)
