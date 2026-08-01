"""Sidebar inputs and their validation."""

from dataclasses import dataclass
from typing import Any

import streamlit as st

from comment_agent.processing.columns import COMMENT_TYPE_OPTIONS


@dataclass(frozen=True)
class ReviewRequest:
    certification_file: Any
    income_attribution_file: Any
    pnl_file: Any
    desks: list[str]
    comment_types: list[str]
    generate: bool

    def validation_error(self) -> str | None:
        if not all((self.certification_file, self.income_attribution_file, self.pnl_file)):
            return "Upload all three CSV files."
        if not self.desks:
            return "Enter at least one desk."
        if not self.comment_types:
            return "Select at least one comment type."
        return None


def render_sidebar() -> ReviewRequest:
    with st.sidebar:
        st.markdown("Upload the certification, income-attribution and PnL CSV files.")
        certification_file = st.file_uploader(
            "Certification Alert CSV", type="csv", key="certification_file"
        )
        income_attribution_file = st.file_uploader(
            "Income Attribution Alert CSV", type="csv", key="income_attribution_file"
        )
        pnl_file = st.file_uploader("PnL Comment CSV", type="csv", key="pnl_file")
        raw_desks = st.text_input("Desks (comma-separated)", placeholder="EQD, FIC")
        desks = [desk.strip() for desk in raw_desks.split(",") if desk.strip()]
        if desks:
            st.caption("Desks to search: " + ", ".join(desks))
        comment_types = st.multiselect(
            "Comment types", COMMENT_TYPE_OPTIONS, default=COMMENT_TYPE_OPTIONS
        )
        generate = st.button("Generate Review")
    return ReviewRequest(
        certification_file,
        income_attribution_file,
        pnl_file,
        desks,
        comment_types,
        generate,
    )
