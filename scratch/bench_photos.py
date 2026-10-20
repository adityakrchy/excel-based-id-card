"""Benchmark the photo scanning / matching pipeline."""

import os
import shutil
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from id_card_generator.core.models import SourceRecord
from id_card_generator.data.photo_matcher import PhotoMatcher
from id_card_generator.data.photo_scanner import PhotoScanner


def build_fixture(root: Path, photos: int, records: int):
    photo_dir = root / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    for i in range(photos):
        (photo_dir / f"EMP_{i:06d}.jpg").write_bytes(b"x" * 64)
    recs = []
    for i in range(records):
        recs.append(
            SourceRecord(
                row_index=i,
                raw_pin=f"{i:06d}",
                pin=f"{i:06d}",
                data={"PIN Number": f"{i:06d}", "Name": f"Person {i}"},
            )
        )
    return recs


def main():
    n_photos = int(os.environ.get("BENCH_PHOTOS", "20000"))
    n_records = int(os.environ.get("BENCH_RECORDS", "20000"))

    tmp = Path(tempfile.mkdtemp())
    try:
        t0 = time.perf_counter()
        records = build_fixture(tmp, n_photos, n_records)
        print(f"fixture built in {time.perf_counter() - t0:.2f}s")

        t0 = time.perf_counter()
        index, lower_index, total = PhotoScanner.scan_directory_streaming(tmp / "photos")
        t_scan = time.perf_counter() - t0
        print(f"scan           : {t_scan:7.2f}s  ({total:,} files)")

        matcher = PhotoMatcher()
        t0 = time.perf_counter()
        matcher.set_indexes(index, lower_index)
        t_index = time.perf_counter() - t0
        print(f"set_indexes    : {t_index:7.2f}s")

        t0 = time.perf_counter()
        results, summary = matcher.match_all(records)
        t_match = time.perf_counter() - t0
        print(f"match_all      : {t_match:7.2f}s  ({summary.matched_count:,} matched)")
        print(f"TOTAL          : {t_scan + t_index + t_match:7.2f}s")

        import tracemalloc

        tracemalloc.start()
        idx2, low2, _ = PhotoScanner.scan_directory_streaming(tmp / "photos")
        matcher.set_indexes(idx2, low2)
        _, _ = matcher.match_all(records)
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        print(f"peak python mem: {peak / 1024 / 1024:7.1f} MB")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
