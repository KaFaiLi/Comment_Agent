import os
import threading

import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

from comment_agent.config import AppConfig
from comment_agent.logging_config import configure_logging, get_logger
from comment_agent.processing.alerts import AlertProcessor
from comment_agent.processing.columns import COMMENT_TYPE_OPTIONS
from comment_agent.review.service import CommentReviewService
from comment_agent.export.documents import DocumentExporter
from comment_agent import persistence

# Configure backend logging once, at import, before any AppConfig is built.
# from_env() (built later) is validated and may raise; logging must already be
# live so that failure is captured. Uses env defaults; refreshed per-run below.
configure_logging()
logger = get_logger(__name__)


def _make_status(placeholder):
    # Status callbacks fire from ThreadPoolExecutor worker threads, which lack
    # the Streamlit ScriptRunContext ("missing ScriptRunContext" warning).
    # Attach the main script's ctx to each worker before touching a widget.
    # ponytail: single shared placeholder, last-writer-wins — fine for a
    # progress line; use a queue if per-task progress bars are ever needed.
    ctx = get_script_run_ctx()

    def status(msg):
        add_script_run_ctx(threading.current_thread(), ctx)
        placeholder.info(msg)

    return status


def init_session_state():
    defaults = {
        "quarterly_reviews": {},
        "markdown_contents": {},
        "executive_summaries": {},
        "selected_types": COMMENT_TYPE_OPTIONS,
        "token_usage": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def render_sidebar():
    with st.sidebar:
        st.markdown("Upload the certification, income-attribution and PnL CSV files.")
        cert = st.file_uploader("Certification Alert CSV", type="csv", key="cert_file")
        ia = st.file_uploader("Income Attribution Alert CSV", type="csv", key="ia_file")
        pnl = st.file_uploader("PnL Comment CSV", type="csv", key="pnl_file")
        raw = st.text_input("Desks (comma-separated)", placeholder="EQD, FIC")
        desks = [d.strip() for d in raw.split(",") if d.strip()]
        if desks:
            st.caption("Desks to search: " + ", ".join(desks))
        selected = st.multiselect("Comment types", COMMENT_TYPE_OPTIONS,
                                  default=COMMENT_TYPE_OPTIONS)
        generate = st.button("Generate Review")
    return cert, ia, pnl, desks, selected, generate


def run_generation(cfg, cert, ia, pnl, desks, selected, status):
    logger.info("Starting review generation | desks=%s | types=%s", desks, selected)
    proc = AlertProcessor(cert, ia, pnl, output_dir=cfg.output_dir)
    merged = proc.merge_comments(desks)
    final_df = AlertProcessor.create_final_comment(merged)
    persistence.save_intermediates(final_df, cfg.output_dir)

    service = CommentReviewService(cfg, status_callback=status)
    reviews = service.review(final_df, selected)

    markdown_by_type, summary_by_type = {}, {}
    for comment_type, qreviews in reviews.items():
        summary = service.generate_executive_summary(qreviews)
        summary_by_type[comment_type] = summary
        markdown_by_type[comment_type] = service.generate_markdown_content(
            comment_type, qreviews, summary=summary)

    persistence.save_results(reviews, markdown_by_type, summary_by_type,
                             cfg.output_dir, DocumentExporter())
    logger.info("Review generation complete | comment types produced=%d",
                len(markdown_by_type))

    st.session_state.quarterly_reviews = reviews
    st.session_state.markdown_contents = markdown_by_type
    st.session_state.executive_summaries = summary_by_type
    st.session_state.selected_types = selected
    st.session_state.token_usage = service.usage


def render_results():
    reviews = st.session_state.quarterly_reviews
    if not reviews:
        return
    exporter = DocumentExporter()
    selected = st.session_state.selected_types
    if not selected:
        return
    tabs = st.tabs(selected)
    for i, comment_type in enumerate(selected):
        with tabs[i]:
            content = st.session_state.markdown_contents.get(comment_type)
            summary = st.session_state.executive_summaries.get(comment_type)
            if not content:
                st.info(f"No review generated for {comment_type}.")
                continue
            st.markdown(content)
            safe = comment_type.replace(" ", "_").lower()
            st.download_button(
                "Download Full Review", exporter.get_word_doc_buffer_from_markdown(content),
                file_name=f"{safe}_full_review.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            st.download_button(
                "Download Executive Summary",
                exporter.get_word_doc_buffer_from_executive_summary(summary, comment_type),
                file_name=f"{safe}_executive_summary.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            st.warning("AI-generated; apply professional judgement.", icon="ℹ️")


def render_token_counts():
    # Appends to the bottom of the sidebar. Called at the end of main() so it
    # lands under the sidebar widgets rendered earlier in the same script run.
    usage = st.session_state.token_usage
    if not usage:
        return
    with st.sidebar:
        st.divider()
        st.caption("Token usage (last run)")
        total = usage["input"] + usage["output"]
        c1, c2 = st.columns(2)
        c1.metric("Input", f"{usage['input']:,}")
        c2.metric("Output", f"{usage['output']:,}")
        c3, c4 = st.columns(2)
        c3.metric("Cached", f"{usage['cached']:,}")
        c4.metric("Total", f"{total:,}")


def render_intro():
    st.markdown(
        """
The **Comment Review Tool** helps market-activities auditors review the risk
comments produced by the Risk department across trading desks.

Upload the three source exports — **certification alerts**, **income-attribution
alerts**, and **PnL comments** — then choose the desks and comment types in
scope. The tool consolidates every comment by quarter and produces, for each
quarter and comment type:

- a **Key Metrics Variation** review — significant PnL and risk-metric moves,
  the instruments and maturities involved, and the dates that evidence them;
- a **Recurrent Topics** review — themes, patterns and technical issues that
  repeat across the period;
- a cross-quarter **Executive Summary** for reporting.

Each review is downloadable as a Word document and is auto-saved to the output
folder. Reviews are AI-generated and must be validated with professional
auditor judgement before use.

*Get started from the sidebar on the left.*
"""
    )


def main():
    st.title("Comment Review Tool")
    init_session_state()
    cert, ia, pnl, desks, selected, generate = render_sidebar()

    if not st.session_state.quarterly_reviews and not generate:
        render_intro()

    if generate:
        if not (cert and ia and pnl):
            logger.warning("Generation blocked | missing CSV upload(s)")
            st.error("Upload all three CSV files.")
        elif not desks:
            logger.warning("Generation blocked | no desks entered")
            st.error("Enter at least one desk.")
        else:
            cfg = AppConfig.from_env()
            cfg.configure_logging(force=True)  # apply config's log settings
            os.makedirs(cfg.output_dir, exist_ok=True)
            placeholder = st.empty()
            with st.spinner("Generating review..."):
                try:
                    run_generation(cfg, cert, ia, pnl, desks, selected,
                                   status=_make_status(placeholder))
                except Exception:
                    logger.exception("Review generation failed")
                    st.error("Review generation failed — see logs for details.")

    # Always render from session_state — survives download-triggered reruns.
    render_results()
    render_token_counts()


if __name__ == "__main__":
    main()
