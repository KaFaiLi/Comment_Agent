from pydantic import BaseModel, Field
from typing import List

# Design note: each topic is one self-contained object. The previous schemas
# used parallel index-aligned List[List[str]] fields, which small models
# routinely flattened or misaligned; flat per-topic fields avoid both failure
# modes while the formatters keep the rendered markdown identical.

_REFERENCES_DESC = (
    "Citation IDs supporting this topic, exactly as shown in the comments, "
    'for example ["[C3]", "[C7]"]. Never write a raw date. Never invent an ID '
    "that is not shown in the comments. Empty list if no comment supports it."
)

_SUMMARY_DESC = (
    "Concise summary of the analysis, highlighting the most critical insights upfront."
)


class RecurrentTopicItem(BaseModel):
    """One recurrent topic identified in the comments."""

    topic: str = Field(description="Short name of the recurrent topic.")
    context: str = Field(
        description=(
            "Contextual explanation: describe the nature of the alerts and comments "
            "behind this topic, acknowledging that these typically indicate potential "
            "negative impacts or red flags. Highlight the specific financial risks or "
            "market activities involved. Be as detailed as possible."
        )
    )
    recurrence_reason: str = Field(
        description=(
            "Reasons for recurrence: analyze why this issue or risk keeps recurring. "
            "Consider potential regulatory changes or internal process deficiencies "
            "that might contribute to these alerts. Be as detailed as possible."
        )
    )
    implications: str = Field(
        description=(
            "Implications and significance: explain the potential impact of this issue "
            "on financial stability or market integrity. Be as detailed as possible."
        )
    )
    pattern: str = Field(
        description=(
            "Noticeable pattern or trend across the alerts and comments that may have "
            "contributed to this recurring issue, including specific periods or "
            "conditions that see an increase in these alerts."
        )
    )
    references: List[str] = Field(description=_REFERENCES_DESC)


class Recurrent(BaseModel):
    """Recurring-topics review of the risk department comments."""

    topics: List[RecurrentTopicItem] = Field(
        description="Recurrent topics identified in the comments, up to 3."
    )
    tech_issues: List[str] = Field(
        description=(
            "Technical issues encountered, including IT issues and booking system "
            "issues, particularly those related to desk activities. Empty list if none."
        )
    )
    summary: str = Field(description=_SUMMARY_DESC)


class KeyMetricItem(BaseModel):
    """One significant metric variation identified in the comments."""

    topic: str = Field(
        description=(
            "Short name of the significant metric variation, based on extreme PnL "
            "value, unusual PnL comment compared to the trading desk activities, "
            "major value variation or unexpected comments."
        )
    )
    analysis: List[str] = Field(
        description=(
            "Deep-dive analysis of this metric variation, one point per entry: "
            "explain its potential impact on risk management; identify instruments "
            "traded by the desk for client activity and hedging purposes; identify "
            "the unusual or most important PnL split per risk factor value; precise "
            "all the underlyings and maturities involved. Provide extreme detail."
        )
    )
    references: List[str] = Field(description=_REFERENCES_DESC)


class KeyVariation(BaseModel):
    """Key-metric-variation review of the risk department comments."""

    topics: List[KeyMetricItem] = Field(
        description="Significant metric variations identified in the comments, up to 3."
    )
    summary: str = Field(description=_SUMMARY_DESC)
