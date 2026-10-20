"""Scans photograph directories and indexes images by normalized filename stem.

The scanner is designed for very large photo folders:

* file names are stored as plain strings - a ``Path`` object costs several
  times more memory than the string it wraps,
* the directory entries are processed by a small thread pool, so the
  (I/O bound) ``scandir``/``stat`` calls overlap,
* the result is streamed to the UI in batches so the interface stays
  responsive while tens of thousands of files are read.
"""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import logging
import os
from pathlib import Path
import time
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple
from id_card_generator.core.constants import SUPPORTED_IMAGE_EXTENSIONS
from id_card_generator.data.data_normalizer import DataNormalizer

logger = logging.getLogger(__name__)

# Files above this count are scanned with a thread pool.
PARALLEL_SCAN_THRESHOLD = 2000

# Upper bound of worker threads used while scanning.
MAX_SCAN_WORKERS = 8

# Number of directory entries handed to a worker at a time.
SCAN_CHUNK_SIZE = 512


class PhotoScanner:
    """Scans and indexes image files by their filename stem with high performance."""

    @staticmethod
    def _split_stem(name: str) -> Optional[str]:
        """Return the normalized stem of a file name, or None when unsupported."""
        dot_idx = name.rfind(".")
        if dot_idx == -1:
            return None
        ext = name[dot_idx:].lower()
        if ext not in _EXT_SET:
            return None
        _, normalized_stem = DataNormalizer.normalize_pin(name[:dot_idx])
        return normalized_stem or None

    @staticmethod
    def _index_entries(
        entries: Iterable[Tuple[str, str]],
    ) -> Tuple[Dict[str, List[str]], Dict[str, List[str]], List[str]]:
        """Index a batch of ``(file name, full path)`` tuples.

        Returns the exact index, the case-insensitive index and the sample of
        the most recent entries (used for the live preview table).
        """
        index: Dict[str, List[str]] = defaultdict(list)
        lower_index: Dict[str, List[str]] = defaultdict(list)
        sample: List[str] = []

        for name, full_path in entries:
            normalized_stem = PhotoScanner._split_stem(name)
            if not normalized_stem:
                continue
            index[normalized_stem].append(full_path)
            lower_index[normalized_stem.lower()].append(full_path)
            sample.append(full_path)

        return index, lower_index, sample

    @staticmethod
    def scan_directory(photo_dir: Path) -> Dict[str, List[str]]:
        """Fast synchronous directory scan using os.scandir."""
        index: Dict[str, List[str]] = defaultdict(list)
        photo_dir = Path(photo_dir)
        if not photo_dir.exists() or not photo_dir.is_dir():
            logger.warning("Photo directory does not exist or is not a directory: %s", photo_dir)
            return index

        dir_str = str(photo_dir)

        try:
            with os.scandir(dir_str) as entries:
                for entry in entries:
                    try:
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        normalized_stem = PhotoScanner._split_stem(entry.name)
                        if normalized_stem:
                            index[normalized_stem].append(entry.path)
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError) as e:
            logger.error("Failed to scan photo directory %s: %s", photo_dir, e)
            return index

        logger.info(
            "Scanned photo directory %s: indexed %d unique stems.",
            photo_dir,
            len(index),
        )
        return index

    @staticmethod
    def scan_directory_streaming(
        photo_dir: Path,
        on_batch: Optional[Callable[[List[Tuple[str, str]], int, str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        batch_size: int = 150,
        workers: int = 0,
    ) -> Tuple[Dict[str, List[str]], Dict[str, List[str]], int]:
        """Stream a directory scan, emitting batches as items are discovered.

        The directory entries are read in chunks; the (I/O bound) file checks
        of a chunk are spread over a small thread pool so the scan keeps up
        with fast disks and network shares.

        Returns:
            Tuple of (exact_index, lower_index, total_indexed_files)
        """
        index: Dict[str, List[str]] = defaultdict(list)
        lower_index: Dict[str, List[str]] = defaultdict(list)
        photo_dir = Path(photo_dir)

        if not photo_dir.exists() or not photo_dir.is_dir():
            logger.warning("Photo directory does not exist: %s", photo_dir)
            return index, lower_index, 0

        dir_str = str(photo_dir)
        total_files = 0
        last_emit = time.monotonic()
        pending_sample: List[Tuple[str, str]] = []

        def _cancelled() -> bool:
            return bool(is_cancelled and is_cancelled())

        def _emit_batch(sample: List[Tuple[str, str]], total: int) -> None:
            """Emit a batch of freshly discovered photos to the UI."""
            nonlocal last_emit
            if not on_batch or not sample:
                return
            latest_name = os.path.basename(sample[-1][1]) if sample else ""
            on_batch(list(sample), total, latest_name)
            last_emit = time.monotonic()

        def _chunked(entries) -> Iterable[List[Tuple[str, str]]]:
            """Yield chunks of candidate entries from the directory iterator."""
            chunk: List[Tuple[str, str]] = []
            for entry in entries:
                name = entry.name
                dot_idx = name.rfind(".")
                if dot_idx == -1:
                    continue
                if name[dot_idx:].lower() not in _EXT_SET:
                    continue
                chunk.append((name, entry.path))
                if len(chunk) >= SCAN_CHUNK_SIZE:
                    yield chunk
                    chunk = []
            if chunk:
                yield chunk

        def _is_file(path: str) -> bool:
            try:
                return os.path.isfile(path)
            except (PermissionError, OSError):
                return False

        try:
            with os.scandir(dir_str) as entries:
                if workers <= 0:
                    workers = 1
                else:
                    workers = max(1, min(workers, MAX_SCAN_WORKERS))

                pool = ThreadPoolExecutor(max_workers=workers) if workers > 1 else None
                try:
                    for chunk in _chunked(entries):
                        if _cancelled():
                            logger.info("Photo scanning cancelled by user request.")
                            break

                        if pool is not None:
                            # Overlap the file system checks of this chunk.
                            flags = list(pool.map(_is_file, [c[1] for c in chunk]))
                            filtered = [
                                item for item, ok in zip(chunk, flags) if ok
                            ]
                        else:
                            filtered = [item for item in chunk if _is_file(item[1])]

                        for name, full_path in filtered:
                            normalized_stem = PhotoScanner._split_stem(name)
                            if not normalized_stem:
                                continue
                            index[normalized_stem].append(full_path)
                            lower_index[normalized_stem.lower()].append(full_path)
                            pending_sample.append((normalized_stem, full_path))
                            total_files += 1

                            if on_batch and (
                                len(pending_sample) >= batch_size
                                or (time.monotonic() - last_emit > 0.05)
                            ):
                                _emit_batch(list(pending_sample), total_files)
                                pending_sample.clear()

                            if _cancelled():
                                logger.info("Photo scanning cancelled by user request.")
                                break
                        else:
                            continue
                        break
                finally:
                    if pool is not None:
                        pool.shutdown(wait=False)

            # Emit the final pending batch if any
            if on_batch and not _cancelled():
                _emit_batch(list(pending_sample), total_files)
                pending_sample.clear()

        except (PermissionError, OSError) as e:
            logger.error("Error reading directory %s: %s", photo_dir, e)

        return index, lower_index, total_files

    @staticmethod
    def get_all_photo_stems(index: Dict[str, List[str]]) -> Set[str]:
        """Return all stems indexed."""
        return set(index.keys())


# Extension lookup is built once - it is consulted for every single file.
_EXT_SET = {e.lower() for e in SUPPORTED_IMAGE_EXTENSIONS}
