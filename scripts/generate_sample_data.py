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

# Long, chaotic fragments to stress the LLM JSON output + citation grounding.
# Deliberately contain quotes, braces, backslashes, tabs/newlines, unicode and
# fake citation-looking tokens ([C99]) that must NOT leak into structured output.
MESSY_FRAGMENTS = [
    'VaR limit breach on the {d} book — utilisation hit 112% intraday; risk flagged '
    '"elevated" exposure to rates & FX vol (ref [C99], not a real id).',
    'PnL swing of +€4.2m / -£3.1m from client hedging {unwind}; booking lag '
    "(T+1) mis-captured a leg, ticket #INC-2024-00871 — awaiting sign-off.",
    'Stress "1987 crash" re-run w/ rates +200bp; tail loss = -12.8m\tvs limit -10m.\n'
    "Escalated to desk head, mgmt validation pending.",
    'Data quality: NULLs in greeks feed => delta/gamma showed 0.00; recompute pending. '
    "Underlyings: SX5E, SPX, 10Y UST. Maturities 3M/6M/2Y.",
    'Raw json-ish noise {"key": "value", "nested": [1, 2, 3]} plus a windows path '
    "C:\\risk\\reports\\q1.xlsx and a stray quote \" to trip naive parsers.",
    "Recurring FX delta drift on EM pairs (USD/TRY, USD/ZAR); recalibration overdue "
    "since Q4. 见备注 / véase la nota — model owner notified.",
    "",  # blank on purpose
    "n/a",
]


def _messy_comment(rng, paragraphs):
    n = rng.randint(1, max(1, paragraphs))
    parts = [
        rng.choice(MESSY_FRAGMENTS).replace("{d}", rng.choice(DESKS))
        for _ in range(n)
    ]
    return "  ".join(p for p in parts if p)


def _comment(rng, messy, paragraphs):
    if messy:
        return _messy_comment(rng, paragraphs)
    return rng.choice(PHRASES).format(d=rng.choice(DESKS))


def _dates(n, rng):
    start = date(2024, 1, 1)
    return [(start + timedelta(days=rng.randint(0, 180))).isoformat() for _ in range(n)]


def generate(output_dir: str, rows: int = 60, seed: int = 0,
             messy: bool = False, paragraphs: int = 4) -> dict:
    rng = random.Random(seed)
    os.makedirs(output_dir, exist_ok=True)

    cert = pd.DataFrame({
        "perimeter_name": [rng.choice(DESKS) for _ in range(rows)],
        "trading_desk": [rng.choice(DESKS) for _ in range(rows)],
        "indicator_name": [rng.choice(INDICATORS) for _ in range(rows)],
        "error_message": [rng.choice(["", "threshold exceeded", "missing data"]) for _ in range(rows)],
        "comment": [_comment(rng, messy, paragraphs) for _ in range(rows)],
        "managerial_validation_comment": [rng.choice(["validated", "", "pending"]) for _ in range(rows)],
        "related_scenario": [rng.choice(["", "1987 crash", "rates +200bp"]) for _ in range(rows)],
        "as_of_date": _dates(rows, rng),
    })

    ia = pd.DataFrame({
        "perimeter_name": [rng.choice(DESKS) for _ in range(rows)],
        "mmg_bl_comment": [_comment(rng, messy, paragraphs) for _ in range(rows)],
        "mmg_xbc_comment": [_comment(rng, messy, paragraphs) for _ in range(rows)],
        "managerial_validation_comment": [rng.choice(["validated", ""]) for _ in range(rows)],
        "as_of_date": _dates(rows, rng),
    })

    pnl = pd.DataFrame({
        "Trading Desk": [rng.choice(DESKS) for _ in range(rows)],
        "Comments": [_comment(rng, messy, paragraphs) for _ in range(rows)],
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
    parser.add_argument("--messy", action="store_true",
                        help="long, chaotic comments to stress the LLM/JSON parser")
    parser.add_argument("--paragraphs", type=int, default=4,
                        help="max messy fragments per comment (with --messy)")
    args = parser.parse_args()
    out = generate(args.out, rows=args.rows, seed=args.seed,
                   messy=args.messy, paragraphs=args.paragraphs)
    print(f"Wrote: {out}")
