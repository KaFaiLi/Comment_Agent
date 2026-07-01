# Citation Grounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace free-text `Reference` fields with deterministic `[Cn]` citation IDs that resolve back to real comments, killing reference hallucination and giving auditors a `## Sources` follow-back trail.

**Architecture:** Stage 2 (review) only. Before the LLM call, each wrapped comment block is assigned a `[Cn]` ID and the model is told to cite only those IDs. After the call, references are resolved against the index — invented IDs cannot resolve and are dropped. Formatters render surviving refs inline and append a `## Sources` block with the original comment text.

**Tech Stack:** Python 3.12, pydantic v2, LangChain `ChatPromptTemplate`, pytest, `uv`.

## Global Constraints

- Run everything through `uv` (e.g. `uv run pytest ...`). Bare `python`/`pytest` fail — deps live in the uv venv.
- No new dependencies. Standard library `re` only.
- `wrap_comment` emits real XML tags: `<Tag on DATE>\n<body>\n</Tag on DATE>` (DATE is ISO `YYYY-MM-DD`). This is the on-the-wire form the splitter must match.
- Tests are plain `assert`, no fixtures/frameworks beyond pytest, mirroring existing `tests/`.
- `Reference` field stays typed `List[List[str]]` end to end. Resolution mutates its contents, never its type.
- Formatter `index` parameter is optional (default `None`) so existing `format_*(data)` callers/tests keep working.

---

### Task 1: `build_citation_index`

**Files:**
- Create: `comment_agent/review/citations.py`
- Test: `tests/test_citations.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `CITATION_RE = re.compile(r"\[(C\d+)\]")` — shared token matcher.
  - `build_citation_index(combined_text: str) -> tuple[str, dict]`. Returns `(annotated_text, index)` where `index[cid] = {"id": cid, "tag": str, "date": str, "text": str}`. `text` is the block **body** (comment content without the tag lines). `annotated_text` is each full block prefixed with `[Cn] `, blocks joined by `"\n\n"`. If no block matches, returns `(combined_text, {})` unchanged.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_citations.py
from comment_agent.review.citations import build_citation_index, CITATION_RE

WRAPPED = (
    "<Risk Metrics Alert Comment on 2024-01-15>\n"
    "Indicator Type: VAR\n"
    "</Risk Metrics Alert Comment on 2024-01-15> "
    "<PnL comments on 2024-02-03>\n"
    "Loss on FX book\n"
    "</PnL comments on 2024-02-03>"
)


def test_build_index_assigns_sequential_ids():
    annotated, index = build_citation_index(WRAPPED)
    assert set(index) == {"C1", "C2"}
    assert index["C1"]["date"] == "2024-01-15"
    assert index["C1"]["tag"] == "Risk Metrics Alert Comment"
    assert index["C1"]["text"] == "Indicator Type: VAR"
    assert index["C2"]["date"] == "2024-02-03"
    assert index["C2"]["text"] == "Loss on FX book"


def test_build_index_annotates_each_block_once():
    annotated, index = build_citation_index(WRAPPED)
    assert annotated.count("[C1]") == 1
    assert annotated.count("[C2]") == 1
    # the full tagged block is preserved for the model
    assert "<Risk Metrics Alert Comment on 2024-01-15>" in annotated


def test_build_index_no_blocks_returns_input_unchanged():
    annotated, index = build_citation_index("no tags here")
    assert annotated == "no tags here"
    assert index == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_citations.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'comment_agent.review.citations'`.

- [ ] **Step 3: Write minimal implementation**

```python
# comment_agent/review/citations.py
import re

CITATION_RE = re.compile(r"\[(C\d+)\]")

_BLOCK_RE = re.compile(
    r"<([^>]+?) on (\d{4}-\d{2}-\d{2})>\n(.*?)\n</\1 on \2>",
    re.DOTALL,
)


def build_citation_index(combined_text):
    index = {}
    annotated_blocks = []
    for i, m in enumerate(_BLOCK_RE.finditer(combined_text or ""), start=1):
        cid = f"C{i}"
        tag, date, body = m.group(1), m.group(2), m.group(3)
        index[cid] = {"id": cid, "tag": tag, "date": date, "text": body}
        annotated_blocks.append(f"[{cid}] {m.group(0)}")
    if not index:
        return combined_text, index
    return "\n\n".join(annotated_blocks), index
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_citations.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add comment_agent/review/citations.py tests/test_citations.py
git commit -m "feat: add build_citation_index for grounded references"
```

---

### Task 2: `resolve_references`

**Files:**
- Modify: `comment_agent/review/citations.py`
- Test: `tests/test_citations.py`

**Interfaces:**
- Consumes: `CITATION_RE`, and an `index` shaped like Task 1's output.
- Produces: `resolve_references(ref_lists: list[list[str]], index: dict) -> tuple[list[list[str]], int]`. For each per-topic list, keeps only `[Cn]` tokens present in `index`, rendered `"[Cn] (DATE)"`, deduped in first-seen order. Returns `(cleaned_lists, dropped_count)`. A reference string that yields no valid ID is omitted and increments `dropped_count`. Outer list length is preserved (one inner list per topic).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_citations.py
from comment_agent.review.citations import resolve_references

INDEX = {
    "C1": {"id": "C1", "tag": "Risk Metrics Alert Comment", "date": "2024-01-15", "text": "Indicator Type: VAR"},
    "C2": {"id": "C2", "tag": "PnL comments", "date": "2024-02-03", "text": "Loss on FX book"},
}


def test_resolve_keeps_valid_and_formats_with_date():
    cleaned, dropped = resolve_references([["[C1]", "[C2]"]], INDEX)
    assert cleaned == [["[C1] (2024-01-15)", "[C2] (2024-02-03)"]]
    assert dropped == 0


def test_resolve_drops_invented_ids():
    cleaned, dropped = resolve_references([["[C1]"], ["[C99]"]], INDEX)
    assert cleaned == [["[C1] (2024-01-15)"], []]
    assert dropped == 1


def test_resolve_drops_raw_date_reference():
    cleaned, dropped = resolve_references([["2024-01-15: system outage"]], INDEX)
    assert cleaned == [[]]
    assert dropped == 1


def test_resolve_dedupes_within_topic():
    cleaned, dropped = resolve_references([["[C1]", "[C1]"]], INDEX)
    assert cleaned == [["[C1] (2024-01-15)"]]
    assert dropped == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_citations.py -q`
Expected: FAIL — `ImportError: cannot import name 'resolve_references'`.

- [ ] **Step 3: Write minimal implementation**

```python
# append to comment_agent/review/citations.py
def resolve_references(ref_lists, index):
    cleaned = []
    dropped = 0
    for refs in (ref_lists or []):
        topic_refs = []
        seen = set()
        for ref in (refs or []):
            valid = [cid for cid in CITATION_RE.findall(str(ref)) if cid in index]
            if not valid:
                dropped += 1
                continue
            for cid in valid:
                if cid not in seen:
                    seen.add(cid)
                    topic_refs.append(f"[{cid}] ({index[cid]['date']})")
        cleaned.append(topic_refs)
    return cleaned, dropped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_citations.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add comment_agent/review/citations.py tests/test_citations.py
git commit -m "feat: add resolve_references to drop invented citations"
```

---

### Task 3: Sources appendix in formatters

**Files:**
- Modify: `comment_agent/review/formatters.py`
- Test: `tests/test_formatters.py`

**Interfaces:**
- Consumes: `CITATION_RE` from `citations`; an `index` shaped like Task 1's output; `data.Reference` already resolved to `"[Cn] (DATE)"` strings (Task 5 does the resolving before calling formatters).
- Produces: `format_key_metrics(data, index=None)` and `format_recurrent_topics(data, index=None)`. When `index` is provided and the review cites at least one ID, both append a trailing `## Sources` block: one line per cited ID, first-seen order, `- [Cn] — <tag> on <date>: "<text>"`. When `index` is `None` or nothing is cited, no Sources block is added and output is byte-identical to today's.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_formatters.py
from comment_agent.review.formatters import _sources_appendix

_IDX = {
    "C1": {"id": "C1", "tag": "Risk Metrics Alert Comment", "date": "2024-01-15", "text": "Indicator Type: VAR"},
}


def test_sources_appendix_lists_cited_ids():
    out = _sources_appendix([["[C1] (2024-01-15)"]], _IDX)
    assert "## Sources" in out
    assert '- [C1] — Risk Metrics Alert Comment on 2024-01-15: "Indicator Type: VAR"' in out


def test_sources_appendix_empty_when_nothing_cited():
    assert _sources_appendix([[]], _IDX) == ""
    assert _sources_appendix([["[C1] (2024-01-15)"]], None) == ""


def test_format_key_metrics_appends_sources_when_index_given():
    data = KeyVariation(
        KeyMetricTopic=["A"], KeyMetricVariation=[["v1"]],
        Reference=[["[C1] (2024-01-15)"]], Summary="s",
    )
    out = format_key_metrics(data, _IDX)
    assert "## Sources" in out


def test_format_key_metrics_no_sources_without_index():
    data = KeyVariation(
        KeyMetricTopic=["A"], KeyMetricVariation=[["v1"]],
        Reference=[["[C1] (2024-01-15)"]], Summary="s",
    )
    assert "## Sources" not in format_key_metrics(data)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_formatters.py -q`
Expected: FAIL — `ImportError: cannot import name '_sources_appendix'`.

- [ ] **Step 3: Write minimal implementation**

Add the import and helper at the top of `comment_agent/review/formatters.py`:

```python
from comment_agent.review.citations import CITATION_RE


def _sources_appendix(reference_lists, index):
    if not index:
        return ""
    cited = []
    seen = set()
    for refs in (reference_lists or []):
        for ref in (refs or []):
            for cid in CITATION_RE.findall(str(ref)):
                if cid in index and cid not in seen:
                    seen.add(cid)
                    cited.append(cid)
    if not cited:
        return ""
    lines = ["", "## Sources"]
    for cid in cited:
        e = index[cid]
        lines.append(f'- [{cid}] — {e["tag"]} on {e["date"]}: "{e["text"]}"')
    return "\n".join(lines)
```

Change `format_key_metrics` signature and end:

```python
def format_key_metrics(data, index=None):
    ...  # body unchanged
    appendix = _sources_appendix(getattr(data, "Reference", []) or [], index)
    if appendix:
        output.append(appendix)
    return "\n".join(output)
```

Change `format_recurrent_topics` signature and end the same way — after the Technical Issues lines, before `return`:

```python
def format_recurrent_topics(data, index=None):
    ...  # body unchanged through the Technical Issues append
    appendix = _sources_appendix(getattr(data, "Reference", []) or [], index)
    if appendix:
        output.append(appendix)
    return "\n".join(output)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_formatters.py -q`
Expected: PASS (existing 2 + new 4 = 6 passed).

- [ ] **Step 5: Commit**

```bash
git add comment_agent/review/formatters.py tests/test_formatters.py
git commit -m "feat: append Sources block to grounded reviews"
```

---

### Task 4: Instruct the model to cite `[Cn]` IDs

**Files:**
- Modify: `comment_agent/review/schemas.py` (both `Reference` field descriptions)
- Modify: `comment_agent/review/prompts.py` (both `<example>` blocks + one system-prompt line each)
- Test: `tests/test_prompts.py`

**Interfaces:**
- Consumes: nothing at runtime — this is prompt/schema text that steers the model.
- Produces: `Reference` field descriptions and both prompt examples that reference `[Cn]` IDs, guarded by a test asserting the instruction is present.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_prompts.py
from comment_agent.review.schemas import KeyVariation, Recurrent
from comment_agent.review.prompts import recurrentPrompt, KeyVariationPrompt


def test_reference_fields_instruct_bracket_ids():
    for schema in (KeyVariation, Recurrent):
        desc = schema.model_fields["Reference"].description
        assert "[C" in desc
        assert "raw date" in desc.lower()


def test_prompt_examples_use_bracket_ids():
    for prompt in (recurrentPrompt, KeyVariationPrompt):
        text = "".join(str(m) for m in prompt.messages)
        assert "[C1]" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prompts.py -q`
Expected: FAIL — the assertions don't find `[C` yet.

- [ ] **Step 3: Write minimal implementation**

In `comment_agent/review/schemas.py`, replace **both** `Reference` field descriptions (in `Recurrent` and `KeyVariation`) with:

```python
    Reference: List[List[str]] = Field(
        description=(
            """Cite ONLY by the bracketed citation IDs shown in the comments, for example [C3].
            Each topic's entry is a list of such IDs. Never write a raw date. Never invent an ID
            that is not shown in the comments. If no comment supports a topic, return an empty list for it."""
        )
    )
```

In `comment_agent/review/prompts.py`, replace the `"Reference"` arrays inside **both** `<example>` blocks so they use IDs instead of raw dates, e.g.:

```json
    "Reference": [
        ["[C1]", "[C2]"],
        ["[C3]"],
        ["[C4]", "[C5]"]
    ],
```

And add this line to **both** system prompts (right after the `DO NOT MAKE UP REFERENCE` sentence):

```
Each comment is prefixed with a bracketed citation ID such as [C3]. In the Reference field, cite those IDs only — never a raw date, never an ID that is not shown.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_prompts.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add comment_agent/review/schemas.py comment_agent/review/prompts.py tests/test_prompts.py
git commit -m "feat: instruct model to cite bracketed citation IDs"
```

---

### Task 5: Wire grounding into `_review_one`

**Files:**
- Modify: `comment_agent/review/service.py:49-72` (`_review_one`)
- Test: `tests/test_service.py`

**Interfaces:**
- Consumes: `build_citation_index`, `resolve_references` (Tasks 1–2); `format_key_metrics(data, index)`, `format_recurrent_topics(data, index)` (Task 3).
- Produces: no signature change to `_review_one`; it now feeds annotated text to the prompts, resolves both results' `Reference` fields against the index, emits a `[WARN] … unsupported reference(s) dropped` status when anything is dropped, and passes `index` to the formatters.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_service.py
from comment_agent.review.service import CommentReviewService as _CRS


def _patch_with_refs(svc, key_refs, rec_refs):
    svc.key_llm = type("K", (), {"invoke": lambda self, p: KeyVariation(
        KeyMetricTopic=["t"], KeyMetricVariation=[["v"]], Reference=key_refs, Summary="s")})()
    svc.recurrent_llm = type("R", (), {"invoke": lambda self, p: Recurrent(
        RecurrentTopic=["t"], RecurrentTopicExplain=[["e"]], pattern=[["p"]],
        Reference=rec_refs, Tech_issue=[], Summary="s")})()
    svc.model = type("M", (), {"invoke": lambda self, p: type("X", (), {"content": "summary"})()})()


def test_review_grounds_and_drops_invented_refs():
    logs = []
    svc = _CRS.__new__(_CRS)
    svc.cfg = _cfg()
    svc.status_callback = logs.append
    # one topic cites a valid ID, one cites an invented one
    _patch_with_refs(svc, key_refs=[["[C1]"], ["[C99]"]], rec_refs=[["[C1]"]])

    wrapped = ("<Risk Metrics Alert Comment on 2024-01-15>\n"
               "Indicator Type: VAR\n"
               "</Risk Metrics Alert Comment on 2024-01-15>")
    df = pd.DataFrame({"as_of_date": ["2024-01-15"], VAR_SVAR_COL: [wrapped]})

    result = svc.review(df, ["VAR_SVAR Comment"])
    review = next(iter(result["VAR_SVAR Comment"].values()))

    assert "## Sources" in review["key_variation"]
    assert "Indicator Type: VAR" in review["key_variation"]   # original text traced back
    assert "C99" not in review["key_variation"]               # invented ref dropped
    assert any("unsupported reference" in m for m in logs)     # drop was reported
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_service.py::test_review_grounds_and_drops_invented_refs -v`
Expected: FAIL — `## Sources` absent and `C99` still present (grounding not wired yet).

- [ ] **Step 3: Write minimal implementation**

Add imports at the top of `comment_agent/review/service.py`:

```python
from comment_agent.review.citations import build_citation_index, resolve_references
```

Replace the body of `_review_one` (currently lines 49-72) with:

```python
    def _review_one(self, task):
        quarter, comment_type, comments = task
        combined = " ".join(str(c) for c in comments)
        annotated, index = build_citation_index(combined)

        key_result = invoke_structured(
            self.key_llm, self.model,
            KeyVariationPrompt.invoke({"query": annotated}), KeyVariation,
            max_retries=self.cfg.max_retries, delay_seconds=2,
            label=f"Key variation {quarter}-{comment_type}",
            status_callback=self.status_callback,
        )
        recurrent_result = invoke_structured(
            self.recurrent_llm, self.model,
            recurrentPrompt.invoke({"query": annotated}), Recurrent,
            max_retries=self.cfg.max_retries, delay_seconds=2,
            label=f"Recurrent {quarter}-{comment_type}",
            status_callback=self.status_callback,
        )
        if key_result is None or recurrent_result is None:
            return None

        key_result.Reference, dropped_k = resolve_references(key_result.Reference, index)
        recurrent_result.Reference, dropped_r = resolve_references(recurrent_result.Reference, index)
        if dropped_k or dropped_r:
            self._emit(
                f"[WARN] {dropped_k + dropped_r} unsupported reference(s) dropped "
                f"| {quarter}-{comment_type}"
            )

        return {
            "key_variation": format_key_metrics(key_result, index),
            "recurrent": format_recurrent_topics(recurrent_result, index),
        }
```

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS — the new test plus all pre-existing tests green.

- [ ] **Step 5: Commit**

```bash
git add comment_agent/review/service.py tests/test_service.py
git commit -m "feat: ground quarterly-review references via citation index"
```

---

## Self-Review

**Spec coverage:**
- `build_citation_index` / `[Cn]` assignment → Task 1. ✅
- `resolve_references` / drop invented → Task 2. ✅
- `## Sources` appendix (Depth-1 follow-back to original text) → Task 3. ✅
- Schema + prompt cite-by-ID instructions → Task 4. ✅
- Service wiring, annotated query, drop-count WARN, formatter index → Task 5. ✅
- Cut items (no verifier LLM, no confidence, no per-row tracing, no Stage 1 change) → honored; `wrap_comment` XML-tag change already shipped separately and is a precondition, not part of this plan. ✅

**Placeholder scan:** none — every code and test step is concrete.

**Type consistency:** `index` shape `{cid: {"id","tag","date","text"}}` identical across Tasks 1/2/3/5. `CITATION_RE` defined in Task 1, imported in Tasks 2/3. `resolve_references` returns `(list[list[str]], int)` and is consumed that way in Task 5. `format_*` gain `index=None`, called with `index` in Task 5. Consistent.
