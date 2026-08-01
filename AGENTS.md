# AGENTS.md

This file provides guidance to coding agents (Claude Code and others) when working
with code in this repository.

## Commands

This is a [uv](https://docs.astral.sh/uv/) project targeting Python 3.12.

```bash
uv sync                                # install dependencies (declared in pyproject.toml)
cp .env.example .env                   # then fill in Azure OpenAI values
uv run streamlit run frontend/app.py   # launch the app
uv run pytest                          # run the test suite
uv run python -m scripts.generate_sample_data --out sample_data   # generate sample CSVs
```

Dependencies are declared in `pyproject.toml` (`streamlit`, `langchain-openai`,
`langchain-core`, `pydantic`, `pandas`, `python-docx`, `openpyxl`,
`python-dotenv`, `langchain-classic`; `pytest` in the dev group). The LLM is
Azure OpenAI via `langchain_openai.AzureChatOpenAI`, configured from environment
variables (see `.env.example`). There is no linter or build step.

## What this is

A Streamlit tool ("Comment Review Tool") that helps market-activities auditors
review trading-desk risk comments. An auditor uploads three CSVs, selects desks
and comment types, and the tool produces per-quarter AI reviews plus an
executive summary, downloadable as Word documents.

## Architecture

The flow is a two-stage pipeline: **deterministic data prep** → **LLM review**.
`frontend/app.py` is a thin Streamlit entry point. Reusable widgets live in
`frontend/components/`, session-state ownership lives in `frontend/session.py`,
thread-aware UI status handling lives in `frontend/status.py`, and use-case
orchestration lives in `frontend/workflows/`. All backend logic lives in the
`comment_agent/` package.

### Stage 1 — `comment_agent/processing/alerts.py` (`AlertProcessor`)

Takes three uploaded CSVs (certification alerts, income-attribution alerts, PnL
comments) and produces one DataFrame keyed by `as_of_date`. Each of the five
comment types is processed separately, then outer-merged on date:

| Comment type | Source CSV | Filter |
|---|---|---|
| VAR_SVAR | cert | `indicator_name in {VAR, SVAR}` |
| Stress Test | cert | `indicator_name == STRESS TEST` |
| Risk Metrics | cert | everything else |
| Income Attribution | ia | by `perimeter_name` |
| PnL | pnl | regex match on desk |

Key conventions to preserve:
- Desk filtering matches against multiple columns **and** does a regex substring
  match on the comment text (`_filter_by_desks`).
- Every comment is wrapped in pseudo-XML tags via `wrap_comment`
  (`<Tag on DATE>...</Tag>`) — this framing is what the citation index and the
  LLM prompts expect.
- `create_final_comment` explodes list-valued columns and concatenates all
  non-empty comments per row into the `All Comment for LLM` column.
- The exact column names (e.g. `"VAR_SVAR Comment for LLM"`) are the contract
  between the two stages. They are defined once in
  `comment_agent/processing/columns.py` (`COMMENT_COLUMNS`, re-used as
  `COMMENT_TYPE_OPTIONS`) and consumed by `review/service.py`. Renaming one
  means renaming it in that single source.

### Stage 2 — `comment_agent/review/service.py` (`CommentReviewService`)

Groups the final DataFrame by quarter (`as_of_date.dt.to_period("Q")`) and
comment type, then for each (quarter, type) pair makes **two** structured LLM
calls:
- `key_variation_model` → `KeyVariation` schema (significant metric variations)
- `recurrent_topics_model` → `Recurrent` schema (recurring topics)

Both bind with `with_structured_output(schema, method="json_schema",
include_raw=True)` (see `llm/client.py`). A third plain-text call
(`EXECUTIVE_SUMMARY_PROMPT`) generates the cross-quarter executive summary. Per-(quarter, type) tasks run
concurrently through `run_parallel`.

- `comment_agent/review/prompts.py` — the `ChatPromptTemplate`s. They cast the
  model as a "market activities auditor" and require citation IDs (never
  invented references).
- `comment_agent/review/schemas.py` — the Pydantic schemas (`Recurrent`,
  `KeyVariation`, and their per-topic item models). Each topic is one
  self-contained object; the field descriptions are the actual instructions to
  the model. Edit prompts/schemas here, not inline.
- `comment_agent/review/citations.py` — `build_citation_index` assigns a `[Cn]`
  ID to each wrapped comment block and annotates the text; `resolve_*` grounds
  each topic's `references` against that index and drops unsupported IDs.
- `comment_agent/review/formatters.py` — turns the structured LLM objects into
  markdown sections, including a `## Sources` appendix. Defensively
  index-aligned (topics/analysis/references can be ragged-length lists).
- `comment_agent/llm/structured.py` — `invoke_structured`: the primary
  structured call plus a two-tier repair path (deterministic JSON fix, then a
  same-model `OutputFixingParser`). Returns `None` instead of raising so one
  failed quarter doesn't kill the whole run.
- `comment_agent/llm/concurrency.py` — `run_parallel`: a thread pool over
  I/O-bound LLM calls that preserves input order and skips failures.
- `comment_agent/llm/client.py` — builds the `AzureChatOpenAI` model and binds
  schemas.
- `comment_agent/export/documents.py` — `DocumentExporter`: a minimal
  markdown→`python-docx` converter (handles `#`/`##`/`###`, `- ` bullets,
  `**bold**`). Used both to save `.docx` to disk and to produce in-memory
  `BytesIO` buffers for Streamlit download buttons.
- `comment_agent/persistence.py` — writes the intermediate `.xlsx` and the
  per-type markdown/`.docx` results.

### Configuration — `comment_agent/config.py` (`AppConfig`)

`AppConfig.from_env()` loads Azure credentials and tuning knobs from the
environment (`.env` is loaded via `python-dotenv`). Required:
`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_KEY`,
`OPENAI_API_VERSION`. Optional `COMMENT_AGENT_*` overrides cover worker count,
retries, token budget, output dir, and logging (see below). Never log the API
key.

### Logging — `comment_agent/logging_config.py`

Backend logging goes through Python's `logging` under the `comment_agent`
namespace. Do **not** add bare `print()` calls.

- `get_logger(__name__)` — every backend module has a module-level logger.
- `configure_logging(...)` — installs a console handler and a rotating file
  handler (5 MiB × 3 backups). It is idempotent (safe to call on every Streamlit
  rerun) and force-reconfigurable without duplicating handlers. `frontend/app.py`
  calls it at startup and again per run from `AppConfig`. Settings come from
  `COMMENT_AGENT_LOG_LEVEL`, `COMMENT_AGENT_LOG_DIR`, `COMMENT_AGENT_LOG_FILE`
  (set the file/dir to `"none"` for console-only).
- `emit_status(logger, status_callback, msg)` — the single choke point for
  progress reporting. It maps the bracketed status tags (`[INFO]`, `[API ERROR]`,
  `[PARSE ERROR]`, `[SKIPPED]`, `[TASK FAILED]`, ...) to log levels, logs the
  line, **and** forwards the raw message to the UI `status_callback`. A raising
  callback is caught and logged so a flaky UI sink can never abort a run.
- The package `__init__` attaches a `NullHandler`, so modules can log during
  import/tests without emitting output until an entry point configures logging.

To surface new progress in the UI, route it through `emit_status` (or the
`_emit` helpers that wrap it), not through `print`.

### Status reporting

Long-running work emits progress via a `status_callback` threaded from
`frontend/app.py` into the services. The UI attaches the Streamlit
`ScriptRunContext` to worker threads before touching a widget, and shares one
placeholder (last-writer-wins). Every status line is also logged via
`emit_status`.

### Outputs

Everything is written to `Outputs/` (configurable via
`COMMENT_AGENT_OUTPUT_DIR`): per-type intermediate `.xlsx`, `All comments.xlsx`,
per-type `quarterly_reviews_summary_*.md`, `*_full_review.docx`, and
`executive_summary_*.docx`. The directory is created on demand. Logs default to
`logs/comment_agent.log`. Both `Outputs/` and `logs/` are gitignored.

## Tests

Tests live in `tests/` and run with `uv run pytest`. There is one test module
per backend module (`test_alerts.py`, `test_service.py`, `test_structured.py`,
`test_logging_config.py`, ...). When you add or change backend behaviour, keep
its test module in step.
