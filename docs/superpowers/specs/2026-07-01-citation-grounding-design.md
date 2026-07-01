# Citation Grounding (Deterministic References)

**Date:** 2026-07-01
**Status:** Approved design, pending implementation
**Scope:** Stage 2 (review) only. No Stage 1 (data-prep) changes.

## Problem

`KeyVariation.Reference` and `Recurrent.Reference` are free-text `List[List[str]]`
the model writes by hand. The only guard against fabrication is the prompt string
"DO NOT MAKE UP REFERENCE". The model can and does invent dates and quotes, and an
auditor has no deterministic way to trace a cited reference back to the original
comment.

## Goal

References become verifiable citation IDs, not free-text dates. An invented citation
cannot resolve, so it is dropped before it reaches the report. Every surviving
reference traces back to the exact original comment text via a `## Sources` appendix.

Non-goal (explicitly cut): tracing a citation to a single source-CSV row. Stage 1
groups comments by `as_of_date`, so a wrapped block aggregates several CSV rows;
per-cell tracing is impossible without ungrouping the pipeline. Cut as not worth the
plumbing.

## Mechanism

Each comment reaching Stage 2 is already a wrapped block:

```
<Risk Metrics Alert Comment on 2024-01-15>
Indicator Type: VAR ...
</Risk Metrics Alert Comment on 2024-01-15>
```

That block is the citation unit.

1. Before invoking the LLM, split the combined text into blocks, assign `[C1]…[Cn]`,
   and prepend each ID to its block. The model receives the annotated text.
2. The model is instructed (schema field + prompt) to cite **only** by bracketed ID,
   e.g. `[C3]`. Never a raw date, never an unlisted ID.
3. After the LLM returns, resolve each emitted reference: extract `[Cn]` tokens, keep
   only IDs present in the index, drop the rest. An invented `[C99]` resolves to
   nothing and disappears.

Grounding is a dict lookup, not a judgment call. No verifier LLM, no confidence model.

## Components

### New: `comment_agent/review/citations.py`

```python
CITATION_RE = re.compile(r"\[(C\d+)\]")

def build_citation_index(combined_text: str) -> tuple[str, dict]:
    """Split wrapped blocks, assign [Cn], return (annotated_text, index).

    index[id] = {"id": "C1", "tag": str, "date": str, "text": str}
    - `tag` and `date` parsed from the opening `<Tag on DATE>` line.
    - `text` is the full wrapped block (original content for the appendix).
    - annotated_text is the blocks re-joined, each prefixed with its `[Cn]`.
    """

def resolve_references(ref_lists: list[list[str]], index: dict) -> tuple[list[list[str]], int]:
    """For each reference string, keep only [Cn] tokens present in `index`,
    rendered as `[Cn] (DATE)`. Return (cleaned_lists, dropped_count).
    A reference string with no valid ID collapses to empty and is omitted."""
```

Block splitting: regex on the opening tag `<([^>]+?) on (\d{4}-\d{2}-\d{2})>` and its
matching close via backreference. `AlertProcessor.wrap_comment` now emits real angle
brackets (`<Tag on DATE>…</Tag on DATE>`), so the splitter matches literal `<`/`>`.

### Changed: `comment_agent/review/service.py` `_review_one`

```
combined = " ".join(str(c) for c in comments)
annotated, index = build_citation_index(combined)
# prompts get {"query": annotated} instead of combined
# after each structured result:
key_result.Reference, dropped_k = resolve_references(key_result.Reference, index)
recurrent_result.Reference, dropped_r = resolve_references(recurrent_result.Reference, index)
if dropped_k or dropped_r:
    self._emit(f"[WARN] {dropped_k + dropped_r} unsupported reference(s) dropped | {quarter}-{comment_type}")
# pass `index` into the formatters so they can emit the Sources appendix
```

### Changed: `comment_agent/review/schemas.py`

Both `Reference` field descriptions:

> Cite ONLY by bracketed citation IDs shown in the comments, e.g. `[C3]`. Each
> reference entry is a list of such IDs. Never write a raw date. Never invent an ID
> that is not shown. If no comment supports a topic, return an empty list for it.

### Changed: `comment_agent/review/prompts.py`

- Replace the raw-date `Reference` entries in both `<example>` blocks with `[Cn]`
  IDs (e.g. `["[C1]", "[C3]"]`).
- Add one line to both system prompts: comments are prefixed with `[Cn]` IDs; cite
  those IDs, nothing else.

### Changed: `comment_agent/review/formatters.py`

- Inline references render as `[Cn] (DATE)` (resolve_references already formats this).
- Both formatters take the `index` and append a `## Sources` block listing every
  cited ID once:
  `- [C3] — Risk Metrics Alert Comment on 2024-01-15: "<full original comment text>"`
  Only IDs actually cited in that review appear (keep the appendix tight). If none
  cited, omit the Sources block.

## Data flow

```
comments (list of wrapped blocks)
  -> " ".join                         (service._review_one, unchanged)
  -> build_citation_index             -> (annotated, index)
  -> prompts.invoke({"query": annotated})
  -> LLM returns Reference = [["[C3]", "[C7]"], ...]
  -> resolve_references(refs, index)  -> cleaned refs + dropped count
  -> format_* (refs inline + Sources appendix from index)
```

The model cannot cite a date that has no block: it only ever sees IDs, and only
listed IDs resolve.

## Testing

Mirror the existing `tests/` layout (`assert`-based, no new frameworks).

`tests/test_citations.py`:
- index built from a 3-block sample: IDs `C1..C3`, correct date/tag/text parsed.
- annotated text contains each `[Cn]` prefix exactly once.
- `resolve_references` keeps valid IDs, renders `[Cn] (DATE)`.
- invented `[C99]` dropped; dropped_count == 1.
- a raw-date reference string (no `[Cn]`) collapses to empty, counted as dropped.
- splitter matches the real `wrap_comment` output form (`<Tag on DATE>`).

Extend `tests/test_formatters.py`:
- `## Sources` appendix lists only cited IDs, with full original text.
- no Sources block when no references cited.

## Ponytail notes / skipped

- No second (verifier) LLM pass — ID resolution is deterministic.
- No confidence scoring.
- No per-CSV-row tracing (Depth B) — grouping by date forbids it; documented ceiling.
- No Stage 1 changes.
