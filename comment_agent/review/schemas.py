from pydantic import BaseModel, Field
from typing import List


class Recurrent(BaseModel):
    """Structure your response to ensure clarity and thoroughness."""

    RecurrentTopic: List[str] = Field(
        description=(""" List of identify recurrent topics in the comments, up to 3""")
    )
    RecurrentTopicExplain: List[List[str]] = Field(
        description=(
            """
            List for providing explaination on each recurrent topics.
            For each recurrent topics, proceed with the following:
            1. **Contextual Explanation:** Describe the nature of the alert and comment, acknowledging that these typically indicate potential negative impacts or red flags. Highlight the specific financial risks or market activities involved.\n
            2. **Reasons for Recurrence:** Analyze why these issues or risks are recurring. Consider potential regulatory changes, or internal process deficiencies that might contribute to these alerts.
            3. **Implications and Significance:** Explain the potential impact of these issues on financial stability or market integrity.
            Be as detail as possible
            """
        )
    )
    pattern: List[List[str]] = Field(
        description=(
            """Identify any noticeable patterns or trends across the alerts and comments that may have contributed to these recurring issues.
            Are there specific periods or conditions that see an increase in these alerts?"""
        )
    )
    Reference: List[List[str]] = Field(
        description=(
            """Cite ONLY by the bracketed citation IDs shown in the comments, for example [C3].
            Each topic's entry is a list of such IDs. Never write a raw date. Never invent an ID
            that is not shown in the comments. If no comment supports a topic, return an empty list for it."""
        )
    )
    Tech_issue: List[str] = Field(
        description=(
            """List any technical issues encountered, including IT issue, booking system issue, particularly those related to desk activities."""
        )
    )
    Summary: str = Field(
        description=(
            """Provide a concise summary of the analysis, highlighting the most critical insights upfront."""
        )
    )


class KeyVariation(BaseModel):
    """Structure your response to ensure clarity and thoroughness."""

    KeyMetricTopic: List[str] = Field(
        description=(
            """Identify significant metrics variations base on extreme PnL value, unusual PnL comment comparing to the trading desk activities, major value variation and unexpected comments. Up to 3"""
        )
    )
    KeyMetricVariation: List[List[str]] = Field(
        description=(
            """Perform a deep dive analyais on each key metric variaions you identified:
            - For each metric, explain its potential impact on risk management.
            - Identify instruments traded by the desk for client activity and hedging purpose.
            - Identify unusual or most important PnL split per risk factor value base on the key metrics variation identified.
            - Precize all the underlyings and maturities involved.
            Provide extreme details."""
        )
    )
    Reference: List[List[str]] = Field(
        description=(
            """Cite ONLY by the bracketed citation IDs shown in the comments, for example [C3].
            Each topic's entry is a list of such IDs. Never write a raw date. Never invent an ID
            that is not shown in the comments. If no comment supports a topic, return an empty list for it."""
        )
    )
    Summary: str = Field(
        description=(
            """Provide a concise summary of the analysis, highlighting the most critical insights upfront."""
        )
    )
