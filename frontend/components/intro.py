"""Landing-page content."""

import streamlit as st


def render_intro() -> None:
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
