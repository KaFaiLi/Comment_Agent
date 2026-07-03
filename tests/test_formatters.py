from comment_agent.review.formatters import format_key_metrics, format_recurrent_topics, _sources_appendix
from comment_agent.review.schemas import KeyVariation, KeyMetricItem, Recurrent, RecurrentTopicItem


def _key_item(topic="A", analysis=("v1",), references=("[C1] (2024-01-15)",)):
    return KeyMetricItem(topic=topic, analysis=list(analysis), references=list(references))


def _recurrent_item(topic="T", references=("r",)):
    return RecurrentTopicItem(
        topic=topic, context="c", recurrence_reason="why",
        implications="impact", pattern="p", references=list(references),
    )


def test_format_key_metrics_renders_each_topic():
    data = KeyVariation(
        topics=[_key_item("A"), _key_item("B", analysis=[], references=[])],
        summary="s",
    )
    out = format_key_metrics(data)
    assert "Key Metric Topic 1: A" in out
    assert "Key Metric Topic 2: B" in out  # empty analysis/references must not crash
    assert "- v1" in out


def test_format_recurrent_topics_handles_empty_tech():
    data = Recurrent(topics=[_recurrent_item()], tech_issues=[], summary="s")
    out = format_recurrent_topics(data)
    assert "No specific technical issues reported." in out


def test_format_recurrent_topics_renders_explanation_bullets():
    data = Recurrent(topics=[_recurrent_item()], tech_issues=["glitch"], summary="s")
    out = format_recurrent_topics(data)
    assert "Recurrent Topic 1: T" in out
    assert "- Contextual Explanation: c" in out
    assert "- Reasons for Recurrence: why" in out
    assert "- Implications and Significance: impact" in out
    assert "**Pattern for Topic 1:** p" in out
    assert "glitch" in out


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
    data = KeyVariation(topics=[_key_item()], summary="s")
    out = format_key_metrics(data, _IDX)
    assert "## Sources" in out


def test_format_key_metrics_no_sources_without_index():
    data = KeyVariation(topics=[_key_item()], summary="s")
    assert "## Sources" not in format_key_metrics(data)


def test_format_recurrent_topics_appends_sources_when_index_given():
    data = Recurrent(
        topics=[_recurrent_item(references=["[C1] (2024-01-15)"])],
        tech_issues=[], summary="s",
    )
    out = format_recurrent_topics(data, _IDX)
    assert "## Sources" in out


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
