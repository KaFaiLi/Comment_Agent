import json
import os
from datetime import datetime, timezone
from pathlib import Path

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
                 summary_by_type: dict, output_dir: str, exporter) -> list[str]:
    """Save review outputs and return the paths written for this run."""
    os.makedirs(output_dir, exist_ok=True)
    paths = []
    for comment_type, markdown in markdown_by_type.items():
        safe = comment_type.replace(" ", "_").lower()

        md_path = os.path.join(output_dir, f"quarterly_reviews_summary_{safe}.md")
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(markdown)
        paths.append(md_path)
        logger.debug("Wrote markdown review | %s", md_path)

        paths.append(
            exporter.convert_and_save_markdown(
                markdown, comment_type, output_dir=output_dir
            )
        )
        summary = summary_by_type.get(comment_type, "")
        paths.append(
            exporter.save_executive_summary(summary, comment_type, output_dir=output_dir)
        )
    logger.info("Saved results for %d comment type(s) to %s",
                len(markdown_by_type), output_dir)
    return paths


def save_run_manifest(*, output_dir: str, desks: list[str],
                      selected_comment_types: list[str], evidence: pd.DataFrame,
                      quarterly_reviews: dict, token_usage: dict,
                      artifacts: list[str], input_files: dict[str, str],
                      deployment: str, api_version: str) -> str:
    """Write a timestamped, credential-free record of one completed review run."""
    os.makedirs(output_dir, exist_ok=True)
    generated_at = datetime.now(timezone.utc)
    timestamp = generated_at.strftime("%Y%m%dT%H%M%S%fZ")
    output_path = Path(output_dir)

    def relative_artifact(path: str) -> str:
        return os.path.relpath(path, output_path)

    manifest = {
        "manifest_version": 1,
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "inputs": input_files,
        "scope": {
            "desks": desks,
            "selected_comment_types": selected_comment_types,
        },
        "review": {
            "evidence_rows": len(evidence),
            "evidence_date_range": _evidence_date_range(evidence),
            "reviews_by_type": {
                comment_type: len(reviews)
                for comment_type, reviews in quarterly_reviews.items()
            },
        },
        "model": {
            "deployment": deployment,
            "api_version": api_version,
        },
        "token_usage": token_usage,
        "artifacts": [relative_artifact(path) for path in artifacts],
    }
    path = output_path / f"run_manifest_{timestamp}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    logger.info("Saved run manifest | %s", path)
    return str(path)


def _evidence_date_range(evidence: pd.DataFrame) -> dict[str, str | None]:
    if evidence.empty or "as_of_date" not in evidence:
        return {"start": None, "end": None}
    dates = pd.to_datetime(evidence["as_of_date"], errors="coerce").dropna()
    if dates.empty:
        return {"start": None, "end": None}
    return {
        "start": dates.min().date().isoformat(),
        "end": dates.max().date().isoformat(),
    }
