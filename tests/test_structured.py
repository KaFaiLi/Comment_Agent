from pydantic import BaseModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from comment_agent.llm.structured import (
    invoke_structured,
    _deterministic_fix,
    _raw_text,
)
from comment_agent.review.schemas import KeyVariation


class Out(BaseModel):
    name: str


class Msg:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.additional_kwargs = {"tool_calls": tool_calls or []}


def _ok(name="ok"):
    return {"parsed": Out(name=name), "parsing_error": None, "raw": Msg()}


def _parse_error(raw_content):
    return {"parsed": None, "parsing_error": ValueError("bad"), "raw": Msg(raw_content)}


class Structured:
    """Returns queued include_raw dicts; repeats the last once drained."""
    def __init__(self, results):
        self.results = results
        self.i = 0

    def invoke(self, _prompt):
        r = self.results[self.i]
        self.i = min(self.i + 1, len(self.results) - 1)
        return r


def _fake_llm(*responses):
    """Real Runnable so OutputFixingParser can build its LCEL fix chain."""
    return FakeListChatModel(responses=list(responses) or ["{}"])


# --- orchestration ---------------------------------------------------------

def test_clean_success():
    result = invoke_structured(Structured([_ok()]), _fake_llm(), "p", Out, fixup=False)
    assert result.name == "ok"


def test_deterministic_fix_recovers_without_llm():
    # raw carries valid JSON the strict binding failed to surface; LLM never called
    s = Structured([_parse_error('{"name": "recovered"}')])
    result = invoke_structured(s, _fake_llm("SHOULD NOT BE CALLED"), "p", Out,
                               max_retries=1, fixup=True)
    assert result.name == "recovered"


def test_llm_fix_fallback():
    s = Structured([_parse_error("totally broken {")])
    result = invoke_structured(s, _fake_llm('{"name": "fixed"}'), "p", Out,
                               max_retries=2, fixup=True)
    assert result.name == "fixed"


def test_returns_none_when_unrecoverable():
    s = Structured([_parse_error("totally broken {")])
    result = invoke_structured(s, _fake_llm("no", "still no", "nope", "never"), "p", Out,
                               max_retries=1, fixup=True)
    assert result is None


# --- tier-1 deterministic repair on the real schema ------------------------

def test_key_case_mismatch():
    raw = '{"keymetrictopic": ["A"], "keymetricvariation": [["x"]], "reference": [["[C1]"]], "summary": "s"}'
    out = _deterministic_fix(raw, KeyVariation)
    assert out is not None and out.KeyMetricTopic == ["A"] and out.Summary == "s"


def test_list_became_string_fences_trailing_comma():
    raw = '```json\n{"KeyMetricTopic": "A", "KeyMetricVariation": [["x"]], "Reference": [["[C1]"]], "Summary": "s",}\n```'
    out = _deterministic_fix(raw, KeyVariation)
    assert out is not None and out.KeyMetricTopic == ["A"]  # bare str wrapped to list


def test_raw_text_from_tool_call_args():
    m = Msg(content="", tool_calls=[{"function": {"arguments": '{"a": 1}'}}])
    assert _raw_text(m) == '{"a": 1}'


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("ok")
