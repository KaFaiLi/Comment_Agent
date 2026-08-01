"""Token usage presentation."""

import streamlit as st


def render_token_usage() -> None:
    usage = st.session_state.token_usage
    if not usage:
        return
    with st.sidebar:
        st.divider()
        st.caption("Token usage (last run)")
        input_column, output_column = st.columns(2)
        input_column.metric("Input", f"{usage['input']:,}")
        output_column.metric("Output", f"{usage['output']:,}")
        cached_column, total_column = st.columns(2)
        cached_column.metric("Cached", f"{usage['cached']:,}")
        total_column.metric("Total", f"{usage['input'] + usage['output']:,}")
