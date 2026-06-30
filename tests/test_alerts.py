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
