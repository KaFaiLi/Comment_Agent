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
