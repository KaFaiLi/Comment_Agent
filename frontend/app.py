"""Streamlit entry point for the Comment Review Tool.

Keep this module deliberately small: widgets live in ``frontend.components``
and the application workflow lives in ``frontend.workflows``.
"""

import os

import streamlit as st

from comment_agent.config import AppConfig
from comment_agent.logging_config import configure_logging, get_logger
from frontend.components.intro import render_intro
from frontend.components.results import render_results
from frontend.components.sidebar import render_sidebar
from frontend.components.token_usage import render_token_usage
from frontend.session import apply_generation_result, initialize_session_state
from frontend.status import make_status_callback
from frontend.workflows.review_generation import generate_review

configure_logging()
logger = get_logger(__name__)


def main() -> None:
    st.title("Comment Review Tool")
    initialize_session_state()
    request = render_sidebar()

    if not st.session_state.quarterly_reviews and not request.generate:
        render_intro()

    if request.generate:
        if error := request.validation_error():
            logger.warning("Generation blocked | %s", error)
            st.error(error)
        else:
            config = AppConfig.from_env()
            config.configure_logging(force=True)
            os.makedirs(config.output_dir, exist_ok=True)
            placeholder = st.empty()
            with st.spinner("Generating review..."):
                try:
                    result = generate_review(
                        config, request, make_status_callback(placeholder)
                    )
                    apply_generation_result(result)
                except Exception:
                    logger.exception("Review generation failed")
                    st.error("Review generation failed — see logs for details.")

    render_results()
    render_token_usage()


if __name__ == "__main__":
    main()
