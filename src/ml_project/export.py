"""Export ranked matching results to an Excel workbook."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def export_results(results: pd.DataFrame, output_path: str | Path) -> Path:
    """Write matching results to an .xlsx file and return its path."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    results.to_excel(path, index=False)
    return path