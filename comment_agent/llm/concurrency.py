from concurrent.futures import ThreadPoolExecutor

from comment_agent.logging_config import get_logger, emit_status

logger = get_logger(__name__)


def run_parallel(items, fn, *, max_workers: int = 4, status_callback=None) -> list:
    # ponytail: thread pool, fine for I/O-bound LLM calls; switch to async if call volume explodes
    items = list(items)
    results = [None] * len(items)
    logger.debug("run_parallel | %d item(s) | max_workers=%d", len(items), max_workers)

    def safe(i, item):
        try:
            return i, fn(item)
        except Exception as exc:
            # emit_status logs at ERROR and forwards to the UI; guard so a raising
            # callback (or logging sink) can never abort the worker.
            try:
                emit_status(logger, status_callback, f"[TASK FAILED] index {i} | {exc}")
            except Exception:
                pass
            return i, None

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for i, value in pool.map(lambda p: safe(*p), enumerate(items)):
            results[i] = value
    return results
