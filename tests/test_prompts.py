from comment_agent.review.schemas import Recurrent, KeyVariation
from comment_agent.review.prompts import recurrentPrompt, KeyVariationPrompt, xxm_prompt


def test_schemas_have_expected_fields():
    assert "RecurrentTopic" in Recurrent.model_fields
    assert "KeyMetricTopic" in KeyVariation.model_fields


def test_prompts_render():
    msg = KeyVariationPrompt.invoke({"query": "some comment"})
    assert msg is not None
    assert isinstance(xxm_prompt, str) and len(xxm_prompt) > 0


def test_reference_fields_instruct_bracket_ids():
    for schema in (KeyVariation, Recurrent):
        desc = schema.model_fields["Reference"].description
        assert "[C" in desc
        assert "raw date" in desc.lower()


def test_prompt_examples_use_bracket_ids():
    for prompt in (recurrentPrompt, KeyVariationPrompt):
        text = "".join(str(m) for m in prompt.messages)
        assert "[C1]" in text
