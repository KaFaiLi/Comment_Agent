# Comment Agent Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the single-file Streamlit comment-review tool into a modular `comment_agent/` backend package with a thin Streamlit frontend, swapping the internal LLM wrapper for LangChain Azure OpenAI with parse-failure handling and threaded retry.

**Architecture:** Pure-Python backend package (no Streamlit imports) imported in-process by `frontend/app.py`. Deterministic data prep (`processing/`) feeds threaded LLM review (`review/` + `llm/`), results cached in `st.session_state` and auto-saved to `Outputs/` (`persistence.py`). Data-processing behavior is preserved verbatim from the current `src/`.

**Tech Stack:** Python 3.12, uv, Streamlit, langchain-openai (`AzureChatOpenAI`), langchain-core, pydantic v2, pandas, python-docx, openpyxl, python-dotenv, pytest.

## Global Constraints

- Python `>=3.12` (existing `pyproject.toml` `requires-python`).
- Backend package `comment_agent/` MUST NOT import `streamlit`. Streamlit only in `frontend/`.
- Column-name strings (`"VAR_SVAR Comment for LLM"` etc.) defined once in `comment_agent/processing/columns.py`; never re-typed elsewhere.
- LLM structured output uses `with_structured_output(Schema, method="json_schema")` — not `function_calling`.
- Data-processing logic (5 comment types, filters, `wrap_comment` framing, `as_of_date` contract) preserved unchanged from current `src/data_processing.py`.
- Config from env / `.env`; missing required Azure values fail fast.
- Tests: pytest only, one smoke test per backend module, no fixtures/frameworks beyond pytest.
- Remove the `socgenai_llm` dependency entirely.

---

### Task 1: Project setup — dependencies and config

**Files:**
- Modify: `pyproject.toml`
- Create: `.env.example`
- Create: `comment_agent/__init__.py` (empty)
- Create: `comment_agent/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `AppConfig` dataclass with fields `azure_endpoint: str`, `azure_deployment: str`, `api_key: str`, `api_version: str`, `max_tokens: int`, `temperature: float`, `max_workers: int`, `max_retries: int`, `output_dir: str`; classmethod `AppConfig.from_env() -> AppConfig` (raises `ValueError` if any of the 4 Azure values missing).

- [ ] **Step 1: Fill `pyproject.toml` dependencies**

```toml
[project]
name = "comment-agent"
version = "0.1.0"
description = "Trading-desk risk comment review tool"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "streamlit",
    "langchain-openai",
    "langchain-core",
    "pydantic>=2",
    "pandas",
    "python-docx",
    "openpyxl",
    "python-dotenv",
]

[dependency-groups]
dev = ["pytest"]
```

- [ ] **Step 2: Create `.env.example`**

```bash
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=your-deployment-name
AZURE_OPENAI_API_KEY=your-key
OPENAI_API_VERSION=2024-10-21
COMMENT_AGENT_MAX_WORKERS=4
COMMENT_AGENT_MAX_RETRIES=3
COMMENT_AGENT_MAX_TOKENS=32768
COMMENT_AGENT_OUTPUT_DIR=Outputs
```

- [ ] **Step 3: Write the failing test**

```python
# tests/test_config.py
import pytest
from comment_agent.config import AppConfig


def test_from_env_reads_values(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://x.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "dep")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
    monkeypatch.setenv("OPENAI_API_VERSION", "2024-10-21")
    cfg = AppConfig.from_env()
    assert cfg.azure_deployment == "dep"
    assert cfg.max_workers == 4  # default


def test_from_env_missing_required_raises(monkeypatch):
    for k in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT",
              "AZURE_OPENAI_API_KEY", "OPENAI_API_VERSION"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValueError):
        AppConfig.from_env()
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: comment_agent.config`

- [ ] **Step 5: Write `comment_agent/config.py`**

```python
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class AppConfig:
    azure_endpoint: str
    azure_deployment: str
    api_key: str
    api_version: str
    max_tokens: int = 32768
    temperature: float = 0.1
    max_workers: int = 4
    max_retries: int = 3
    output_dir: str = "Outputs"

    @classmethod
    def from_env(cls) -> "AppConfig":
        required = {
            "azure_endpoint": os.environ.get("AZURE_OPENAI_ENDPOINT"),
            "azure_deployment": os.environ.get("AZURE_OPENAI_DEPLOYMENT"),
            "api_key": os.environ.get("AZURE_OPENAI_API_KEY"),
            "api_version": os.environ.get("OPENAI_API_VERSION"),
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Missing required Azure env vars: {missing}")

        return cls(
            **required,
            max_tokens=int(os.environ.get("COMMENT_AGENT_MAX_TOKENS", 32768)),
            max_workers=int(os.environ.get("COMMENT_AGENT_MAX_WORKERS", 4)),
            max_retries=int(os.environ.get("COMMENT_AGENT_MAX_RETRIES", 3)),
            output_dir=os.environ.get("COMMENT_AGENT_OUTPUT_DIR", "Outputs"),
        )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .env.example comment_agent/__init__.py comment_agent/config.py tests/test_config.py
git commit -m "feat: add AppConfig and fill dependencies"
```

---

### Task 2: Column-name contract

**Files:**
- Create: `comment_agent/processing/__init__.py` (empty)
- Create: `comment_agent/processing/columns.py`
- Test: `tests/test_columns.py`

**Interfaces:**
- Produces: `COMMENT_COLUMNS: dict[str, str]` mapping UI comment-type label → DataFrame column name. `COMMENT_TYPE_OPTIONS: list[str]` (the dict keys). Individual constants `VAR_SVAR_COL`, `STRESS_TEST_COL`, `RISK_METRICS_COL`, `IA_COL`, `PNL_COL`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_columns.py
from comment_agent.processing.columns import COMMENT_COLUMNS, COMMENT_TYPE_OPTIONS


def test_column_mapping_complete():
    assert COMMENT_COLUMNS["VAR_SVAR Comment"] == "VAR_SVAR Comment for LLM"
    assert set(COMMENT_TYPE_OPTIONS) == set(COMMENT_COLUMNS.keys())
    assert len(COMMENT_COLUMNS) == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_columns.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `comment_agent/processing/columns.py`**

```python
VAR_SVAR_COL = "VAR_SVAR Comment for LLM"
STRESS_TEST_COL = "Stress Test Comment for LLM"
RISK_METRICS_COL = "Risk Metrics Comment for LLM"
IA_COL = "Income Attribution Alert Comment for LLM"
PNL_COL = "PnL Comment for LLM"

COMMENT_COLUMNS = {
    "VAR_SVAR Comment": VAR_SVAR_COL,
    "Risk Metrics Comment": RISK_METRICS_COL,
    "IA Comment": IA_COL,
    "PnL Comment": PNL_COL,
    "Stress Test Comment": STRESS_TEST_COL,
}

COMMENT_TYPE_OPTIONS = list(COMMENT_COLUMNS.keys())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_columns.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add comment_agent/processing/__init__.py comment_agent/processing/columns.py tests/test_columns.py
git commit -m "feat: add single-source column-name contract"
```

---

### Task 3: Sample data generator

**Files:**
- Create: `scripts/__init__.py` (empty)
- Create: `scripts/generate_sample_data.py`
- Test: `tests/test_generate_sample_data.py`

**Interfaces:**
- Produces: `generate(output_dir: str, rows: int = 60, seed: int = 0) -> dict[str, str]` returning `{"cert": path, "ia": path, "pnl": path}`. CLI entrypoint with `--out`, `--rows`, `--seed`.
- CSV headers (exact, consumed by Task 4):
  - cert: `perimeter_name, trading_desk, indicator_name, error_message, comment, managerial_validation_comment, related_scenario, as_of_date`
  - ia: `perimeter_name, mmg_bl_comment, mmg_xbc_comment, managerial_validation_comment, as_of_date`
  - pnl: `Trading Desk, Comments, Date`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_generate_sample_data.py
import pandas as pd
from scripts.generate_sample_data import generate


def test_generate_writes_three_csvs(tmp_path):
    paths = generate(str(tmp_path), rows=20, seed=1)
    cert = pd.read_csv(paths["cert"])
    ia = pd.read_csv(paths["ia"])
    pnl = pd.read_csv(paths["pnl"])

    assert {"perimeter_name", "trading_desk", "indicator_name", "comment",
            "as_of_date"}.issubset(cert.columns)
    assert "VAR" in set(cert["indicator_name"])
    assert {"perimeter_name", "mmg_bl_comment", "as_of_date"}.issubset(ia.columns)
    assert {"Trading Desk", "Comments", "Date"}.issubset(pnl.columns)
    assert len(cert) > 0


def test_generate_is_deterministic(tmp_path):
    p1 = generate(str(tmp_path / "a"), rows=20, seed=42)
    p2 = generate(str(tmp_path / "b"), rows=20, seed=42)
    assert pd.read_csv(p1["cert"]).equals(pd.read_csv(p2["cert"]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_generate_sample_data.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `scripts/generate_sample_data.py`**

```python
import argparse
import os
import random
from datetime import date, timedelta

import pandas as pd

DESKS = ["EQD", "FIC"]
INDICATORS = ["VAR", "SVAR", "STRESS TEST", "INTEREST RATE", "FX DELTA"]
PHRASES = [
    "Limit breach driven by increased volatility on {d} book.",
    "PnL spike linked to client hedging activity.",
    "Booking system delay caused late capture.",
    "Stress scenario triggered on rates curve.",
    "No material change, within tolerance.",
    "",  # blank comment on purpose
]


def _dates(n, rng):
    start = date(2024, 1, 1)
    return [(start + timedelta(days=rng.randint(0, 180))).isoformat() for _ in range(n)]


def generate(output_dir: str, rows: int = 60, seed: int = 0) -> dict:
    rng = random.Random(seed)
    os.makedirs(output_dir, exist_ok=True)

    cert = pd.DataFrame({
        "perimeter_name": [rng.choice(DESKS) for _ in range(rows)],
        "trading_desk": [rng.choice(DESKS) for _ in range(rows)],
        "indicator_name": [rng.choice(INDICATORS) for _ in range(rows)],
        "error_message": [rng.choice(["", "threshold exceeded", "missing data"]) for _ in range(rows)],
        "comment": [rng.choice(PHRASES).format(d=rng.choice(DESKS)) for _ in range(rows)],
        "managerial_validation_comment": [rng.choice(["validated", "", "pending"]) for _ in range(rows)],
        "related_scenario": [rng.choice(["", "1987 crash", "rates +200bp"]) for _ in range(rows)],
        "as_of_date": _dates(rows, rng),
    })

    ia = pd.DataFrame({
        "perimeter_name": [rng.choice(DESKS) for _ in range(rows)],
        "mmg_bl_comment": [rng.choice(PHRASES).format(d=rng.choice(DESKS)) for _ in range(rows)],
        "mmg_xbc_comment": [rng.choice(PHRASES).format(d=rng.choice(DESKS)) for _ in range(rows)],
        "managerial_validation_comment": [rng.choice(["validated", ""]) for _ in range(rows)],
        "as_of_date": _dates(rows, rng),
    })

    pnl = pd.DataFrame({
        "Trading Desk": [rng.choice(DESKS) for _ in range(rows)],
        "Comments": [rng.choice(PHRASES).format(d=rng.choice(DESKS)) for _ in range(rows)],
        "Date": _dates(rows, rng),
    })

    paths = {
        "cert": os.path.join(output_dir, "sample_certification_alert.csv"),
        "ia": os.path.join(output_dir, "sample_income_attribution_alert.csv"),
        "pnl": os.path.join(output_dir, "sample_pnl_comment.csv"),
    }
    cert.to_csv(paths["cert"], index=False)
    ia.to_csv(paths["ia"], index=False)
    pnl.to_csv(paths["pnl"], index=False)
    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate sample CSVs for the comment agent.")
    parser.add_argument("--out", default="sample_data")
    parser.add_argument("--rows", type=int, default=60)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    out = generate(args.out, rows=args.rows, seed=args.seed)
    print(f"Wrote: {out}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_generate_sample_data.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/__init__.py scripts/generate_sample_data.py tests/test_generate_sample_data.py
git commit -m "feat: add sample data generator"
```

---

### Task 4: AlertProcessor (data processing)

**Files:**
- Create: `comment_agent/processing/alerts.py`
- Test: `tests/test_alerts.py`

**Interfaces:**
- Consumes: `scripts.generate_sample_data.generate` (test only), column constants from `columns.py`.
- Produces: `AlertProcessor(cert_path, ia_path, pnl_path, output_dir="Outputs")` with methods `merge_comments(desks) -> DataFrame` and static `create_final_comment(merged_df) -> DataFrame` (adds `"All Comment for LLM"` column). Behavior identical to current `src/data_processing.py`.

- [ ] **Step 1: Write `comment_agent/processing/alerts.py`**

Copy the full body of the existing `src/data_processing.py` verbatim (the `AlertProcessor` class with `_filter_by_desks`, `wrap_comment`, `_prepare_as_of_date`, `_concatenate_fields`, `_group_comments_by_date`, `process_var_svar`, `process_stress_test`, `process_risk_comments`, `process_ia_alerts`, `process_pnl_comments`, `merge_comments`, `create_final_comment`). Then make these two changes:

1. At the top, after `import` lines, add:
```python
from comment_agent.processing.columns import (
    VAR_SVAR_COL, STRESS_TEST_COL, RISK_METRICS_COL, IA_COL, PNL_COL,
)
```
2. Replace the five hard-coded `"... Comment for LLM"` column-name string literals inside the `process_*` methods with the imported constants (`VAR_SVAR_COL`, `STRESS_TEST_COL`, `RISK_METRICS_COL`, `IA_COL`, `PNL_COL`). Leave all logic, filters, and `wrap_comment` framing untouched.
3. In `__init__`, after reading the three CSVs, validate required columns and fail fast:
```python
self._require_columns(self.cert_df, ["perimeter_name", "trading_desk",
    "indicator_name", "comment", "as_of_date"], "certification alert")
self._require_columns(self.ia_alert_df, ["perimeter_name", "as_of_date"],
    "income attribution alert")
self._require_columns(self.pnl_comment_df, ["Trading Desk", "Comments", "Date"],
    "PnL comment")
```
and add the helper:
```python
@staticmethod
def _require_columns(df, cols, name):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{name} CSV missing columns: {missing}")
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_alerts.py
import pandas as pd
import pytest
from scripts.generate_sample_data import generate
from comment_agent.processing.alerts import AlertProcessor
from comment_agent.processing.columns import COMMENT_COLUMNS


def test_merge_and_final_comment(tmp_path):
    paths = generate(str(tmp_path), rows=80, seed=3)
    proc = AlertProcessor(paths["cert"], paths["ia"], paths["pnl"],
                          output_dir=str(tmp_path / "out"))
    merged = proc.merge_comments(["EQD", "FIC"])
    assert "as_of_date" in merged.columns
    final = AlertProcessor.create_final_comment(merged)
    assert "All Comment for LLM" in final.columns
    # at least one of the per-type columns survives the merge
    assert any(c in final.columns for c in COMMENT_COLUMNS.values())


def test_missing_columns_fail_fast(tmp_path):
    bad = tmp_path / "bad.csv"
    pd.DataFrame({"wrong": [1]}).to_csv(bad, index=False)
    with pytest.raises(ValueError):
        AlertProcessor(str(bad), str(bad), str(bad), output_dir=str(tmp_path))
```

- [ ] **Step 3: Run test to verify it fails then passes**

Run: `uv run pytest tests/test_alerts.py -v`
Expected: first run before writing the module FAILs with `ModuleNotFoundError`; after Step 1 module exists → PASS (2 passed).

- [ ] **Step 4: Commit**

```bash
git add comment_agent/processing/alerts.py tests/test_alerts.py
git commit -m "feat: port AlertProcessor with column constants and column validation"
```

---

### Task 5: LLM client

**Files:**
- Create: `comment_agent/llm/__init__.py` (empty)
- Create: `comment_agent/llm/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: `AppConfig` from Task 1.
- Produces: `build_chat_model(cfg: AppConfig) -> AzureChatOpenAI`; `structured(model, schema)` returning `model.with_structured_output(schema, method="json_schema")`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client.py
from comment_agent.config import AppConfig
from comment_agent.llm import client


def _cfg():
    return AppConfig(azure_endpoint="https://x.openai.azure.com/",
                     azure_deployment="dep", api_key="k", api_version="2024-10-21")


def test_build_chat_model_uses_config():
    model = client.build_chat_model(_cfg())
    assert model.deployment_name == "dep"
    assert model.temperature == 0.1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `comment_agent/llm/client.py`**

```python
from langchain_openai import AzureChatOpenAI

from comment_agent.config import AppConfig


def build_chat_model(cfg: AppConfig) -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_endpoint=cfg.azure_endpoint,
        azure_deployment=cfg.azure_deployment,
        api_key=cfg.api_key,
        api_version=cfg.api_version,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )


def structured(model, schema):
    """Bind a Pydantic schema using the modern strict JSON-schema method."""
    return model.with_structured_output(schema, method="json_schema")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_client.py -v`
Expected: PASS (note: requires `langchain-openai` installed; `AzureChatOpenAI` does not call the API at construction)

- [ ] **Step 5: Commit**

```bash
git add comment_agent/llm/__init__.py comment_agent/llm/client.py tests/test_client.py
git commit -m "feat: add AzureChatOpenAI client builder"
```

---

### Task 6: Structured invocation with retry + fix-up

**Files:**
- Create: `comment_agent/llm/structured.py`
- Test: `tests/test_structured.py`

**Interfaces:**
- Consumes: nothing from other tasks (model objects passed in).
- Produces:
```python
def invoke_structured(structured_llm, base_llm, prompt_value, schema, *,
                      max_retries=3, delay_seconds=0.0, label="LLM call",
                      status_callback=None, fixup=True): -> BaseModel | None
```
Returns a validated `schema` instance, or `None` after retries + fix-up all fail.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_structured.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_structured.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `comment_agent/llm/structured.py`**

```python
import json
import time
from typing import Optional


def _emit(status_callback, msg):
    print(msg)
    if status_callback:
        status_callback(msg)


def _try_fixup(base_llm, raw_text, schema, label, status_callback):
    _emit(status_callback, f"[FIXUP] {label} | attempting JSON reformat")
    instruction = (
        "The following text was supposed to be JSON matching this schema:\n"
        f"{json.dumps(schema.model_json_schema())}\n\n"
        "Return ONLY valid JSON matching the schema, no prose:\n"
        f"{raw_text}"
    )
    try:
        result = base_llm.invoke(instruction)
        text = getattr(result, "content", result)
        data = json.loads(text)
        return schema.model_validate(data)
    except Exception as exc:
        _emit(status_callback, f"[FIXUP FAILED] {label} | {exc}")
        return None


def invoke_structured(structured_llm, base_llm, prompt_value, schema, *,
                      max_retries: int = 3, delay_seconds: float = 0.0,
                      label: str = "LLM call", status_callback=None,
                      fixup: bool = True) -> Optional[object]:
    last_raw = None
    for attempt in range(1, max_retries + 1):
        _emit(status_callback, f"[REQUEST] {label} | attempt {attempt}/{max_retries}")
        try:
            result = structured_llm.invoke(prompt_value)
            _emit(status_callback, f"[SUCCESS] {label}")
            return result
        except Exception as exc:
            last_raw = str(exc)
            _emit(status_callback, f"[FAILED] {label} | attempt {attempt} | {exc}")
            if attempt < max_retries and delay_seconds:
                time.sleep(delay_seconds)

    if fixup:
        fixed = _try_fixup(base_llm, last_raw, schema, label, status_callback)
        if fixed is not None:
            _emit(status_callback, f"[FIXUP SUCCESS] {label}")
            return fixed

    _emit(status_callback, f"[SKIPPED] {label} failed after retries + fixup")
    return None
```

> Note: the fix-up parses the LLM's exception text as a fallback signal. In production the structured call's failure carries the raw model output; passing `last_raw` keeps the fix-up self-contained for the smoke test. `ponytail:` keep until a real parse-failure payload is available, then feed the actual raw completion instead of the exception string.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_structured.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add comment_agent/llm/structured.py tests/test_structured.py
git commit -m "feat: structured invocation with retry and fix-up pass"
```

---

### Task 7: Threaded concurrency helper

**Files:**
- Create: `comment_agent/llm/concurrency.py`
- Test: `tests/test_concurrency.py`

**Interfaces:**
- Produces: `run_parallel(items, fn, *, max_workers=4, status_callback=None) -> list`. Applies `fn(item)` over `items` in a thread pool, preserving input order. An item whose `fn` raises or returns `None` yields `None` in the output list.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_concurrency.py
from comment_agent.llm.concurrency import run_parallel


def test_preserves_order_and_skips_failures():
    def fn(x):
        if x == 3:
            raise RuntimeError("boom")
        if x == 4:
            return None
        return x * 10

    out = run_parallel([1, 2, 3, 4, 5], fn, max_workers=3)
    assert out == [10, 20, None, None, 50]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_concurrency.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `comment_agent/llm/concurrency.py`**

```python
from concurrent.futures import ThreadPoolExecutor


def run_parallel(items, fn, *, max_workers: int = 4, status_callback=None) -> list:
    # ponytail: thread pool, fine for I/O-bound LLM calls; switch to async if call volume explodes
    items = list(items)
    results = [None] * len(items)

    def safe(i, item):
        try:
            return i, fn(item)
        except Exception as exc:
            if status_callback:
                status_callback(f"[TASK FAILED] index {i} | {exc}")
            return i, None

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for i, value in pool.map(lambda p: safe(*p), enumerate(items)):
            results[i] = value
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_concurrency.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add comment_agent/llm/concurrency.py tests/test_concurrency.py
git commit -m "feat: threaded run_parallel helper"
```

---

### Task 8: Review schemas and prompts

**Files:**
- Create: `comment_agent/review/__init__.py` (empty)
- Create: `comment_agent/review/schemas.py`
- Create: `comment_agent/review/prompts.py`
- Test: `tests/test_prompts.py`

**Interfaces:**
- Produces: `schemas.Recurrent`, `schemas.KeyVariation` (pydantic models); `prompts.recurrentPrompt`, `prompts.KeyVariationPrompt` (`ChatPromptTemplate`), `prompts.xxm_prompt` (str).

- [ ] **Step 1: Create the two files by splitting existing `src/prompt.py`**

`comment_agent/review/schemas.py` — copy verbatim the `Recurrent` and `KeyVariation` Pydantic classes (and their imports: `from pydantic import BaseModel, Field` and `from typing import List`) from the current `src/prompt.py`. No changes.

`comment_agent/review/prompts.py` — copy verbatim `recurrentPrompt`, `KeyVariationPrompt`, and `xxm_prompt` from `src/prompt.py`, plus `from langchain_core.prompts import ChatPromptTemplate`. No changes.

- [ ] **Step 2: Write the smoke test**

```python
# tests/test_prompts.py
from comment_agent.review.schemas import Recurrent, KeyVariation
from comment_agent.review.prompts import recurrentPrompt, KeyVariationPrompt, xxm_prompt


def test_schemas_have_expected_fields():
    assert "RecurrentTopic" in Recurrent.model_fields
    assert "KeyMetricTopic" in KeyVariation.model_fields


def test_prompts_render():
    msg = KeyVariationPrompt.invoke({"query": "some comment"})
    assert msg is not None
    assert isinstance(xxm_prompt, str) and len(xxm_prompt) > 0
```

- [ ] **Step 3: Run test to verify it passes**

Run: `uv run pytest tests/test_prompts.py -v`
Expected: PASS (after files created)

- [ ] **Step 4: Commit**

```bash
git add comment_agent/review/__init__.py comment_agent/review/schemas.py comment_agent/review/prompts.py tests/test_prompts.py
git commit -m "feat: split review schemas and prompts"
```

---

### Task 9: Review formatters

**Files:**
- Create: `comment_agent/review/formatters.py`
- Test: `tests/test_formatters.py`

**Interfaces:**
- Consumes: `schemas.KeyVariation`, `schemas.Recurrent` instances.
- Produces: `format_key_metrics(data) -> str`, `format_recurrent_topics(data) -> str`.

- [ ] **Step 1: Create `comment_agent/review/formatters.py`**

Copy the full body of the existing `src/review_formatters.py` verbatim (both `format_key_metrics` and `format_recurrent_topics`). No changes.

- [ ] **Step 2: Write the failing test (ragged lists)**

```python
# tests/test_formatters.py
from comment_agent.review.formatters import format_key_metrics, format_recurrent_topics
from comment_agent.review.schemas import KeyVariation, Recurrent


def test_format_key_metrics_handles_ragged():
    data = KeyVariation(
        KeyMetricTopic=["A", "B"],
        KeyMetricVariation=[["v1"]],          # shorter than topics on purpose
        Reference=[["2024-01-01"]],
        Summary="s",
    )
    out = format_key_metrics(data)
    assert "Key Metric Topic 1: A" in out
    assert "Key Metric Topic 2: B" in out  # must not crash on missing index


def test_format_recurrent_topics_handles_empty_tech():
    data = Recurrent(
        RecurrentTopic=["T"], RecurrentTopicExplain=[["e"]],
        pattern=[["p"]], Reference=[["r"]], Tech_issue=[], Summary="s",
    )
    out = format_recurrent_topics(data)
    assert "No specific technical issues reported." in out
```

- [ ] **Step 2b: Run to verify it fails**

Run: `uv run pytest tests/test_formatters.py -v`
Expected: FAIL — `ModuleNotFoundError` (before Step 1 done) — if Step 1 already done, run shows PASS.

- [ ] **Step 3: Run test to verify it passes**

Run: `uv run pytest tests/test_formatters.py -v`
Expected: PASS (2 passed)

- [ ] **Step 4: Commit**

```bash
git add comment_agent/review/formatters.py tests/test_formatters.py
git commit -m "feat: port review formatters"
```

---

### Task 10: Document exporter

**Files:**
- Create: `comment_agent/export/__init__.py` (empty)
- Create: `comment_agent/export/documents.py`
- Test: `tests/test_documents.py`

**Interfaces:**
- Produces: `DocumentExporter` with `convert_markdown_to_word`, `get_word_doc_buffer_from_markdown(md) -> BytesIO`, `generate_executive_summary_word(summary, comment_type) -> Document`, `get_word_doc_buffer_from_executive_summary(summary, comment_type) -> BytesIO`, `save_executive_summary(summary, comment_type, output_dir) -> str`, `convert_and_save_markdown(md, comment_type, output_dir) -> str`.

- [ ] **Step 1: Create `comment_agent/export/documents.py`**

Copy the full body of the existing `src/formatting.py` verbatim (the entire `DocumentExporter` class and its imports `import re`, `from io import BytesIO`, `from docx import Document`). No changes.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_documents.py
from comment_agent.export.documents import DocumentExporter


def test_markdown_buffer_nonempty():
    exporter = DocumentExporter()
    buf = exporter.get_word_doc_buffer_from_markdown("# Title\n- bullet\n**bold** text")
    data = buf.getvalue()
    assert data[:2] == b"PK"  # docx is a zip
    assert len(data) > 0


def test_save_executive_summary_writes_file(tmp_path):
    exporter = DocumentExporter()
    path = exporter.save_executive_summary("## Summary\ncontent", "PnL Comment",
                                           output_dir=str(tmp_path))
    assert path.endswith(".docx")
```

- [ ] **Step 3: Run test to verify it passes**

Run: `uv run pytest tests/test_documents.py -v`
Expected: PASS (2 passed)

- [ ] **Step 4: Commit**

```bash
git add comment_agent/export/__init__.py comment_agent/export/documents.py tests/test_documents.py
git commit -m "feat: port DocumentExporter"
```

---

### Task 11: Persistence

**Files:**
- Create: `comment_agent/persistence.py`
- Test: `tests/test_persistence.py`

**Interfaces:**
- Consumes: `DocumentExporter` from Task 10.
- Produces:
  - `save_intermediates(final_df, output_dir) -> str` — writes `All comments.xlsx`, returns its path.
  - `save_results(quarterly_reviews: dict, markdown_by_type: dict, summary_by_type: dict, output_dir, exporter) -> None` — writes `quarterly_reviews_summary_<type>.md`, `<type>_full_review.docx`, `executive_summary_<type>.docx` for each comment type.

`quarterly_reviews` shape: `{comment_type: {quarter: {"key_variation": str, "recurrent": str}}}`. `markdown_by_type`/`summary_by_type`: `{comment_type: str}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_persistence.py
import os
import pandas as pd
from comment_agent.persistence import save_intermediates, save_results
from comment_agent.export.documents import DocumentExporter


def test_save_intermediates(tmp_path):
    df = pd.DataFrame({"as_of_date": ["2024-01-01"], "All Comment for LLM": ["x"]})
    path = save_intermediates(df, str(tmp_path))
    assert os.path.exists(path)


def test_save_results_writes_all_files(tmp_path):
    save_results(
        quarterly_reviews={"PnL Comment": {"2024Q1": {"key_variation": "k", "recurrent": "r"}}},
        markdown_by_type={"PnL Comment": "# md content"},
        summary_by_type={"PnL Comment": "## summary"},
        output_dir=str(tmp_path),
        exporter=DocumentExporter(),
    )
    files = os.listdir(tmp_path)
    assert any(f.endswith(".md") for f in files)
    assert any("full_review.docx" in f for f in files)
    assert any("executive_summary" in f for f in files)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_persistence.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `comment_agent/persistence.py`**

```python
import os


def save_intermediates(final_df, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "All comments.xlsx")
    final_df.to_excel(path, index=False)
    return path


def save_results(quarterly_reviews: dict, markdown_by_type: dict,
                 summary_by_type: dict, output_dir: str, exporter) -> None:
    os.makedirs(output_dir, exist_ok=True)
    for comment_type, markdown in markdown_by_type.items():
        safe = comment_type.replace(" ", "_").lower()

        md_path = os.path.join(output_dir, f"quarterly_reviews_summary_{safe}.md")
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(markdown)

        exporter.convert_and_save_markdown(markdown, comment_type, output_dir=output_dir)
        summary = summary_by_type.get(comment_type, "")
        exporter.save_executive_summary(summary, comment_type, output_dir=output_dir)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_persistence.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add comment_agent/persistence.py tests/test_persistence.py
git commit -m "feat: add persistence for intermediates and results"
```

---

### Task 12: CommentReviewService

**Files:**
- Create: `comment_agent/review/service.py`
- Test: `tests/test_service.py`

**Interfaces:**
- Consumes: `client.build_chat_model`/`client.structured`, `structured.invoke_structured`, `concurrency.run_parallel`, `formatters`, `prompts`, `schemas`, `columns.COMMENT_COLUMNS`.
- Produces: `CommentReviewService(cfg, status_callback=None)` with:
  - `review(df, selected_comment_types) -> dict` shaped `{comment_type: {quarter: {"key_variation": str, "recurrent": str}}}`.
  - `generate_markdown_content(comment_type, reviews) -> str`.
  - `generate_executive_summary(reviews) -> str`.

- [ ] **Step 1: Write `comment_agent/review/service.py`**

```python
import pandas as pd

from comment_agent.config import AppConfig
from comment_agent.llm import client
from comment_agent.llm.structured import invoke_structured
from comment_agent.llm.concurrency import run_parallel
from comment_agent.review.schemas import Recurrent, KeyVariation
from comment_agent.review.prompts import recurrentPrompt, KeyVariationPrompt, xxm_prompt
from comment_agent.review.formatters import format_key_metrics, format_recurrent_topics
from comment_agent.processing.columns import COMMENT_COLUMNS


class CommentReviewService:
    def __init__(self, cfg: AppConfig, status_callback=None):
        self.cfg = cfg
        self.status_callback = status_callback
        self.model = client.build_chat_model(cfg)
        self.key_llm = client.structured(self.model, KeyVariation)
        self.recurrent_llm = client.structured(self.model, Recurrent)

    def _emit(self, msg):
        print(msg)
        if self.status_callback:
            self.status_callback(msg)

    def review(self, df, selected_comment_types) -> dict:
        by_quarter = self._gather_comments_by_type_and_quarter(df)

        tasks = []
        for quarter, types in by_quarter.items():
            for comment_type, comments in types.items():
                if comment_type in selected_comment_types and comments:
                    tasks.append((quarter, comment_type, comments))

        self._emit(f"[INFO] {len(tasks)} review task(s) across quarters/types")

        results = run_parallel(
            tasks, self._review_one,
            max_workers=self.cfg.max_workers,
            status_callback=self.status_callback,
        )

        quarterly_reviews = {ct: {} for ct in selected_comment_types}
        for (quarter, comment_type, _comments), review in zip(tasks, results):
            if review is not None:
                quarterly_reviews[comment_type][quarter] = review
        return quarterly_reviews

    def _review_one(self, task):
        quarter, comment_type, comments = task
        combined = " ".join(str(c) for c in comments)

        key_result = invoke_structured(
            self.key_llm, self.model,
            KeyVariationPrompt.invoke({"query": combined}), KeyVariation,
            max_retries=self.cfg.max_retries, delay_seconds=2,
            label=f"Key variation {quarter}-{comment_type}",
            status_callback=self.status_callback,
        )
        recurrent_result = invoke_structured(
            self.recurrent_llm, self.model,
            recurrentPrompt.invoke({"query": combined}), Recurrent,
            max_retries=self.cfg.max_retries, delay_seconds=2,
            label=f"Recurrent {quarter}-{comment_type}",
            status_callback=self.status_callback,
        )
        if key_result is None or recurrent_result is None:
            return None
        return {
            "key_variation": format_key_metrics(key_result),
            "recurrent": format_recurrent_topics(recurrent_result),
        }

    def generate_markdown_content(self, comment_type, reviews) -> str:
        out = f"# Executive Summary for {comment_type}\n\n"
        out += f"## Executive Summary:\n{self.generate_executive_summary(reviews)}\n\n"
        for quarter, review in reviews.items():
            out += f"## Quarter: {quarter}\n"
            out += f"### Key Metrics Variation\n{review['key_variation']}\n"
            out += f"### Recurrent Topics\n{review['recurrent']}\n"
        return out

    def generate_executive_summary(self, reviews) -> str:
        if not reviews:
            return "No quarterly reviews found."
        complete = "\n".join(
            f"Quarter: {q}\nKey Variation: {r['key_variation']}\nRecurrent: {r['recurrent']}\n"
            for q, r in reviews.items()
        )
        try:
            result = self.model.invoke(f"{xxm_prompt} {complete}")
            return getattr(result, "content", str(result))
        except Exception as exc:
            self._emit(f"[FAILED] executive summary | {exc}")
            return "Executive summary generation failed."

    @staticmethod
    def _gather_comments_by_type_and_quarter(df) -> dict:
        df = df.copy()
        df["as_of_date"] = pd.to_datetime(df["as_of_date"])
        df["quarter"] = df["as_of_date"].dt.to_period("Q")

        by_quarter = {}
        for quarter in df["quarter"].unique():
            qdf = df[df["quarter"] == quarter]
            by_quarter[quarter] = {}
            for comment_type, column in COMMENT_COLUMNS.items():
                if column not in qdf.columns:
                    by_quarter[quarter][comment_type] = []
                else:
                    by_quarter[quarter][comment_type] = (
                        qdf[column].dropna().astype(str).tolist()
                    )
        return by_quarter
```

- [ ] **Step 2: Write the failing test (mocked LLM, no network)**

```python
# tests/test_service.py
import pandas as pd
from comment_agent.config import AppConfig
from comment_agent.review.service import CommentReviewService
from comment_agent.review.schemas import KeyVariation, Recurrent
from comment_agent.processing.columns import VAR_SVAR_COL


def _cfg():
    return AppConfig(azure_endpoint="https://x.openai.azure.com/",
                     azure_deployment="d", api_key="k", api_version="2024-10-21",
                     max_workers=2, max_retries=1)


def _patch(svc):
    svc.key_llm = type("K", (), {"invoke": lambda self, p: KeyVariation(
        KeyMetricTopic=["t"], KeyMetricVariation=[["v"]], Reference=[["2024-01-01"]],
        Summary="s")})()
    svc.recurrent_llm = type("R", (), {"invoke": lambda self, p: Recurrent(
        RecurrentTopic=["t"], RecurrentTopicExplain=[["e"]], pattern=[["p"]],
        Reference=[["r"]], Tech_issue=[], Summary="s")})()
    svc.model = type("M", (), {"invoke": lambda self, p: type("X", (), {"content": "summary"})()})()


def test_review_produces_structure(monkeypatch):
    svc = CommentReviewService.__new__(CommentReviewService)
    svc.cfg = _cfg()
    svc.status_callback = None
    _patch(svc)

    df = pd.DataFrame({
        "as_of_date": ["2024-01-15", "2024-02-15"],
        VAR_SVAR_COL: ["comment a", "comment b"],
    })
    result = svc.review(df, ["VAR_SVAR Comment"])
    assert "VAR_SVAR Comment" in result
    assert len(result["VAR_SVAR Comment"]) >= 1
    review = next(iter(result["VAR_SVAR Comment"].values()))
    assert "key_variation" in review and "recurrent" in review
```

> The test constructs the service with `__new__` to bypass real Azure client creation, then patches in fake structured models. This keeps the smoke test offline.

- [ ] **Step 3: Run test to verify it fails then passes**

Run: `uv run pytest tests/test_service.py -v`
Expected: FAIL before Step 1 (`ModuleNotFoundError`); PASS after.

- [ ] **Step 4: Commit**

```bash
git add comment_agent/review/service.py tests/test_service.py
git commit -m "feat: threaded CommentReviewService"
```

---

### Task 13: Streamlit frontend and cleanup

**Files:**
- Create: `frontend/__init__.py` (empty)
- Create: `frontend/app.py`
- Delete: `main.py`, `src/` (entire directory)
- Modify: `README.md` (add run instructions)

**Interfaces:**
- Consumes: `AppConfig`, `AlertProcessor`, `CommentReviewService`, `DocumentExporter`, `persistence`, `columns.COMMENT_TYPE_OPTIONS`.

- [ ] **Step 1: Write `frontend/app.py`**

```python
import os
import streamlit as st

from comment_agent.config import AppConfig
from comment_agent.processing.alerts import AlertProcessor
from comment_agent.processing.columns import COMMENT_TYPE_OPTIONS
from comment_agent.review.service import CommentReviewService
from comment_agent.export.documents import DocumentExporter
from comment_agent import persistence


def init_session_state():
    defaults = {
        "quarterly_reviews": {},
        "markdown_contents": {},
        "executive_summaries": {},
        "selected_types": COMMENT_TYPE_OPTIONS,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def render_sidebar():
    with st.sidebar:
        st.markdown("Upload the certification, income-attribution and PnL CSV files.")
        cert = st.file_uploader("Certification Alert CSV", type="csv", key="cert_file")
        ia = st.file_uploader("Income Attribution Alert CSV", type="csv", key="ia_file")
        pnl = st.file_uploader("PnL Comment CSV", type="csv", key="pnl_file")
        raw = st.text_input("Desks (comma-separated)", placeholder="EQD, FIC")
        desks = [d.strip() for d in raw.split(",") if d.strip()]
        selected = st.multiselect("Comment types", COMMENT_TYPE_OPTIONS,
                                  default=COMMENT_TYPE_OPTIONS)
        generate = st.button("Generate Review")
    return cert, ia, pnl, desks, selected, generate


def run_generation(cfg, cert, ia, pnl, desks, selected, status):
    proc = AlertProcessor(cert, ia, pnl, output_dir=cfg.output_dir)
    merged = proc.merge_comments(desks)
    final_df = AlertProcessor.create_final_comment(merged)
    persistence.save_intermediates(final_df, cfg.output_dir)

    service = CommentReviewService(cfg, status_callback=status)
    reviews = service.review(final_df, selected)

    markdown_by_type, summary_by_type = {}, {}
    for comment_type, qreviews in reviews.items():
        markdown_by_type[comment_type] = service.generate_markdown_content(comment_type, qreviews)
        summary_by_type[comment_type] = service.generate_executive_summary(qreviews)

    persistence.save_results(reviews, markdown_by_type, summary_by_type,
                             cfg.output_dir, DocumentExporter())

    st.session_state.quarterly_reviews = reviews
    st.session_state.markdown_contents = markdown_by_type
    st.session_state.executive_summaries = summary_by_type
    st.session_state.selected_types = selected


def render_results():
    reviews = st.session_state.quarterly_reviews
    if not reviews:
        return
    exporter = DocumentExporter()
    selected = st.session_state.selected_types
    tabs = st.tabs(selected)
    for i, comment_type in enumerate(selected):
        with tabs[i]:
            content = st.session_state.markdown_contents.get(comment_type)
            summary = st.session_state.executive_summaries.get(comment_type)
            if not content:
                st.info(f"No review generated for {comment_type}.")
                continue
            st.markdown(content)
            safe = comment_type.replace(" ", "_").lower()
            st.download_button(
                "Download Full Review", exporter.get_word_doc_buffer_from_markdown(content),
                file_name=f"{safe}_full_review.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            st.download_button(
                "Download Executive Summary",
                exporter.get_word_doc_buffer_from_executive_summary(summary, comment_type),
                file_name=f"{safe}_executive_summary.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            st.warning("AI-generated; apply professional judgement.", icon="ℹ️")


def main():
    st.title("Comment Review Tool")
    init_session_state()
    cert, ia, pnl, desks, selected, generate = render_sidebar()

    if generate:
        if not (cert and ia and pnl):
            st.error("Upload all three CSV files.")
        elif not desks:
            st.error("Enter at least one desk.")
        else:
            cfg = AppConfig.from_env()
            os.makedirs(cfg.output_dir, exist_ok=True)
            placeholder = st.empty()
            with st.spinner("Generating review..."):
                run_generation(cfg, cert, ia, pnl, desks, selected,
                               status=lambda m: placeholder.info(m))

    # Always render from session_state — survives download-triggered reruns.
    render_results()


if __name__ == "__main__":
    main()
```

Key behavior (req #6): `run_generation` runs **only** under `if generate:`. Download buttons trigger a rerun where `generate` is `False`, so `render_results()` re-renders from `st.session_state` without recomputing or clearing. Auto-save to `cfg.output_dir` happens inside `run_generation` before results render.

- [ ] **Step 2: Delete old code**

```bash
git rm main.py
git rm -r src
```

- [ ] **Step 3: Update `README.md`**

```markdown
# Comment Review Tool

Streamlit tool that turns trading-desk risk-comment CSVs into per-quarter AI reviews and executive summaries (downloadable as Word docs).

## Setup

    uv sync
    cp .env.example .env   # fill in Azure OpenAI values

## Run

    uv run streamlit run frontend/app.py

## Sample data

    uv run python -m scripts.generate_sample_data --out sample_data

## Tests

    uv run pytest
```

- [ ] **Step 4: Verify the full suite passes and the app imports**

Run: `uv run pytest -v`
Expected: all tests PASS.
Run: `uv run python -c "import frontend.app"`
Expected: no error (imports resolve; no Streamlit runtime needed for import).

- [ ] **Step 5: Commit**

```bash
git add frontend/__init__.py frontend/app.py README.md
git commit -m "feat: Streamlit frontend; remove old main.py and src/"
```

---

## Self-Review

**Spec coverage:**
- Modularize (req 1) → Tasks 1–13 split package by responsibility. ✓
- Backend/frontend, Streamlit frontend (req 2) → backend `comment_agent/`, `frontend/app.py`, Task 13. ✓
- LangChain Azure OpenAI (req 3) → Task 5. ✓
- Latest method + parse handling (req 4) → `json_schema` in Task 5, retry+fix-up in Task 6. ✓
- Multithreading with retry (req 5) → Task 7 pool + Task 6 retry, wired in Task 12. ✓
- Screen survives download + auto-save (req 6) → Task 13 session_state + Task 11 persistence. ✓
- Sample data script (req 7) → Task 3. ✓

**Placeholder scan:** No TBD/TODO. Verbatim-copy steps (Tasks 4, 8, 9, 10) reference an existing in-repo file with the exact edits listed — concrete, not deferred.

**Type consistency:** `quarterly_reviews` shape `{type: {quarter: {"key_variation", "recurrent"}}}` consistent across Tasks 11, 12, 13. `invoke_structured`, `run_parallel`, `structured`, `build_chat_model`, `save_intermediates`, `save_results` signatures match between producer and consumer tasks. `COMMENT_COLUMNS`/`COMMENT_TYPE_OPTIONS` used consistently.
