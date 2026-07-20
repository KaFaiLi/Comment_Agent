import os
import pandas as pd
from comment_agent.persistence import save_intermediates, save_results
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
