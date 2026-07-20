import os

import pandas as pd

from comment_agent.logging_config import get_logger
from comment_agent.processing.columns import EVIDENCE_COLUMNS, REVIEW_TYPES

logger = get_logger(__name__)


def _daily_comments_view(evidence: pd.DataFrame) -> pd.DataFrame:
    """Create one audit-friendly row per date without changing LLM evidence."""
    missing = set(EVIDENCE_COLUMNS).difference(evidence.columns)
    if missing:
        raise ValueError(f"Review evidence missing columns: {sorted(missing)}")
    if evidence.empty:
        return pd.DataFrame(columns=["as_of_date", *REVIEW_TYPES, "All Comments"])

    evidence = evidence.sort_values(
        ["as_of_date", "review_type", "source", "source_row_id"], kind="stable"
    )
    grouped = (
        evidence.groupby(["as_of_date", "review_type"], sort=True)["evidence_text"]
        .agg("\n\n".join)
        .unstack("review_type")
        .reindex(columns=REVIEW_TYPES)
        .reset_index()
    )
    grouped["All Comments"] = grouped[list(REVIEW_TYPES)].apply(
        lambda row: "\n\n".join(
            str(value) for value in row if pd.notna(value) and str(value).strip()
        ),
        axis=1,
    )
    return grouped


def save_intermediates(evidence: pd.DataFrame, output_dir: str) -> str:
    """Save a daily comment view and the complete row-level evidence trail."""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "All comments.xlsx")
    daily = _daily_comments_view(evidence)
    with pd.ExcelWriter(path) as writer:
        daily.to_excel(writer, sheet_name="Daily comments", index=False)
        evidence.to_excel(writer, sheet_name="Review evidence", index=False)
    logger.info(
        "Saved intermediate comments | %d day(s) | %d evidence row(s) | %s",
        len(daily), len(evidence), path,
    )
    return path


def save_results(quarterly_reviews: dict, markdown_by_type: dict,
                 summary_by_type: dict, output_dir: str, exporter) -> None:
    os.makedirs(output_dir, exist_ok=True)
    for comment_type, markdown in markdown_by_type.items():
        safe = comment_type.replace(" ", "_").lower()

        md_path = os.path.join(output_dir, f"quarterly_reviews_summary_{safe}.md")
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(markdown)
        logger.debug("Wrote markdown review | %s", md_path)

        exporter.convert_and_save_markdown(markdown, comment_type, output_dir=output_dir)
        summary = summary_by_type.get(comment_type, "")
        exporter.save_executive_summary(summary, comment_type, output_dir=output_dir)
    logger.info("Saved results for %d comment type(s) to %s",
                len(markdown_by_type), output_dir)
