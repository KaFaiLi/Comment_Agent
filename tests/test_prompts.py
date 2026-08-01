from comment_agent.review.schemas import (
    Recurrent,
    RecurrentTopicItem,
    KeyVariation,
    KeyMetricItem,
)
from comment_agent.review.prompts import (
    EXECUTIVE_SUMMARY_PROMPT,
    KEY_VARIATION_PROMPT,
    RECURRENT_TOPICS_PROMPT,
)


def test_schemas_have_expected_fields():
    assert "topics" in Recurrent.model_fields
    assert "tech_issues" in Recurrent.model_fields
    assert "summary" in Recurrent.model_fields
    assert "topics" in KeyVariation.model_fields
    assert "summary" in KeyVariation.model_fields


def test_topic_items_are_flat_objects():
    # the schema redesign contract: no parallel List[List[str]] fields —
    # everything about a topic lives on one flat object
    assert set(RecurrentTopicItem.model_fields) == {
        "topic", "context", "recurrence_reason", "implications", "pattern", "references",
    }
    assert set(KeyMetricItem.model_fields) == {"topic", "analysis", "references"}


def test_prompts_render():
    msg = KEY_VARIATION_PROMPT.invoke({"query": "some comment"})
    assert msg is not None
    assert isinstance(EXECUTIVE_SUMMARY_PROMPT, str) and len(EXECUTIVE_SUMMARY_PROMPT) > 0


def test_recurrent_prompt_uses_a_system_message_for_instructions():
    messages = RECURRENT_TOPICS_PROMPT.invoke({"query": "some comment"}).to_messages()
    assert messages[0].type == "system"
    assert messages[1].type == "human"


def test_reference_fields_instruct_bracket_ids():
    for item_schema in (KeyMetricItem, RecurrentTopicItem):
        desc = item_schema.model_fields["references"].description
        assert "[C" in desc
        assert "raw date" in desc.lower()


def test_prompt_examples_use_bracket_ids():
    for prompt in (RECURRENT_TOPICS_PROMPT, KEY_VARIATION_PROMPT):
        text = "".join(str(m) for m in prompt.messages)
        assert "[C1]" in text


def test_prompt_examples_match_schema_shape():
    import json

    for prompt, schema in (
        (RECURRENT_TOPICS_PROMPT, Recurrent), (KEY_VARIATION_PROMPT, KeyVariation)
    ):
        rendered = prompt.invoke({"query": "q"})
        text = "".join(m.content for m in rendered.to_messages())
        start, end = text.find("<example>"), text.find("</example>")
        assert start != -1 and end != -1
        example = text[start + len("<example>"):end]
        schema.model_validate(json.loads(example))
