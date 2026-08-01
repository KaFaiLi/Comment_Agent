"""Orchestrate review generation independently of Streamlit session state."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from comment_agent import persistence
from comment_agent.config import AppConfig
from comment_agent.export.documents import DocumentExporter
from comment_agent.logging_config import get_logger
from comment_agent.processing.alerts import AlertProcessor
from comment_agent.review.service import CommentReviewService
from frontend.components.sidebar import ReviewRequest

logger = get_logger(__name__)


@dataclass(frozen=True)
class GenerationResult:
    quarterly_reviews: dict
    markdown_contents: dict[str, str]
    executive_summaries: dict[str, str]
    selected_types: list[str]
    token_usage: dict[str, int]
    run_manifest_path: Path
    report_context: dict[str, Any]


def generate_review(config: AppConfig, request: ReviewRequest, status_callback) -> GenerationResult:
    logger.info(
        "Starting review generation | desks=%s | types=%s",
        request.desks, request.comment_types,
    )
    processor = AlertProcessor(
        request.certification_file, request.income_attribution_file,
        request.pnl_file, output_dir=config.output_dir,
    )
    evidence = processor.build_evidence(request.desks)
    intermediate_path = persistence.save_intermediates(evidence, config.output_dir)
    review_service = CommentReviewService(config, status_callback=status_callback)
    quarterly_reviews = review_service.review(evidence, request.comment_types)

    markdown_contents, executive_summaries = {}, {}
    for comment_type, reviews_for_type in quarterly_reviews.items():
        summary = review_service.generate_executive_summary(reviews_for_type)
        executive_summaries[comment_type] = summary
        markdown_contents[comment_type] = review_service.generate_markdown_content(
            comment_type, reviews_for_type, summary=summary
        )

    dates = sorted(evidence["as_of_date"].dropna().astype(str).unique()) if not evidence.empty else []
    input_files = (
        request.certification_file.name, request.income_attribution_file.name,
        request.pnl_file.name,
    )
    report_context = {
        "report_id": f"CAR-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}",
        "generated_at": datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC"),
        "review_status": "AI-generated — auditor validation required",
        "desks": ", ".join(request.desks),
        "date_range": f"{dates[0]} to {dates[-1]}" if dates else "No in-scope evidence",
        "evidence_rows": len(evidence),
        "input_files": ", ".join(input_files),
    }
    result_paths = persistence.save_results(
        quarterly_reviews, markdown_contents, executive_summaries,
        config.output_dir, DocumentExporter(), report_context=report_context,
    )
    manifest_path = persistence.save_run_manifest(
        output_dir=config.output_dir, desks=request.desks,
        selected_comment_types=request.comment_types, evidence=evidence,
        quarterly_reviews=quarterly_reviews, token_usage=review_service.usage,
        artifacts=[*processor.source_extract_paths, intermediate_path, *result_paths],
        input_files={
            "certification_alerts": input_files[0],
            "income_attribution_alerts": input_files[1], "pnl_comments": input_files[2],
        },
        deployment=config.azure_deployment, api_version=config.api_version,
    )
    logger.info("Review generation complete | comment types produced=%d", len(markdown_contents))
    return GenerationResult(
        quarterly_reviews, markdown_contents, executive_summaries,
        request.comment_types, review_service.usage, manifest_path, report_context,
    )
