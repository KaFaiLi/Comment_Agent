from comment_agent.processing.columns import COMMENT_COLUMNS, COMMENT_TYPE_OPTIONS


def test_column_mapping_complete():
    assert COMMENT_COLUMNS["VAR_SVAR Comment"] == "VAR_SVAR Comment for LLM"
    assert set(COMMENT_TYPE_OPTIONS) == set(COMMENT_COLUMNS.keys())
    assert len(COMMENT_COLUMNS) == 5
