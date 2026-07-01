from comment_agent.review.formatters import format_key_metrics, format_recurrent_topics, _sources_appendix
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


_IDX = {
    "C1": {"id": "C1", "tag": "Risk Metrics Alert Comment", "date": "2024-01-15", "text": "Indicator Type: VAR"},
}


def test_sources_appendix_lists_cited_ids():
    out = _sources_appendix([["[C1] (2024-01-15)"]], _IDX)
    assert "## Sources" in out
    assert '- [C1] — Risk Metrics Alert Comment on 2024-01-15: "Indicator Type: VAR"' in out


def test_sources_appendix_empty_when_nothing_cited():
    assert _sources_appendix([[]], _IDX) == ""
    assert _sources_appendix([["[C1] (2024-01-15)"]], None) == ""


def test_format_key_metrics_appends_sources_when_index_given():
    data = KeyVariation(
        KeyMetricTopic=["A"], KeyMetricVariation=[["v1"]],
        Reference=[["[C1] (2024-01-15)"]], Summary="s",
    )
    out = format_key_metrics(data, _IDX)
    assert "## Sources" in out


def test_format_key_metrics_no_sources_without_index():
    data = KeyVariation(
        KeyMetricTopic=["A"], KeyMetricVariation=[["v1"]],
        Reference=[["[C1] (2024-01-15)"]], Summary="s",
    )
    assert "## Sources" not in format_key_metrics(data)


def test_sources_appendix_flattens_multiline_text():
    """Verify multi-line comment text is collapsed to single line in bullet."""
    multiline_text = "Indicator Type: VAR\nError Message: none\nComment: spike"
    idx = {
        "C1": {
            "id": "C1",
            "tag": "Risk Metrics Alert Comment",
            "date": "2024-01-15",
            "text": multiline_text,
        },
    }
    out = _sources_appendix([["[C1] (2024-01-15)"]], idx)

    # The entire bullet should be a single line with text flattened to spaces
    assert "## Sources" in out
    expected_bullet = '- [C1] — Risk Metrics Alert Comment on 2024-01-15: "Indicator Type: VAR Error Message: none Comment: spike"'
    assert expected_bullet in out

    # Extract the bullet line and verify it has no embedded newlines
    lines = out.split("\n")
    bullet_lines = [line for line in lines if line.startswith("- [C1]")]
    assert len(bullet_lines) == 1, "Should have exactly one bullet line"
    assert bullet_lines[0] == expected_bullet
