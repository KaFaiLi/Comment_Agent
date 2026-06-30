from comment_agent.llm.concurrency import run_parallel


def test_preserves_order_and_skips_failures():
    def fn(x):
        if x == 3:
            raise RuntimeError("boom")
        if x == 4:
            return None
        return x * 10

    out = run_parallel([1, 2, 3, 4, 5], fn, max_workers=3)
    assert out == [10, 20, None, None, 50]
