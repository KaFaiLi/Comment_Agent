import os
import threading

import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

from comment_agent.config import AppConfig
from comment_agent.processing.alerts import AlertProcessor
from comment_agent.processing.columns import COMMENT_TYPE_OPTIONS
from comment_agent.review.service import CommentReviewService
from comment_agent.export.documents import DocumentExporter
from comment_agent import persistence


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

    st.session_state.quarterly_reviews = reviews
    st.session_state.markdown_contents = markdown_by_type
    st.session_state.executive_summaries = summary_by_type
    st.session_state.selected_types = selected


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


def main():
    st.title("Comment Review Tool")
    init_session_state()
    cert, ia, pnl, desks, selected, generate = render_sidebar()

    if generate:
        if not (cert and ia and pnl):
            st.error("Upload all three CSV files.")
        elif not desks:
            st.error("Enter at least one desk.")
        else:
            cfg = AppConfig.from_env()
            os.makedirs(cfg.output_dir, exist_ok=True)
            placeholder = st.empty()
            with st.spinner("Generating review..."):
                run_generation(cfg, cert, ia, pnl, desks, selected,
                               status=_make_status(placeholder))

    # Always render from session_state — survives download-triggered reruns.
    render_results()


if __name__ == "__main__":
    main()
