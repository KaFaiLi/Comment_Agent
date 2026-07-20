REVIEW_TYPES = (
    "VAR_SVAR Comment",
    "Risk Metrics Comment",
    "IA Comment",
    "PnL Comment",
    "Stress Test Comment",
)

COMMENT_TYPE_OPTIONS = list(REVIEW_TYPES)

# Canonical, long-form evidence contract used by the review stage.  One row is
# one source record; review_type determines the single review task it belongs
# to.  Keeping this separate from the legacy wide comment columns prevents
# comments from unrelated sources being multiplied through DataFrame joins.
EVIDENCE_COLUMNS = [
    "as_of_date",
    "desk",
    "perimeter_name",
    "source",
    "source_row_id",
    "review_type",
    "metric_name",
    "evidence_text",
]
