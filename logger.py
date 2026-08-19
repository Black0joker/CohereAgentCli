"""Application logging.

Single responsibility: configure and provide loggers.

All log records go to logs/agent.log ONLY (nothing is printed to the
console): full detail including tracebacks, rotated (1 MB x 3).

No agent logic.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "agent.log")
MAX_BYTES = 1_000_000   # 1 MB per log file
BACKUP_COUNT = 3
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def setup_logging() -> logging.Logger:
    """Configure the 'agent' logger once (file-only) and return it."""
    global _configured
    logger = logging.getLogger("agent")
    if _configured:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # File handler: everything incl. tracebacks, rotated. No console handler -
    # logs must never pollute the interactive UI.
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        logger.addHandler(file_handler)
        logger.info("logging initialized (file: %s)", LOG_FILE)
    except OSError:
        # Logging must never crash the agent; run silently without handlers.
        pass

    _configured = True
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'agent' namespace."""
    return logging.getLogger(f"agent.{name}")
