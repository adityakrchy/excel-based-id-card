"""Benchmark the photo library page: scanning, matching, table fill, thumbnails."""

import os
import shutil
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

app = QApplication([])

from PIL import Image

from id_card_generator.core.models import ProjectConfiguration, SourceRecord
from id_card_generator.ui.photo_library_page import PhotoLibraryPage

N_PHOTOS = int(os.environ.get("BENCH_PHOTOS", "4000"))
N_RECORDS = int(os.environ.get("BENCH_RECORDS", "4000"))


def main():
    tmp = Path(tempfile.mkdtemp())
    try:
        photos = tmp / "photos"
        photos.mkdir()
        print(f"creating {N_PHOTOS} photos...")
        # Real 600x800 JPEGs so the thumbnail path is exercised.
        template = Image.new("RGB", (600, 800), (60, 90, 160))
        for i in range(N_PHOTOS):
            template.save(photos / f"EMP_{i:06d}.jpg", quality=70)

        records = [
            SourceRecord(
                row_index=i,
                raw_pin=f"{i:06d}",
                pin=f"{i:06d}",
                data={"PIN Number": f"{i:06d}", "Name": f"Person {i}"},
            )
            for i in range(N_RECORDS)
        ]

        page = PhotoLibraryPage()
        page.resize(1440, 900)
        page.show()

        t0 = time.perf_counter()
        page.matcher.set_directory(photos)
        deadline = time.perf_counter() + 120
        while page._worker is not None and time.perf_counter() < deadline:
            app.processEvents()
            time.sleep(0.01)
        scan_time = time.perf_counter() - t0
        print(f"scan + index   : {scan_time:6.2f}s")

        page.set_records(records)
        t0 = time.perf_counter()
        deadline = time.perf_counter() + 120
        while (page._match_worker is not None or not page.match_results) and time.perf_counter() < deadline:
            app.processEvents()
            time.sleep(0.01)
        match_time = time.perf_counter() - t0
        print(f"match + table  : {match_time:6.2f}s  ({len(page.match_results):,} results)")

        # Let the thumbnail workers finish.
        t0 = time.perf_counter()
        deadline = time.perf_counter() + 120
        while page._thread_pool.activeThreadCount() and time.perf_counter() < deadline:
            app.processEvents()
            time.sleep(0.01)
        print(f"thumbnails     : {time.perf_counter() - t0:6.2f}s")

        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024
        print(f"peak rss       : {usage:6.1f} MB")
        print(f"rows in table  : {page.table.rowCount()}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
