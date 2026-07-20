# tests/test_alerts.py
import pandas as pd
import pytest
from comment_agent.processing.alerts import AlertProcessor
from comment_agent.processing.columns import EVIDENCE_COLUMNS


def test_missing_columns_fail_fast(tmp_path):
    bad = tmp_path / "bad.csv"
    pd.DataFrame({"wrong": [1]}).to_csv(bad, index=False)
    with pytest.raises(ValueError):
        AlertProcessor(str(bad), str(bad), str(bad), output_dir=str(tmp_path))


def test_wrap_comment_uses_entity_framing():
    out = AlertProcessor.wrap_comment("Tag", "2024-01-01", "body")
    assert out == "<Tag on 2024-01-01>\nbody\n</Tag on 2024-01-01>"


def test_build_evidence_keeps_each_source_record_once(tmp_path):
    cert = pd.DataFrame([
        {
            "perimeter_name": "EQD", "trading_desk": "EQD", "indicator_name": "VAR",
            "error_message": "limit", "comment": "var comment",
            "managerial_validation_comment": "validated", "related_scenario": "base",
            "as_of_date": "2024-01-15",
        },
        {
            "perimeter_name": "EQD", "trading_desk": "EQD", "indicator_name": "SVAR",
            "error_message": "limit", "comment": "svar comment",
            "managerial_validation_comment": "validated", "related_scenario": "base",
            "as_of_date": "2024-01-15",
        },
        {
            "perimeter_name": "EQD", "trading_desk": "EQD", "indicator_name": "STRESS TEST",
            "error_message": "scenario", "comment": "stress comment",
            "managerial_validation_comment": "pending", "related_scenario": "1987 crash",
            "as_of_date": "2024-01-15",
        },
    ])
    ia = pd.DataFrame([
        {
            "perimeter_name": "EQD", "mmg_bl_comment": "ia 1", "mmg_xbc_comment": "",
            "managerial_validation_comment": "validated", "as_of_date": "2024-01-15",
        },
        {
            "perimeter_name": "EQD", "mmg_bl_comment": "ia 2", "mmg_xbc_comment": "",
            "managerial_validation_comment": "validated", "as_of_date": "2024-01-15",
        },
    ])
    pnl = pd.DataFrame([
        {"Trading Desk": "EQD", "Comments": "pnl 1", "Date": "2024-01-15"},
        {"Trading Desk": "EQD", "Comments": "pnl 2", "Date": "2024-01-15"},
    ])
    cert_path, ia_path, pnl_path = (tmp_path / "cert.csv", tmp_path / "ia.csv", tmp_path / "pnl.csv")
    cert.to_csv(cert_path, index=False)
    ia.to_csv(ia_path, index=False)
    pnl.to_csv(pnl_path, index=False)

    evidence = AlertProcessor(
        cert_path, ia_path, pnl_path, output_dir=str(tmp_path / "out")
    ).build_evidence(["EQD"])

    assert list(evidence.columns) == EVIDENCE_COLUMNS
    assert len(evidence) == 7
    assert evidence["source_row_id"].is_unique
    var_svar = evidence[evidence["review_type"] == "VAR_SVAR Comment"]
    assert len(var_svar) == 2
    assert set(var_svar["metric_name"]) == {"VAR", "SVAR"}
    assert all("Desk: EQD" in text for text in var_svar["evidence_text"])
