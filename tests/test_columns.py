from comment_agent.processing.columns import COMMENT_TYPE_OPTIONS, EVIDENCE_COLUMNS, REVIEW_TYPES


def test_review_contract_complete():
    assert COMMENT_TYPE_OPTIONS == list(REVIEW_TYPES)
    assert len(REVIEW_TYPES) == 5
    assert {"source_row_id", "review_type", "metric_name", "evidence_text"}.issubset(
        EVIDENCE_COLUMNS
    )
