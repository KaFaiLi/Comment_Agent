import logging

import pytest

from comment_agent import logging_config
from comment_agent.logging_config import (
    PACKAGE_LOGGER,
    configure_logging,
    emit_status,
    get_logger,
    level_for_message,
)


@pytest.fixture
def clean_logger():
    """Snapshot and restore the package logger + module state around a test."""
    logger = logging.getLogger(PACKAGE_LOGGER)
    saved_handlers = list(logger.handlers)
    saved_level = logger.level
    saved_propagate = logger.propagate
    saved_configured = logging_config._configured
    try:
        yield logger
    finally:
        for h in list(logger.handlers):
            if h not in saved_handlers:
                logger.removeHandler(h)
                h.close()
        for h in saved_handlers:
            if h not in logger.handlers:
                logger.addHandler(h)
        logger.setLevel(saved_level)
        logger.propagate = saved_propagate
        logging_config._configured = saved_configured


def test_get_logger_is_namespaced():
    assert get_logger("comment_agent.foo").name == "comment_agent.foo"


# --- level_for_message -----------------------------------------------------

@pytest.mark.parametrize("msg,level", [
    ("[REQUEST] Key variation | attempt 1/3", logging.DEBUG),
    ("[SUCCESS] Recurrent", logging.DEBUG),
    ("[INFO] 4 review task(s)", logging.INFO),
    ("[FIXED] label | deterministic", logging.INFO),
    ("[WARN] 2 unsupported reference(s) dropped", logging.WARNING),
    ("[API ERROR] label | attempt 1 | boom", logging.WARNING),
    ("[PARSE ERROR] label | attempt 1", logging.WARNING),
    ("[FIXUP] label | LLM repair", logging.WARNING),
    ("[FIXUP SUCCESS] label", logging.INFO),
    ("[FIXUP FAILED] label | boom", logging.ERROR),
    ("[TASK FAILED] index 2 | boom", logging.ERROR),
    ("[SKIPPED] label | unrecoverable", logging.ERROR),
    ("[FAILED] executive summary | boom", logging.ERROR),
])
def test_level_for_message_maps_known_tags(msg, level):
    assert level_for_message(msg) == level


def test_level_for_message_defaults_to_info():
    assert level_for_message("no tag here") == logging.INFO
    assert level_for_message("[lowercase] ignored") == logging.INFO
    assert level_for_message("") == logging.INFO
    assert level_for_message(None) == logging.INFO


# --- emit_status -----------------------------------------------------------

def test_emit_status_logs_at_tag_level_and_forwards(caplog):
    logger = get_logger("comment_agent.test_emit")
    received = []
    with caplog.at_level(logging.DEBUG, logger="comment_agent.test_emit"):
        emit_status(logger, received.append, "[API ERROR] boom")
    assert received == ["[API ERROR] boom"]
    assert caplog.records[-1].levelno == logging.WARNING


def test_emit_status_without_callback(caplog):
    logger = get_logger("comment_agent.test_emit_none")
    with caplog.at_level(logging.INFO, logger="comment_agent.test_emit_none"):
        emit_status(logger, None, "[INFO] hello")
    assert any(r.getMessage() == "[INFO] hello" for r in caplog.records)


def test_emit_status_swallows_callback_error(caplog):
    logger = get_logger("comment_agent.test_emit_raise")

    def bad(_msg):
        raise ValueError("sink down")

    # Must not raise even though the callback does.
    emit_status(logger, bad, "[INFO] hello")


# --- configure_logging -----------------------------------------------------

def test_configure_logging_installs_handlers(clean_logger, tmp_path):
    configure_logging(level="DEBUG", log_dir=str(tmp_path), log_file="app.log",
                      force=True)
    kinds = {type(h).__name__ for h in clean_logger.handlers}
    assert "StreamHandler" in kinds
    assert "RotatingFileHandler" in kinds
    assert clean_logger.level == logging.DEBUG
    assert clean_logger.propagate is False


def test_configure_logging_writes_to_file(clean_logger, tmp_path):
    configure_logging(level="INFO", log_dir=str(tmp_path), log_file="app.log",
                      force=True)
    get_logger("comment_agent.filetest").info("a written line")
    for h in clean_logger.handlers:
        h.flush()
    log_path = tmp_path / "app.log"
    assert log_path.exists()
    assert "a written line" in log_path.read_text(encoding="utf-8")


def test_configure_logging_can_disable_file(clean_logger, tmp_path):
    configure_logging(level="INFO", log_dir=str(tmp_path), log_file="none",
                      force=True)
    kinds = {type(h).__name__ for h in clean_logger.handlers}
    assert "RotatingFileHandler" not in kinds


def test_configure_logging_is_idempotent_without_force(clean_logger, tmp_path):
    configure_logging(log_dir=str(tmp_path), log_file="app.log", force=True)
    count = len(clean_logger.handlers)
    configure_logging(log_dir=str(tmp_path), log_file="app.log")  # no force
    assert len(clean_logger.handlers) == count


def test_configure_logging_force_does_not_duplicate(clean_logger, tmp_path):
    configure_logging(log_dir=str(tmp_path), log_file="app.log", force=True)
    count = len(clean_logger.handlers)
    configure_logging(log_dir=str(tmp_path), log_file="app.log", force=True)
    assert len(clean_logger.handlers) == count  # old handlers replaced, not stacked
