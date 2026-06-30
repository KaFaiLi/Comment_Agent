# Comment Agent Rewrite — Design

**Date:** 2026-06-30
**Status:** Approved (design), pending spec review

## Goal

Restructure the existing single-file Streamlit "Comment Review Tool" into a modular, maintainable backend package with a thin Streamlit frontend. Swap the internal `socgenai_llm.GenAIChatModel` for LangChain Azure OpenAI, modernize the LLM calling, add parse-failure handling, parallelize LLM calls with retry, make the UI survive downloads, auto-save all outputs, and ship a sample-data generator.

**Behavior of the data-processing logic is preserved** — the five comment types, their filters, the `wrap_comment` framing, and the per-date column contract stay identical. This is a restructure, not a redesign of the audit logic.

## Decisions (from brainstorming)

1. **Backend/frontend split:** in-process service layer. A pure-Python `comment_agent/` package with no Streamlit imports, imported directly by `frontend/app.py`. No FastAPI/HTTP server (YAGNI for a local auditor tool).
2. **Parse-failure handling:** retry the structured call N times → one fix-up pass (reformat into valid JSON) → skip that `(quarter, type)` and log. Run continues.
3. **Config:** `AppConfig` loaded from env / `.env` — Azure endpoint, deployment, API key, API version, plus `max_workers`, `max_retries`, `max_tokens`, `output_dir`.
4. **Concurrency:** `ThreadPoolExecutor`, one `(quarter, comment_type)` review per task. Threads (not async) — I/O-bound, simpler with Streamlit.

## Module Layout

```
comment_agent/                  # backend package (pure python, no streamlit)
├── config.py                   # AppConfig from env/.env
├── llm/
│   ├── client.py               # build AzureChatOpenAI + structured-output wrappers
│   ├── structured.py           # invoke_structured: retry → fix-up → None
│   └── concurrency.py          # run_parallel: ThreadPoolExecutor
├── processing/
│   ├── alerts.py               # AlertProcessor (behavior preserved)
│   └── columns.py              # single source of truth for "... Comment for LLM" names
├── review/
│   ├── schemas.py              # Recurrent, KeyVariation
│   ├── prompts.py              # ChatPromptTemplates + xxm_prompt
│   ├── formatters.py           # format_key_metrics / format_recurrent_topics
│   └── service.py              # CommentReviewService orchestration
├── export/
│   └── documents.py            # DocumentExporter (md → docx)
└── persistence.py              # save intermediates + results to output_dir

frontend/
└── app.py                      # Streamlit UI

scripts/
└── generate_sample_data.py     # synthetic CSVs for testing

tests/                          # one smoke test per backend module (pytest)
```

Maps 1:1 to current files, split by responsibility. `columns.py` removes the column-name strings currently triplicated across `data_processing.py`, `review_service.py`, and `main.py`.

## Component Detail

### config.py
`AppConfig` dataclass. Fields: `azure_endpoint`, `azure_deployment`, `api_key`, `api_version`, `max_tokens` (default 32768), `temperature` (0.1), `max_workers` (default 4), `max_retries` (default 3), `output_dir` (default `Outputs`). Loaded from environment (`.env` via `python-dotenv` or `os.environ`). Missing required Azure values fail fast with a clear message.

### llm/client.py
Builds `AzureChatOpenAI` (from `langchain-openai`) from `AppConfig`. Exposes the base chat model (for plain calls like the executive summary and the fix-up pass) and a helper to bind a schema via `with_structured_output(Schema, method="json_schema")` (strict JSON schema — the modern replacement for the current `method="function_calling"`).

### llm/structured.py
```python
def invoke_structured(structured_llm, base_llm, prompt_value, schema, *,
                      max_retries, label, status_callback=None, fixup=True) -> BaseModel | None
```
1. Invoke `structured_llm`. On exception / `ValidationError` → retry up to `max_retries` (short delay between).
2. Still failing and `fixup=True` → one plain `base_llm` call: "reformat the following into JSON matching this schema", then validate with the Pydantic schema.
3. Fix-up fails → return `None`, log via `status_callback`. Caller skips.

No `OutputFixingParser` dependency — the fix-up is a few lines we control.

### llm/concurrency.py
```python
def run_parallel(tasks, fn, *, max_workers, status_callback=None) -> list
```
Wraps `ThreadPoolExecutor`. Each task is one `(quarter, comment_type)` review (which internally makes its 2 structured calls via `invoke_structured`). A task that returns `None` is collected as a skip. Retry lives inside `invoke_structured`, so the pool just fans out and gathers. `ponytail:` comment marks the worker-count ceiling.

### processing/alerts.py + columns.py
`AlertProcessor` moves over unchanged in behavior: `_filter_by_desks`, `wrap_comment`, the five `process_*` methods, `merge_comments`, `create_final_comment`. The column-name constants (`"VAR_SVAR Comment for LLM"`, etc.) live in `columns.py` and are imported wherever needed. Processor `__init__` validates required CSV columns and raises a clear error if missing.

### review/service.py
`CommentReviewService.review()` groups the final DataFrame by quarter and comment type, builds the task list, and calls `run_parallel`. Each task runs the Key Variation + Recurrent structured calls through `invoke_structured`, then `formatters`. Executive summary (`xxm_prompt`) runs as a plain call after. Progress flows through the existing `status_callback` pattern.

### export/documents.py
`DocumentExporter` moves over unchanged (markdown → `python-docx`, disk save + `BytesIO` buffers).

### persistence.py
Writes on generation, before the UI renders downloads:
- intermediates: per-type `.xlsx` + `All comments.xlsx`
- results: `quarterly_reviews_summary_<type>.md`, `<type>_full_review.docx`, `executive_summary_<type>.docx`

`Outputs/` always holds the full set even if the user never downloads. Download buttons hand back the same bytes.

### frontend/app.py
Streamlit UI preserved: sidebar uploads (3 CSVs), desk text input, comment-type multiselect, Generate button, result tabs with markdown + two download buttons + the AI-disclaimer warning.

**Download survives rerun (req #6):** all results cached in `st.session_state` (`quarterly_reviews`, `markdown_contents`, `executive_summaries`). Rendering reads only from state. Review runs **only** on the Generate button — a download-triggered rerun recomputes nothing and re-renders from state. Buffers built from cached content.

## Data Flow

```
upload 3 CSVs
  → AlertProcessor.merge_comments(desks)
  → AlertProcessor.create_final_comment
  → persistence.save_intermediates
  → group by (quarter, comment_type)
  → run_parallel(review_one)            # threaded, retry+fixup inside
      → invoke_structured(KeyVariation)
      → invoke_structured(Recurrent)
      → formatters
  → executive summary (plain call)
  → st.session_state
  → persistence.save_results
  → render tabs + download buttons
```

## Error Handling

- Failed `(quarter, type)` → `None` → skipped + logged, run continues.
- Missing CSV columns → fail fast at processor init with a clear message.
- Azure auth/config errors → surfaced in the UI, not swallowed.
- LLM parse failures → retry → fix-up → skip (above).

## Testing

`pytest`, one smoke test per backend module. No fixtures/frameworks beyond pytest, no per-function suites:
- processor produces expected columns on sample data
- formatters handle ragged-length lists
- `invoke_structured` falls back correctly (mocked LLM: bad output → fix-up → valid)
- `run_parallel` collects results and skips `None`
- sample-data script runs and emits valid CSVs

## Sample Data Generator

`scripts/generate_sample_data.py` emits 3 CSVs matching the exact columns the processors read:
- **cert:** `perimeter_name, trading_desk, indicator_name, error_message, comment, managerial_validation_comment, related_scenario, as_of_date`
- **ia:** `perimeter_name, mmg_bl_comment, mmg_xbc_comment, managerial_validation_comment, as_of_date`
- **pnl:** `Trading Desk, Comments, Date`

Spans ~2 quarters, desks EQD + FIC, indicators VAR/SVAR/STRESS TEST/other, some blank comments. `--rows` / `--seed` flags, deterministic, stdlib `random` only (no faker).

## Dependencies

Fill in `pyproject.toml` (currently empty): `streamlit`, `langchain-openai`, `langchain-core`, `pydantic`, `pandas`, `python-docx`, `openpyxl`, `python-dotenv`. Dev: `pytest`. Removes the internal `socgenai_llm`.

## Out of Scope

FastAPI/HTTP server, async, DB, caching beyond `session_state`, DI framework, unrelated refactoring, changes to audit/prompt logic beyond the structured-output method swap.
