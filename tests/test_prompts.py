from comment_agent.review.schemas import Recurrent, KeyVariation
from comment_agent.review.prompts import recurrentPrompt, KeyVariationPrompt, xxm_prompt


def test_schemas_have_expected_fields():
    assert "RecurrentTopic" in Recurrent.model_fields
    assert "KeyMetricTopic" in KeyVariation.model_fields


def test_prompts_render():
    msg = KeyVariationPrompt.invoke({"query": "some comment"})
    assert msg is not None
    assert isinstance(xxm_prompt, str) and len(xxm_prompt) > 0
