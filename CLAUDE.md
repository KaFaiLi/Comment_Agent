# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

This is a [uv](https://docs.astral.sh/uv/) project targeting Python 3.12.

```bash
uv sync                    # install dependencies
uv run streamlit run main.py   # launch the app
```

No tests, linter, or build step exist yet.

> Note: `pyproject.toml` declares `dependencies = []`, but the code imports `streamlit`, `langchain_core`, `pydantic`, `pandas`, and `docx` (python-docx). It also imports `socgenai_llm` (an internal Société Générale package providing `GenAIChatModel`, the wrapper over SoGPT / `gpt-4.1-nano`). These must be installed manually until `pyproject.toml` is filled in. `socgenai_llm` is not on public PyPI.

## What this is

A Streamlit tool ("Comment Review Tool") that helps auditors review trading-desk risk comments. An auditor uploads three CSVs, selects desks and comment types, and the tool produces per-quarter AI reviews plus an executive summary, downloadable as Word documents.

## Architecture

The flow is a two-stage pipeline: **deterministic data prep** → **LLM review**. `main.py` is the Streamlit UI that wires the two together and holds all state in `st.session_state`.

### Stage 1 — `src/data_processing.py` (`AlertProcessor`)

Takes three uploaded CSVs (certification alerts, income-attribution alerts, PnL comments) and produces one DataFrame keyed by `as_of_date`. Each of the five comment types is processed separately, then outer-merged on date:

| Comment type | Source CSV | Filter |
|---|---|---|
| VAR_SVAR | cert | `indicator_name in {VAR, SVAR}` |
| Stress Test | cert | `indicator_name == STRESS TEST` |
| Risk Metrics | cert | everything else |
| Income Attribution | ia | by `perimeter_name` |
| PnL | pnl | regex match on desk |

Key conventions to preserve:
- Desk filtering matches against multiple columns **and** does a regex substring match on the comment text (`_filter_by_desks`).
- Every comment is wrapped in pseudo-XML tags via `wrap_comment` (`<Tag on DATE>...</Tag>`) — this framing is what the LLM prompts expect.
- `create_final_comment` explodes list-valued columns and concatenates all non-empty comments per row into the `All Comment for LLM` column.
- The exact column names (e.g. `"VAR_SVAR Comment for LLM"`) are the contract between this stage and Stage 2 — they're re-listed in `COMMENT_COLUMNS` in `review_service.py` and `COMMENT_TYPE_OPTIONS` in `main.py`. Renaming one means renaming all three.

### Stage 2 — `src/review_service.py` (`CommentReviewService`)

Groups the final DataFrame by quarter (`as_of_date.dt.to_period("Q")`) and comment type, then for each (quarter, type) pair makes **two** structured LLM calls:
- `key_llm` → `KeyVariation` schema (significant metric variations)
- `recurrent_llm` → `Recurrent` schema (recurring topics)

Both use LangChain's `with_structured_output(..., method="function_calling", strict=True)`. A third plain-text call (`xxm_prompt`) generates the cross-quarter executive summary.

- `src/prompt.py` — the Pydantic schemas (`Recurrent`, `KeyVariation`) and `ChatPromptTemplate`s. The schemas' field descriptions are the actual instructions to the model; the prompts cast the model as a "market activities auditor." Edit prompts/schemas here, not inline.
- `src/review_formatters.py` — turns the structured LLM objects into markdown sections. Defensively index-aligned (topics/explanations/references can be ragged-length lists).
- `src/llm_utils.py` — `invoke_with_retry`: retries N times, returns a `default` (usually `None`) instead of raising so one failed quarter doesn't kill the whole run.
- `src/formatting.py` — `DocumentExporter`: a minimal markdown→`python-docx` converter (handles `#`/`##`/`###`, `- ` bullets, `**bold**`). Used both to save `.docx` to disk and to produce in-memory `BytesIO` buffers for Streamlit download buttons.

### Status reporting

Long-running work emits progress via a `status_callback` threaded from `main.py` into the services. Every `_emit_status` / `emit` call also `print()`s. To surface new progress in the UI, route through this callback rather than printing directly.

### Outputs

Everything is written to `Outputs/`: per-type intermediate `.xlsx` (one per comment type), `All comments.xlsx`, per-type `quarterly_reviews_summary_*.md`, and `executive_summary_*.docx`. The directory is created on demand.
