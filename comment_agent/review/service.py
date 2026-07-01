import pandas as pd

from comment_agent.config import AppConfig
from comment_agent.llm import client
from comment_agent.llm.structured import invoke_structured
from comment_agent.llm.concurrency import run_parallel
from comment_agent.review.schemas import Recurrent, KeyVariation
from comment_agent.review.prompts import recurrentPrompt, KeyVariationPrompt, xxm_prompt
from comment_agent.review.formatters import format_key_metrics, format_recurrent_topics
from comment_agent.review.citations import build_citation_index, resolve_references
from comment_agent.processing.columns import COMMENT_COLUMNS


class CommentReviewService:
    def __init__(self, cfg: AppConfig, status_callback=None):
        self.cfg = cfg
        self.status_callback = status_callback
        self.model = client.build_chat_model(cfg)
        self.key_llm = client.structured(self.model, KeyVariation)
        self.recurrent_llm = client.structured(self.model, Recurrent)

    def _emit(self, msg):
        print(msg)
        if self.status_callback:
            self.status_callback(msg)

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
            max_workers=self.cfg.max_workers,
            status_callback=self.status_callback,
        )

        quarterly_reviews = {ct: {} for ct in selected_comment_types}
        for (quarter, comment_type, _comments), review in zip(tasks, results):
            if review is not None:
                quarterly_reviews[comment_type][quarter] = review
        return quarterly_reviews

    def _review_one(self, task):
        quarter, comment_type, comments = task
        combined = " ".join(str(c) for c in comments)
        annotated, index = build_citation_index(combined)

        key_result = invoke_structured(
            self.key_llm, self.model,
            KeyVariationPrompt.invoke({"query": annotated}), KeyVariation,
            max_retries=self.cfg.max_retries, delay_seconds=2,
            label=f"Key variation {quarter}-{comment_type}",
            status_callback=self.status_callback,
        )
        recurrent_result = invoke_structured(
            self.recurrent_llm, self.model,
            recurrentPrompt.invoke({"query": annotated}), Recurrent,
            max_retries=self.cfg.max_retries, delay_seconds=2,
            label=f"Recurrent {quarter}-{comment_type}",
            status_callback=self.status_callback,
        )
        if key_result is None or recurrent_result is None:
            return None

        key_result.Reference, dropped_k = resolve_references(key_result.Reference, index)
        recurrent_result.Reference, dropped_r = resolve_references(recurrent_result.Reference, index)
        if dropped_k or dropped_r:
            self._emit(
                f"[WARN] {dropped_k + dropped_r} unsupported reference(s) dropped "
                f"| {quarter}-{comment_type}"
            )

        return {
            "key_variation": format_key_metrics(key_result, index),
            "recurrent": format_recurrent_topics(recurrent_result, index),
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
            result = self.model.invoke(f"{xxm_prompt} {complete}")
            return getattr(result, "content", str(result))
        except Exception as exc:
            self._emit(f"[FAILED] executive summary | {exc}")
            return "Executive summary generation failed."

    @staticmethod
    def _gather_comments_by_type_and_quarter(df) -> dict:
        df = df.copy()
        df["as_of_date"] = pd.to_datetime(df["as_of_date"])
        df["quarter"] = df["as_of_date"].dt.to_period("Q")

        by_quarter = {}
        for quarter in df["quarter"].unique():
            qdf = df[df["quarter"] == quarter]
            by_quarter[quarter] = {}
            for comment_type, column in COMMENT_COLUMNS.items():
                if column not in qdf.columns:
                    by_quarter[quarter][comment_type] = []
                else:
                    by_quarter[quarter][comment_type] = (
                        qdf[column].dropna().astype(str).tolist()
                    )
        return by_quarter
