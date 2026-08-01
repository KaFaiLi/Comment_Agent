import pandas as pd
from langchain_core.callbacks import UsageMetadataCallbackHandler

from comment_agent.config import AppConfig
from comment_agent.logging_config import get_logger, emit_status
from comment_agent.llm import client
from comment_agent.llm.structured import invoke_structured
from comment_agent.llm.concurrency import run_parallel
from comment_agent.review.schemas import Recurrent, KeyVariation
from comment_agent.review.prompts import (
    EXECUTIVE_SUMMARY_PROMPT,
    KEY_VARIATION_PROMPT,
    RECURRENT_TOPICS_PROMPT,
)
from comment_agent.review.formatters import format_key_metrics, format_recurrent_topics
from comment_agent.review.citations import build_citation_index, resolve_topic_references
from comment_agent.processing.columns import REVIEW_TYPES, EVIDENCE_COLUMNS

logger = get_logger(__name__)


class CommentReviewService:
    def __init__(self, config: AppConfig, status_callback=None):
        self.config = config
        self.status_callback = status_callback
        self.model = client.build_chat_model(config)
        self.key_variation_model = client.structured(self.model, KeyVariation)
        self.recurrent_topics_model = client.structured(self.model, Recurrent)
        # Running token totals across the whole run. `cached` is the Azure
        # server-side prompt-cache portion of `input` (a subset, not additive).
        self.usage = {"input": 0, "cached": 0, "output": 0}

    def _emit(self, msg):
        emit_status(logger, self.status_callback, msg)

    def _merge_usage(self, usage_by_model: dict):
        # UsageMetadataCallbackHandler.usage_metadata is {model_name: {...}}.
        for u in (usage_by_model or {}).values():
            self.usage["input"] += u.get("input_tokens", 0)
            self.usage["output"] += u.get("output_tokens", 0)
            details = u.get("input_token_details") or {}
            self.usage["cached"] += details.get("cache_read", 0)

    @property
    def total_tokens(self) -> int:
        return self.usage["input"] + self.usage["output"]

    def review(self, df, selected_comment_types) -> dict:
        by_quarter = self._gather_comments_by_type_and_quarter(df)

        tasks = []
        for quarter, types in by_quarter.items():
            for comment_type, comments in types.items():
                if comment_type in selected_comment_types and comments:
                    tasks.append((quarter, comment_type, comments))

        self._emit(f"[INFO] {len(tasks)} review task(s) across quarters/types")

        results = run_parallel(
            tasks, self._review_one,
            max_workers=self.config.max_workers,
            status_callback=self.status_callback,
        )

        quarterly_reviews = {ct: {} for ct in selected_comment_types}
        completed = 0
        for (quarter, comment_type, _comments), review in zip(tasks, results):
            if review is not None:
                self._merge_usage(review.pop("usage", None))
                quarterly_reviews[comment_type][quarter] = review
                completed += 1
        logger.info("Review complete | %d/%d task(s) produced a review",
                    completed, len(tasks))
        return quarterly_reviews

    def _review_one(self, task):
        quarter, comment_type, comments = task
        combined = " ".join(str(c) for c in comments)
        logger.debug(
            "Review input | %s-%s | %d unique evidence block(s)",
            quarter, comment_type, len(comments),
        )
        annotated, index = build_citation_index(combined)

        # One handler per task (own thread); aggregated single-threaded in review().
        cb = UsageMetadataCallbackHandler()
        config = {"callbacks": [cb]}

        key_result = invoke_structured(
            self.key_variation_model, self.model,
            KEY_VARIATION_PROMPT.invoke({"query": annotated}), KeyVariation,
            max_retries=self.config.max_retries, delay_seconds=2,
            label=f"Key variation {quarter}-{comment_type}",
            status_callback=self.status_callback, config=config,
        )
        recurrent_result = invoke_structured(
            self.recurrent_topics_model, self.model,
            RECURRENT_TOPICS_PROMPT.invoke({"query": annotated}), Recurrent,
            max_retries=self.config.max_retries, delay_seconds=2,
            label=f"Recurrent {quarter}-{comment_type}",
            status_callback=self.status_callback, config=config,
        )
        if key_result is None or recurrent_result is None:
            return None

        dropped_k = resolve_topic_references(key_result.topics, index)
        dropped_r = resolve_topic_references(recurrent_result.topics, index)
        if dropped_k or dropped_r:
            self._emit(
                f"[WARN] {dropped_k + dropped_r} unsupported reference(s) dropped "
                f"| {quarter}-{comment_type}"
            )

        return {
            "key_variation": format_key_metrics(key_result, index),
            "recurrent": format_recurrent_topics(recurrent_result, index),
            "usage": cb.usage_metadata,
        }

    def generate_markdown_content(self, comment_type, reviews, summary=None) -> str:
        if summary is None:
            summary = self.generate_executive_summary(reviews)
        out = f"# Executive Summary for {comment_type}\n\n"
        out += f"## Executive Summary:\n{summary}\n\n"
        for quarter, review in reviews.items():
            out += f"## Quarter: {quarter}\n"
            out += f"### Key Metrics Variation\n{review['key_variation']}\n"
            out += f"### Recurrent Topics\n{review['recurrent']}\n"
        return out

    def generate_executive_summary(self, reviews) -> str:
        if not reviews:
            return "No quarterly reviews found."
        complete = "\n".join(
            f"Quarter: {q}\nKey Variation: {r['key_variation']}\nRecurrent: {r['recurrent']}\n"
            for q, r in reviews.items()
        )
        try:
            logger.debug("Generating executive summary over %d quarter(s)", len(reviews))
            cb = UsageMetadataCallbackHandler()
            result = self.model.invoke(
                f"{EXECUTIVE_SUMMARY_PROMPT} {complete}", config={"callbacks": [cb]}
            )
            self._merge_usage(cb.usage_metadata)
            return getattr(result, "content", str(result))
        except Exception as exc:
            self._emit(f"[FAILED] executive summary | {exc}")
            return "Executive summary generation failed."

    @staticmethod
    def _gather_comments_by_type_and_quarter(evidence) -> dict:
        """Group canonical source evidence without multiplying comment types.

        ``source_row_id`` is the deduplication key rather than the text itself:
        identical wording on two separate source rows remains valid evidence,
        while a mistakenly duplicated source row can never be sent twice.
        """
        missing = set(EVIDENCE_COLUMNS).difference(evidence.columns)
        if missing:
            raise ValueError(f"Review evidence missing columns: {sorted(missing)}")

        evidence = evidence[EVIDENCE_COLUMNS].copy()
        evidence["as_of_date"] = pd.to_datetime(evidence["as_of_date"])
        evidence["quarter"] = evidence["as_of_date"].dt.to_period("Q")

        by_quarter = {}
        quarters = sorted(evidence["quarter"].dropna().unique())
        for quarter in quarters:
            qdf = evidence[evidence["quarter"] == quarter]
            by_quarter[quarter] = {}
            for comment_type in REVIEW_TYPES:
                typed = qdf[qdf["review_type"] == comment_type]
                typed = typed.sort_values(
                    ["as_of_date", "source", "source_row_id"], kind="stable"
                )
                duplicate_count = typed.duplicated(subset=["source_row_id"]).sum()
                if duplicate_count:
                    logger.warning(
                        "Dropped %d duplicate evidence row(s) | %s-%s",
                        duplicate_count, quarter, comment_type,
                    )
                typed = typed.drop_duplicates(subset=["source_row_id"], keep="first")
                by_quarter[quarter][comment_type] = typed["evidence_text"].tolist()
        return by_quarter
