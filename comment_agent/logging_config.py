"""Central logging for the comment_agent backend.

The backend historically emitted progress via bare ``print()`` calls plus an
optional ``status_callback`` threaded from the UI, with severity carried in a
bracketed prefix (``[INFO]``, ``[API ERROR]``, ...). This module turns that
convention into real ``logging``: every backend module gets a logger under the
``comment_agent`` namespace, ``configure_logging`` installs console + rotating
file handlers, and ``emit_status`` records a status line at the right level
*and* forwards it to the UI callback so both channels stay in sync.

Library-friendly: importing ``comment_agent`` attaches a ``NullHandler`` (see
``comment_agent/__init__.py``), so modules can log freely without producing
output until an entry point calls ``configure_logging``.
"""

import logging
import logging.handlers
import os
import re

PACKAGE_LOGGER = "comment_agent"

DEFAULT_LEVEL = "INFO"
DEFAULT_LOG_DIR = "logs"
DEFAULT_LOG_FILE = "comment_agent.log"

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_MAX_BYTES = 5 * 1024 * 1024  # 5 MiB per file
_BACKUP_COUNT = 3

# Values that disable the file handler when passed for the log file/dir.
_DISABLED = {"", "none", "off", "0", "false"}

_configured = False


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the ``comment_agent`` namespace.

    Modules call ``get_logger(__name__)``; because every backend module lives
    under the package, the returned logger inherits the package handlers set up
    by :func:`configure_logging`.
    """
    return logging.getLogger(name)


# --- status-tag → level mapping --------------------------------------------

_TAG_RE = re.compile(r"^\s*\[([A-Z][A-Z ]*)\]")

_TAG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "REQUEST": logging.DEBUG,
    "SUCCESS": logging.DEBUG,
    "INFO": logging.INFO,
    "FIXED": logging.INFO,
    "FIXUP SUCCESS": logging.INFO,
    "WARN": logging.WARNING,
    "WARNING": logging.WARNING,
    "API ERROR": logging.WARNING,
    "PARSE ERROR": logging.WARNING,
    "FIXUP": logging.WARNING,
    "ERROR": logging.ERROR,
    "FAILED": logging.ERROR,
    "TASK FAILED": logging.ERROR,
    "FIXUP FAILED": logging.ERROR,
    "SKIPPED": logging.ERROR,
}


def level_for_message(msg: str) -> int:
    """Infer a log level from a status message's leading ``[TAG]`` prefix.

    Unknown or absent tags fall back to ``INFO`` so nothing is silently lost.
    """
    match = _TAG_RE.match(msg or "")
    if match:
        return _TAG_LEVELS.get(match.group(1).strip(), logging.INFO)
    return logging.INFO


def emit_status(logger: logging.Logger, status_callback, msg: str) -> None:
    """Log ``msg`` at its tag-derived level and forward it to the UI callback.

    This is the single choke point for progress reporting: it replaces the old
    ``print()`` + ``status_callback`` pairs. A raising callback is logged and
    swallowed so a flaky UI sink can never break a backend run.
    """
    logger.log(level_for_message(msg), msg)
    if status_callback is not None:
        try:
            status_callback(msg)
        except Exception:
            logger.warning("status_callback raised while forwarding a status message",
                           exc_info=True)


# --- setup -----------------------------------------------------------------

def _coerce_level(level) -> int:
    if isinstance(level, int):
        return level
    if isinstance(level, str):
        resolved = logging.getLevelName(level.strip().upper())
        if isinstance(resolved, int):
            return resolved
    return logging.INFO


def configure_logging(*, level=None, log_dir=None, log_file=None,
                      console: bool = True, force: bool = False) -> logging.Logger:
    """Install handlers on the ``comment_agent`` package logger.

    Idempotent: repeated calls are no-ops unless ``force=True`` (the UI re-runs
    its script on every interaction, so this must be safe to call each time).

    Resolution order for each setting is explicit argument, then environment
    variable, then module default:

    - level    ← ``COMMENT_AGENT_LOG_LEVEL`` (default ``INFO``)
    - log_dir  ← ``COMMENT_AGENT_LOG_DIR``   (default ``logs``)
    - log_file ← ``COMMENT_AGENT_LOG_FILE``  (default ``comment_agent.log``)

    Setting the log file (or dir) to an empty/``"none"`` value disables file
    logging and keeps console output only.
    """
    global _configured

    logger = logging.getLogger(PACKAGE_LOGGER)

    if _configured and not force:
        return logger

    level = _coerce_level(level if level is not None
                          else os.environ.get("COMMENT_AGENT_LOG_LEVEL", DEFAULT_LEVEL))
    log_dir = (log_dir if log_dir is not None
               else os.environ.get("COMMENT_AGENT_LOG_DIR", DEFAULT_LOG_DIR))
    log_file = (log_file if log_file is not None
                else os.environ.get("COMMENT_AGENT_LOG_FILE", DEFAULT_LOG_FILE))

    # Drop any handlers we previously attached so force-reconfigure doesn't
    # duplicate output. Leave the NullHandler in place as a safety net.
    for handler in list(logger.handlers):
        if not isinstance(handler, logging.NullHandler):
            logger.removeHandler(handler)
            handler.close()

    logger.setLevel(level)
    # Handle records here; don't also bubble them to the root logger (which the
    # host — e.g. Streamlit — may have configured with its own handlers).
    logger.propagate = False

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    file_disabled = (not log_file or str(log_file).strip().lower() in _DISABLED
                     or (log_dir is not None and str(log_dir).strip().lower() in _DISABLED))
    if not file_disabled:
        try:
            path = os.path.join(log_dir, log_file) if log_dir else log_file
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError as exc:
            # A read-only or full filesystem must not stop the app; keep console.
            logger.warning("File logging disabled — could not open log file: %s", exc)

    _configured = True
    logger.debug("Logging configured | level=%s | handlers=%d",
                 logging.getLevelName(level), len(logger.handlers))
    return logger
