"""Unit tests for high-throughput streaming photo directory scanner and queue processing."""

from pathlib import Path
from id_card_generator.data.photo_scanner import PhotoScanner


def test_photo_scanner_streaming(tmp_path: Path):
    """Verify photo scanner streams batches incrementally and builds exact and lower indexes."""
    # Create 35 dummy image files
    for i in range(35):
        pin = f"EMP_{i:04d}"
        (tmp_path / f"{pin}.jpg").write_bytes(b"dummy image data")

    batches_received = []

    def on_batch(batch, total, latest_name):
        batches_received.append((list(batch), total, latest_name))

    exact_idx, lower_idx, total = PhotoScanner.scan_directory_streaming(
        photo_dir=tmp_path,
        on_batch=on_batch,
        batch_size=10,
    )

    assert total == 35
    assert len(exact_idx) == 35
    assert len(lower_idx) == 35
    # Should have emitted 4 batches: 10, 20, 30, and final 35
    assert len(batches_received) == 4
    assert batches_received[-1][1] == 35


def test_photo_scanner_streaming_cancellation(tmp_path: Path):
    """Verify streaming stops cleanly when cancellation is requested."""
    for i in range(25):
        (tmp_path / f"ST_{i:03d}.png").write_bytes(b"dummy")

    cancelled = False

    def is_cancelled():
        return cancelled

    def on_batch(batch, total, latest_name):
        nonlocal cancelled
        if total >= 10:
            cancelled = True

    exact_idx, lower_idx, total = PhotoScanner.scan_directory_streaming(
        photo_dir=tmp_path,
        on_batch=on_batch,
        is_cancelled=is_cancelled,
        batch_size=10,
    )

    # Should have cancelled early
    assert total < 25
