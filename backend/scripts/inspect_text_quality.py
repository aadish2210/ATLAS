"""Inspect the raw dataset for language/encoding issues and saturation diagnostics.

Two questions:
  1. Are there Kannada rows? In which columns? How many?
  2. How easily can our current ESI saturate at 10 across the input space?
"""
from __future__ import annotations

import re

import pandas as pd

from app.core.config import settings

DEVANAGARI = re.compile(r"[\u0900-\u097F]")   # Hindi range (sometimes appears)
KANNADA = re.compile(r"[\u0C80-\u0CFF]")       # Kannada script range
TAMIL = re.compile(r"[\u0B80-\u0BFF]")
TELUGU = re.compile(r"[\u0C00-\u0C7F]")


def main() -> None:
    df = pd.read_csv(settings.raw_csv_path, low_memory=False)
    print(f"raw rows = {len(df):,}")

    text_cols = ["description", "comment", "address", "end_address",
                 "reason_breakdown", "cargo_material", "resolved_at_address"]

    def _count(series: pd.Series, pat: re.Pattern) -> int:
        return int(series.apply(lambda s: bool(pat.search(s))).sum())

    for col in text_cols:
        if col not in df.columns:
            continue
        s = df[col].dropna().astype(str)
        if s.empty:
            print(f"  {col:<22}  empty")
            continue
        n_kn = _count(s, KANNADA)
        n_hi = _count(s, DEVANAGARI)
        n_ta = _count(s, TAMIL)
        n_te = _count(s, TELUGU)
        print(f"  {col:<22}  rows={len(s):<5} kannada={n_kn} hindi={n_hi} tamil={n_ta} telugu={n_te}")
        if n_kn > 0:
            hits = s[s.apply(lambda x: bool(KANNADA.search(x)))]
            print(f"    examples: {hits.head(3).tolist()}")


if __name__ == "__main__":
    main()
