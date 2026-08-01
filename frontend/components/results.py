"""Generated review presentation and downloads."""

import streamlit as st

from comment_agent.export.documents import DocumentExporter


def render_results() -> None:
    reviews = st.session_state.quarterly_reviews
    if not reviews:
        return
    if st.session_state.run_manifest_path:
        st.caption(f"Run manifest saved: {st.session_state.run_manifest_path}")
    if not st.session_state.selected_types:
        return

    exporter = DocumentExporter()
    for tab, comment_type in zip(
        st.tabs(st.session_state.selected_types), st.session_state.selected_types
    ):
        with tab:
            content = st.session_state.markdown_contents.get(comment_type)
            summary = st.session_state.executive_summaries.get(comment_type)
            if not content:
                st.info(f"No review generated for {comment_type}.")
                continue
            st.markdown(content)
            safe_name = comment_type.replace(" ", "_").lower()
            report_context = st.session_state.report_context
            type_reviews = reviews.get(comment_type, {})
            st.download_button(
                "Download Detailed Full Review",
                exporter.get_word_doc_buffer_from_markdown(
                    content, comment_type, reviews=type_reviews,
                    executive_summary=summary, report_context=report_context,
                ),
                file_name=f"{safe_name}_full_review.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            st.download_button(
                "Download Executive Review",
                exporter.get_word_doc_buffer_from_executive_summary(
                    summary, comment_type, reviews=type_reviews,
                    report_context=report_context,
                ),
                file_name=f"{safe_name}_executive_summary.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            st.warning("AI-generated; apply professional judgement.", icon="ℹ️")
