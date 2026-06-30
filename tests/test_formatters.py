from comment_agent.review.formatters import format_key_metrics, format_recurrent_topics
from comment_agent.review.schemas import KeyVariation, Recurrent


def test_format_key_metrics_handles_ragged():
    data = KeyVariation(
        KeyMetricTopic=["A", "B"],
        KeyMetricVariation=[["v1"]],          # shorter than topics on purpose
        Reference=[["2024-01-01"]],
        Summary="s",
    )
    out = format_key_metrics(data)
    assert "Key Metric Topic 1: A" in out
    assert "Key Metric Topic 2: B" in out  # must not crash on missing index


def test_format_recurrent_topics_handles_empty_tech():
    data = Recurrent(
        RecurrentTopic=["T"], RecurrentTopicExplain=[["e"]],
        pattern=[["p"]], Reference=[["r"]], Tech_issue=[], Summary="s",
    )
    out = format_recurrent_topics(data)
    assert "No specific technical issues reported." in out
