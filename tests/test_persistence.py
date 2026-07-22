import os
import json
import re
import pandas as pd
from comment_agent.persistence import (
    save_intermediates,
    save_results,
    save_run_manifest,
)
from comment_agent.export.documents import DocumentExporter
from comment_agent.processing.columns import EVIDENCE_COLUMNS


def test_save_intermediates(tmp_path):
    def evidence(date, source_row_id, review_type, text):
        return {
            "as_of_date": date,
            "desk": "EQD",
            "perimeter_name": "EQD",
            "source": "certification",
            "source_row_id": source_row_id,
            "review_type": review_type,
            "metric_name": "VAR",
            "evidence_text": text,
        }

    df = pd.DataFrame([
        evidence("2024-01-01", "cert:2", "VAR_SVAR Comment", "var comment"),
        evidence("2024-01-01", "cert:3", "Stress Test Comment", "stress comment"),
        evidence("2024-01-02", "pnl:2", "PnL Comment", "pnl comment"),
    ], columns=EVIDENCE_COLUMNS)
    path = save_intermediates(df, str(tmp_path))
    assert os.path.exists(path)

    workbook = pd.ExcelFile(path)
    assert workbook.sheet_names == ["Daily comments", "Review evidence"]
    daily = pd.read_excel(path, sheet_name="Daily comments")
    detailed = pd.read_excel(path, sheet_name="Review evidence")
    assert len(daily) == 2
    assert len(detailed) == 3
    first_day = daily.loc[daily["as_of_date"] == "2024-01-01"].iloc[0]
    assert first_day["VAR_SVAR Comment"] == "var comment"
    assert first_day["Stress Test Comment"] == "stress comment"
    assert "var comment" in first_day["All Comments"]
    assert "stress comment" in first_day["All Comments"]


def test_save_results_writes_all_files(tmp_path):
    paths = save_results(
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
    assert len(paths) == 3


def test_save_run_manifest_writes_timestamped_json(tmp_path):
    evidence = pd.DataFrame([
        {
            "as_of_date": "2024-01-01",
            "desk": "EQD",
            "perimeter_name": "EQD",
            "source": "certification",
            "source_row_id": "cert:2",
            "review_type": "VAR_SVAR Comment",
            "metric_name": "VAR",
            "evidence_text": "var comment",
        }
    ], columns=EVIDENCE_COLUMNS)
    artifact = tmp_path / "All comments.xlsx"
    artifact.touch()

    path = save_run_manifest(
        output_dir=str(tmp_path),
        desks=["EQD"],
        selected_comment_types=["VAR_SVAR Comment"],
        evidence=evidence,
        quarterly_reviews={"VAR_SVAR Comment": {"2024Q1": {}}},
        token_usage={"input": 10, "cached": 2, "output": 3},
        artifacts=[str(artifact)],
        input_files={"certification_alerts": "cert.csv"},
        deployment="audit-model",
        api_version="2024-10-21",
    )

    assert re.fullmatch(r"run_manifest_\d{8}T\d{12}Z\.json", os.path.basename(path))
    with open(path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    assert manifest["generated_at"].endswith("Z")
    assert manifest["scope"]["desks"] == ["EQD"]
    assert manifest["review"]["evidence_date_range"] == {
        "start": "2024-01-01", "end": "2024-01-01"
    }
    assert manifest["artifacts"] == ["All comments.xlsx"]
    assert manifest["token_usage"] == {"input": 10, "cached": 2, "output": 3}
