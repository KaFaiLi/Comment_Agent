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
