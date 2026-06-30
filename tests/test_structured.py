from pydantic import BaseModel
from comment_agent.llm.structured import invoke_structured


class Out(BaseModel):
    name: str


class FlakyStructured:
    """Fails N times, then succeeds."""
    def __init__(self, fails):
        self.fails = fails
        self.calls = 0

    def invoke(self, _prompt):
        self.calls += 1
        if self.calls <= self.fails:
            raise ValueError("bad format")
        return Out(name="ok")


class FixupModel:
    """Plain model whose .invoke returns text the fix-up can parse."""
    def invoke(self, _prompt):
        class M:
            content = '{"name": "fixed"}'
        return M()


def test_succeeds_after_retries():
    s = FlakyStructured(fails=2)
    result = invoke_structured(s, FixupModel(), "p", Out, max_retries=3, fixup=False)
    assert result.name == "ok"


def test_falls_back_to_fixup():
    s = FlakyStructured(fails=99)  # never succeeds
    result = invoke_structured(s, FixupModel(), "p", Out, max_retries=2, fixup=True)
    assert result.name == "fixed"


def test_returns_none_when_all_fail():
    s = FlakyStructured(fails=99)

    class BadFixup:
        def invoke(self, _p):
            class M:
                content = "not json at all"
            return M()

    result = invoke_structured(s, BadFixup(), "p", Out, max_retries=2, fixup=True)
    assert result is None
