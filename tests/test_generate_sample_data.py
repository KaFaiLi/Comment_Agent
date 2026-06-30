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
