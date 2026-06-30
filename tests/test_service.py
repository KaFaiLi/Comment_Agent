import pandas as pd
from comment_agent.config import AppConfig
from comment_agent.review.service import CommentReviewService
from comment_agent.review.schemas import KeyVariation, Recurrent
from comment_agent.processing.columns import VAR_SVAR_COL


def _cfg():
    return AppConfig(azure_endpoint="https://x.openai.azure.com/",
                     azure_deployment="d", api_key="k", api_version="2024-10-21",
                     max_workers=2, max_retries=1)


def _patch(svc):
    svc.key_llm = type("K", (), {"invoke": lambda self, p: KeyVariation(
        KeyMetricTopic=["t"], KeyMetricVariation=[["v"]], Reference=[["2024-01-01"]],
        Summary="s")})()
    svc.recurrent_llm = type("R", (), {"invoke": lambda self, p: Recurrent(
        RecurrentTopic=["t"], RecurrentTopicExplain=[["e"]], pattern=[["p"]],
        Reference=[["r"]], Tech_issue=[], Summary="s")})()
    svc.model = type("M", (), {"invoke": lambda self, p: type("X", (), {"content": "summary"})()})()


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
