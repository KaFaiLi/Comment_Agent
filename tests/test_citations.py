from comment_agent.review.citations import build_citation_index, CITATION_RE

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
