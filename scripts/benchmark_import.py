"""Import-pipeline benchmark for large spreadsheets.

Generates a synthetic workbook of a chosen size and times the legacy
blocking path (``ExcelImporter.import_data``) against the streamed pipeline
(``SpreadsheetLoadPipeline.run_sync``), including the optional process-pool
backend (``ID_STREAM_PROCESS_POOL=1``).

Usage::

    uv run python scripts/benchmark_import.py [--rows 25000] [--cols 10]

The report prints per-path wall time, throughput, and the peak process
memory sampled with ``ProcessMetrics``.
"""

from __future__ import annotations

import argparse
import random
import sys
import tempfile
import time
from pathlib import Path

# Make the src package importable when run from a bare checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from id_card_generator.core.process_metrics import ProcessMetrics  # noqa: E402
from id_card_generator.data.data_validator import DataValidator  # noqa: E402
from id_card_generator.data.excel_importer import ExcelImporter  # noqa: E402
from id_card_generator.data.load_pipeline import (  # noqa: E402
    SpreadsheetLoadPipeline,
    configured_chunk_size,
    configured_worker_count,
    process_pool_enabled,
)

# Kruti Dev sample fragments exercising the Hindi conversion path.
KRUTI_SAMPLES = [
    "dkslh vkSDl",
    "efUnze~ lks",
    "piA fjfd",
    "gksjk.k Hkw",
]

ASCII_NAMES = [
    "Aditya Sharma", "Priya Patel", "Ravi Kumar", "Neha Gupta",
    "Sanjay Mehta", "Kiran Joshi", "Meera Iyer", "Arjun Rao",
    "Divya Nair", "Vikram Singh",
]
DEPARTMENTS = ["Production", "Design", "HR", "Finance", "Security", "Marketing"]


def build_workbook(path: Path, rows: int, cols: int) -> None:
    """Write a synthetic spreadsheet with a mix of types and Hindi cells."""
    import openpyxl

    headers = ["PIN Number", "Employee ID", "Name", "Designation", "Department"]
    extra = [
        "Photo Path", "Joining Date", "Salary", "Remarks", "Kruti Text",
        "Alias", "Zone", "Shift", "Grade", "Blood Group",
    ]
    headers += extra[: max(cols - len(headers), 0)]
    while len(headers) < cols:
        headers.append(f"Extra {len(headers)}")

    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet("Sheet1")
    ws.append(headers)
    rng = random.Random(2026)
    for i in range(rows):
        row = [
            f"PIN{i:06d}",                                        # unique PIN
            f"EMP-{i:05d}",
            ASCII_NAMES[i % len(ASCII_NAMES)],
            "Officer" if i % 3 else "Inspector",
            DEPARTMENTS[i % len(DEPARTMENTS)],
            f"photo_{i % 500:03d}.png",
            f"2024-0{1 + i % 9}-1{ i % 9}",
            1200.5 + (i % 977),
            "" if i % 37 == 0 else "regular desk duty",           # NaN gaps
            KRUTI_SAMPLES[i % len(KRUTI_SAMPLES)] if i % 5 == 0 else "",
        ][:cols]
        while len(row) < cols:
            row.append(f"x{i % 13}")
        ws.append(row)
    wb.save(str(path))


def time_legacy(path: Path) -> tuple[float, float, int]:
    """Time the historical blocking facade; returns (seconds, peak MB, records)."""
    metrics = ProcessMetrics()
    started = time.monotonic()
    _cols, records = ExcelImporter.import_data(path)
    elapsed = time.monotonic() - started
    _, mem = metrics.sample()
    return elapsed, mem, len(records)


def time_pipeline(path: Path) -> tuple[float, float, int, str, int]:
    """Time the streamed pipeline synchronously on the caller thread."""
    metrics = ProcessMetrics()
    pipeline = SpreadsheetLoadPipeline()
    started = time.monotonic()
    result = pipeline.run_sync(_request(path))
    elapsed = time.monotonic() - started
    _, mem = metrics.sample()
    report = DataValidator.validate_records(result.records)
    assert report.total_records == result.committed_rows
    return (
        elapsed,
        max(mem, result.peak_memory_mb),
        result.committed_rows,
        result.backend,
        result.worker_count,
    )


def _request(path: Path):
    from id_card_generator.data.load_pipeline import LoadRequest

    return LoadRequest(file_path=path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=25000)
    parser.add_argument("--cols", type=int, default=10)
    parser.add_argument(
        "--skip-legacy",
        action="store_true",
        help="skip the blocking facade (useful when comparing backends only)",
    )
    args = parser.parse_args()

    workers = configured_worker_count()
    chunk = configured_chunk_size(args.rows)
    backend_flag = "process pool ON" if process_pool_enabled() else "threads"

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "benchmark.xlsx"
        print(f"Generating {args.rows:,} rows × {args.cols} columns…")
        t_gen = time.monotonic()
        build_workbook(path, args.rows, args.cols)
        print(f"Workbook ready in {time.monotonic() - t_gen:.1f}s → {path.name}\n")

        print(f"{'path':<28}{'seconds':>9}{'rows/s':>10}{'peak MB':>9}  notes")
        if not args.skip_legacy:
            seconds, mem, n = time_legacy(path)
            print(
                f"{'legacy import_data':<28}{seconds:>9.2f}{n / seconds / 1000:>9.1f}k{mem:>8.0f}"
                f"  blocking, 1 thread"
            )

        seconds, mem, n, backend, final_workers = time_pipeline(path)
        print(
            f"{'pipeline (run_sync)':<28}{seconds:>9.2f}{n / seconds / 1000:>9.1f}k{mem:>8.0f}"
            f"  {final_workers} workers · {backend} · chunk {chunk:,}"
        )

        print(f"\nenv: workers={workers} · backend={backend_flag} · rows={args.rows:,}")


if __name__ == "__main__":
    main()
