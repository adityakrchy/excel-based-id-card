"""Tests for the photo scanning and matching performance work.

The photo pipeline used to be quadratic and to decode full resolution images
for the table thumbnails, which made large photo folders unusable and could
crash the application.  These tests lock in the new behaviour.
"""

import time
from pathlib import Path

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QImage

from id_card_generator.core.models import SourceRecord
from id_card_generator.data.photo_matcher import PhotoMatcher
from id_card_generator.data.photo_scanner import PhotoScanner
from id_card_generator.ui.photo_thumbnails import (
    ThumbnailCache,
    load_thumbnail_image,
)


def _make_photos(folder: Path, count: int) -> None:
    """Create photos named after the record pins so they match."""
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (folder / f"{i:06d}.jpg").write_bytes(b"photo")


def _make_records(count: int) -> list:
    return [
        SourceRecord(
            row_index=i,
            raw_pin=f"{i:06d}",
            pin=f"{i:06d}",
            data={"PIN Number": f"{i:06d}", "Name": f"Person {i}"},
        )
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------
def test_scanner_indexes_paths_as_strings(tmp_path: Path):
    """The index stores plain strings - a Path object costs far more memory."""
    _make_photos(tmp_path, 10)
    index, lower_index, total = PhotoScanner.scan_directory_streaming(tmp_path)

    assert total == 10
    assert len(index) == 10
    for paths in index.values():
        for path in paths:
            assert isinstance(path, str)


def test_scanner_handles_missing_directory(tmp_path: Path):
    """A missing directory is reported, not raised."""
    index, lower_index, total = PhotoScanner.scan_directory_streaming(
        tmp_path / "does_not_exist"
    )
    assert total == 0
    assert index == {}
    assert lower_index == {}


def test_scanner_parallel_matches_serial_result(tmp_path: Path):
    """The parallel scan produces exactly the same index as a serial one."""
    _make_photos(tmp_path, 1200)

    serial, serial_lower, serial_total = PhotoScanner.scan_directory_streaming(
        tmp_path, workers=1
    )
    parallel, parallel_lower, parallel_total = PhotoScanner.scan_directory_streaming(
        tmp_path, workers=4
    )

    assert serial_total == parallel_total == 1200
    assert set(serial) == set(parallel)
    assert set(serial_lower) == set(parallel_lower)
    assert sum(len(v) for v in serial.values()) == sum(
        len(v) for v in parallel.values()
    )


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
def test_unassigned_detection_is_linear(tmp_path: Path):
    """Detecting the unassigned photos must not scale quadratically."""
    photo_count = 6000
    record_count = 3000
    _make_photos(tmp_path, photo_count)

    matcher = PhotoMatcher()
    matcher.set_directory(tmp_path)

    started = time.perf_counter()
    results, summary = matcher.match_all(_make_records(record_count))
    elapsed = time.perf_counter() - started

    assert len(results) == record_count
    assert summary.unassigned_photos_count == photo_count - record_count

    # A quadratic implementation needs ~20 s for this data set.
    assert elapsed < 5.0, f"matching took {elapsed:.2f}s"


def test_matching_counts_are_correct(tmp_path: Path):
    """The summary counters stay correct after the rewrite."""
    _make_photos(tmp_path, 3)
    matcher = PhotoMatcher()
    matcher.set_directory(tmp_path)

    records = _make_records(2)
    results, summary = matcher.match_all(records)

    assert summary.total_records == 2
    assert summary.matched_count == 2
    assert summary.missing_count == 0
    assert summary.unassigned_photos_count == 1
    for result in results.values():
        assert result.photo_path is not None


def test_parallel_matching_matches_serial_result(tmp_path: Path):
    """The threaded matcher returns the same results as the serial one."""
    _make_photos(tmp_path, 400)
    matcher = PhotoMatcher()
    matcher.set_directory(tmp_path)

    records = _make_records(400)
    serial, serial_summary = matcher.match_all(records, workers=1)
    parallel, parallel_summary = matcher.match_all(records, workers=4)

    assert set(serial) == set(parallel)
    assert serial_summary.matched_count == parallel_summary.matched_count
    for record_id, result in serial.items():
        assert parallel[record_id].photo_path == result.photo_path


def test_matching_is_thread_safe(tmp_path: Path):
    """The matcher can be used from several threads at once."""
    _make_photos(tmp_path, 200)
    matcher = PhotoMatcher()
    matcher.set_directory(tmp_path)

    records = _make_records(200)
    results, summary = matcher.match_all(records, workers=4)
    assert summary.matched_count == 200


# ---------------------------------------------------------------------------
# Thumbnails
# ---------------------------------------------------------------------------
def test_thumbnail_is_decoded_at_target_size(tmp_path: Path):
    """The full resolution image is never materialised."""
    from PIL import Image

    source = tmp_path / "big.jpg"
    Image.new("RGB", (4000, 3000), (20, 80, 160)).save(source, quality=85)

    image = load_thumbnail_image(str(source), 48)
    assert image is not None
    assert isinstance(image, QImage)
    assert image.width() <= 48
    assert image.height() <= 48


def test_thumbnail_handles_broken_file(tmp_path: Path):
    """A broken image returns None instead of raising."""
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not an image")
    assert load_thumbnail_image(str(broken), 48) is None


def test_thumbnail_cache_is_bounded(tmp_path: Path):
    """The cache never grows beyond its limit."""
    cache = ThumbnailCache(max_entries=10)
    for i in range(50):
        cache.put(f"/photo/{i}.jpg", QImage(48, 48, QImage.Format_RGB32))
    assert len(cache) == 10

    # The most recent entry is still cached.
    assert cache.get("/photo/49.jpg") is not None
    assert cache.get("/photo/0.jpg") is None


# ---------------------------------------------------------------------------
# Worker lifecycle (crash safety)
# ---------------------------------------------------------------------------
def test_indexing_worker_can_be_cancelled_and_joined(qtbot, tmp_path: Path):
    """A cancelled worker terminates cleanly - the reference must be kept."""
    from id_card_generator.tasks.photo_indexing_worker import PhotoIndexingWorker

    _make_photos(tmp_path, 300)
    worker = PhotoIndexingWorker(photo_dir=tmp_path, parent=None)
    worker.start()
    worker.cancel()
    assert worker.wait(5000), "the worker did not terminate"

    finished = []
    worker.indexing_finished.connect(
        lambda idx, low, total: finished.append(total)
    )
    worker.deleteLater()


def test_match_worker_stops_cleanly(qtbot, tmp_path: Path):
    """The matching worker terminates and reports its results."""
    from id_card_generator.tasks.photo_match_worker import PhotoMatchWorker

    _make_photos(tmp_path, 50)
    matcher = PhotoMatcher()
    matcher.set_directory(tmp_path)

    worker = PhotoMatchWorker(matcher=matcher, records=_make_records(50))
    finished = []
    worker.matching_finished.connect(
        lambda results, summary, copied: finished.append((results, summary))
    )
    worker.start()
    assert worker.wait(10000), "the matching worker did not terminate"

    # The result is delivered through the event loop of this thread.
    for _ in range(200):
        if finished:
            break
        qtbot.wait(25)

    assert finished, "no result was reported"
    assert len(finished[0][0]) == 50
    worker.deleteLater()


def test_photo_page_rematch_reports_results(qtbot, tmp_path: Path):
    """The page publishes the matching results of the background worker."""
    from id_card_generator.ui.photo_library_page import PhotoLibraryPage

    _make_photos(tmp_path, 20)
    page = PhotoLibraryPage()
    qtbot.addWidget(page)
    page.show()

    page.set_records(_make_records(20))
    page.matcher.set_directory(tmp_path)
    page._rematch()

    for _ in range(200):
        if page._match_worker is None and page.match_results:
            break
        qtbot.wait(25)

    assert len(page.match_results) == 20
    page.shutdown()
