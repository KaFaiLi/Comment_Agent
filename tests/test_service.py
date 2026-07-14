import pandas as pd
from comment_agent.config import AppConfig
from comment_agent.review.service import CommentReviewService
from comment_agent.review.schemas import (
    KeyVariation,
    KeyMetricItem,
    Recurrent,
    RecurrentTopicItem,
)
from comment_agent.processing.columns import VAR_SVAR_COL


def _cfg():
    return AppConfig(azure_endpoint="https://x.openai.azure.com/",
                     azure_deployment="d", api_key="k", api_version="2024-10-21",
                     max_workers=2, max_retries=1)


def _key_variation(refs_per_topic):
    return KeyVariation(
        topics=[KeyMetricItem(topic="t", analysis=["v"], references=refs)
                for refs in refs_per_topic],
        summary="s",
    )


def _recurrent(refs_per_topic):
    return Recurrent(
        topics=[RecurrentTopicItem(topic="t", context="c", recurrence_reason="w",
                                   implications="i", pattern="p", references=refs)
                for refs in refs_per_topic],
        tech_issues=[], summary="s",
    )


def _patch(svc, key_refs=(["2024-01-01"],), rec_refs=(["r"],)):
    svc.usage = {"input": 0, "cached": 0, "output": 0}
    svc.key_llm = type("K", (), {"invoke": lambda self, p, config=None: _key_variation(key_refs)})()
    svc.recurrent_llm = type("R", (), {"invoke": lambda self, p, config=None: _recurrent(rec_refs)})()
    svc.model = type("M", (), {"invoke": lambda self, p, config=None: type("X", (), {"content": "summary"})()})()


def test_review_produces_structure(monkeypatch):
    svc = CommentReviewService.__new__(CommentReviewService)
    svc.cfg = _cfg()
    svc.status_callback = None
    _patch(svc)

    df = pd.DataFrame({
        "as_of_date": ["2024-01-15", "2024-02-15"],
        VAR_SVAR_COL: ["comment a", "comment b"],
    })
    result = svc.review(df, ["VAR_SVAR Comment"])
    assert "VAR_SVAR Comment" in result
    assert len(result["VAR_SVAR Comment"]) >= 1
    review = next(iter(result["VAR_SVAR Comment"].values()))
    assert "key_variation" in review and "recurrent" in review


def test_merge_usage_sums_and_tracks_cache():
    svc = CommentReviewService.__new__(CommentReviewService)
    svc.usage = {"input": 0, "cached": 0, "output": 0}
    # UsageMetadataCallbackHandler.usage_metadata shape: {model: {...}}
    svc._merge_usage({"gpt-4o": {
        "input_tokens": 100, "output_tokens": 40,
        "input_token_details": {"cache_read": 30}}})
    svc._merge_usage({"gpt-4o": {"input_tokens": 10, "output_tokens": 5}})
    assert svc.usage == {"input": 110, "cached": 30, "output": 45}
    assert svc.total_tokens == 155  # input + output; cached is a subset of input
    svc._merge_usage(None)  # missing usage must be a no-op, not a crash
    assert svc.total_tokens == 155


def test_markdown_uses_passed_summary_without_extra_llm_call():
    svc = CommentReviewService.__new__(CommentReviewService)
    svc.cfg = _cfg()
    svc.status_callback = None

    calls = {"n": 0}

    class Model:
        def invoke(self, p):
            calls["n"] += 1
            return type("X", (), {"content": "summary"})()

    svc.model = Model()
    reviews = {"2024Q1": {"key_variation": "k", "recurrent": "r"}}
    out = svc.generate_markdown_content("VAR_SVAR Comment", reviews, summary="precomputed")
    assert "precomputed" in out
    assert calls["n"] == 0  # no executive-summary LLM call when summary is passed


def test_review_grounds_and_drops_invented_refs():
    logs = []
    svc = CommentReviewService.__new__(CommentReviewService)
    svc.cfg = _cfg()
    svc.status_callback = logs.append
    # one topic cites a valid ID, one cites an invented one
    _patch(svc, key_refs=(["[C1]"], ["[C99]"]), rec_refs=(["[C1]"],))

    wrapped = ("<Risk Metrics Alert Comment on 2024-01-15>\n"
               "Indicator Type: VAR\n"
               "</Risk Metrics Alert Comment on 2024-01-15>")
    df = pd.DataFrame({"as_of_date": ["2024-01-15"], VAR_SVAR_COL: [wrapped]})

    result = svc.review(df, ["VAR_SVAR Comment"])
    review = next(iter(result["VAR_SVAR Comment"].values()))

    assert "## Sources" in review["key_variation"]
    assert "Indicator Type: VAR" in review["key_variation"]   # original text traced back
    assert "C99" not in review["key_variation"]               # invented ref dropped
    assert any("unsupported reference" in m for m in logs)     # drop was reported
