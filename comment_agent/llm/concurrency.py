from concurrent.futures import ThreadPoolExecutor


def run_parallel(items, fn, *, max_workers: int = 4, status_callback=None) -> list:
    # ponytail: thread pool, fine for I/O-bound LLM calls; switch to async if call volume explodes
    items = list(items)
    results = [None] * len(items)

    def safe(i, item):
        try:
            return i, fn(item)
        except Exception as exc:
            if status_callback:
                status_callback(f"[TASK FAILED] index {i} | {exc}")
            return i, None

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for i, value in pool.map(lambda p: safe(*p), enumerate(items)):
            results[i] = value
    return results
