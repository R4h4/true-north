"""Write headers-only CSV files (header row, zero data rows) for every table.

The committed state of ``data/csv/`` is headers only. The generator overwrites these
with header+data; run this module to reset back to headers-only before committing.

    uv run python -m generator.write_headers
"""

from __future__ import annotations

import csv
from pathlib import Path

from generator.schema import TABLES, column_names

CSV_DIR = Path(__file__).resolve().parent.parent / "data" / "csv"


def write_headers(csv_dir: Path = CSV_DIR) -> list[Path]:
    csv_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for table in TABLES:
        path = csv_dir / f"{table}.csv"
        with path.open("w", newline="") as f:
            csv.writer(f).writerow(column_names(table))
        written.append(path)
    return written


def main() -> None:
    written = write_headers()
    for path in written:
        print(f"wrote headers: {path.relative_to(path.parent.parent.parent)}")


if __name__ == "__main__":
    main()
