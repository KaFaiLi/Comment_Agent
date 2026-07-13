from comment_agent.review.citations import (
    build_citation_index,
    CITATION_RE,
    resolve_references,
    resolve_topic_references,
)

WRAPPED = (
    "<Risk Metrics Alert Comment on 2024-01-15>\n"
    "Indicator Type: VAR\n"
    "</Risk Metrics Alert Comment on 2024-01-15> "
    "<PnL comments on 2024-02-03>\n"
    "Loss on FX book\n"
    "</PnL comments on 2024-02-03>"
)


def test_build_index_assigns_sequential_ids():
    annotated, index = build_citation_index(WRAPPED)
    assert set(index) == {"C1", "C2"}
    assert index["C1"]["date"] == "2024-01-15"
    assert index["C1"]["tag"] == "Risk Metrics Alert Comment"
    assert index["C1"]["text"] == "Indicator Type: VAR"
    assert index["C2"]["date"] == "2024-02-03"
    assert index["C2"]["text"] == "Loss on FX book"


def test_build_index_annotates_each_block_once():
    annotated, index = build_citation_index(WRAPPED)
    assert annotated.count("[C1]") == 1
    assert annotated.count("[C2]") == 1
    # the full tagged block is preserved for the model
    assert "<Risk Metrics Alert Comment on 2024-01-15>" in annotated


def test_build_index_no_blocks_returns_input_unchanged():
    annotated, index = build_citation_index("no tags here")
    assert annotated == "no tags here"
    assert index == {}


INDEX = {
    "C1": {"id": "C1", "tag": "Risk Metrics Alert Comment", "date": "2024-01-15", "text": "Indicator Type: VAR"},
    "C2": {"id": "C2", "tag": "PnL comments", "date": "2024-02-03", "text": "Loss on FX book"},
}


def test_resolve_keeps_valid_and_formats_with_date():
    cleaned, dropped = resolve_references([["[C1]", "[C2]"]], INDEX)
    assert cleaned == [["[C1] (2024-01-15)", "[C2] (2024-02-03)"]]
    assert dropped == 0


def test_resolve_drops_invented_ids():
    cleaned, dropped = resolve_references([["[C1]"], ["[C99]"]], INDEX)
    assert cleaned == [["[C1] (2024-01-15)"], []]
    assert dropped == 1


def test_resolve_drops_raw_date_reference():
    cleaned, dropped = resolve_references([["2024-01-15: system outage"]], INDEX)
    assert cleaned == [[]]
    assert dropped == 1


def test_resolve_dedupes_within_topic():
    cleaned, dropped = resolve_references([["[C1]", "[C1]"]], INDEX)
    assert cleaned == [["[C1] (2024-01-15)"]]
    assert dropped == 0


def test_resolve_topic_references_grounds_in_place():
    from comment_agent.review.schemas import KeyMetricItem

    topics = [
        KeyMetricItem(topic="a", analysis=["x"], references=["[C1]"]),
        KeyMetricItem(topic="b", analysis=["y"], references=["[C99]"]),
    ]
    dropped = resolve_topic_references(topics, INDEX)
    assert topics[0].references == ["[C1] (2024-01-15)"]
    assert topics[1].references == []
    assert dropped == 1


def test_resolve_topic_references_handles_empty():
    assert resolve_topic_references([], INDEX) == 0
    assert resolve_topic_references(None, INDEX) == 0
