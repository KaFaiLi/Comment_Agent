"""Central definition of Streamlit session state."""

import streamlit as st

from comment_agent.processing.columns import COMMENT_TYPE_OPTIONS
from frontend.workflows.review_generation import GenerationResult


def initialize_session_state() -> None:
    defaults = {
        "quarterly_reviews": {}, "markdown_contents": {},
        "executive_summaries": {}, "selected_types": COMMENT_TYPE_OPTIONS,
        "token_usage": None, "run_manifest_path": None, "report_context": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def apply_generation_result(result: GenerationResult) -> None:
    st.session_state.quarterly_reviews = result.quarterly_reviews
    st.session_state.markdown_contents = result.markdown_contents
    st.session_state.executive_summaries = result.executive_summaries
    st.session_state.selected_types = result.selected_types
    st.session_state.token_usage = result.token_usage
    st.session_state.run_manifest_path = result.run_manifest_path
    st.session_state.report_context = result.report_context
