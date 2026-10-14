"""Scans photograph directories and indexes images by normalized filename stem with high-throughput streaming."""

from collections import defaultdict
import logging
import os
from pathlib import Path
import time
from typing import Callable, Dict, List, Optional, Set, Tuple
from id_card_generator.core.constants import SUPPORTED_IMAGE_EXTENSIONS
from id_card_generator.data.data_normalizer import DataNormalizer

logger = logging.getLogger(__name__)


class PhotoScanner:
    """Scans and indexes image files by their filename stem with high performance."""

    @staticmethod
    def scan_directory(photo_dir: Path) -> Dict[str, List[Path]]:
        """Fast synchronous directory scan using os.scandir."""
        index: Dict[str, List[Path]] = defaultdict(list)
        photo_dir = Path(photo_dir)
        if not photo_dir.exists() or not photo_dir.is_dir():
            logger.warning("Photo directory does not exist or is not a directory: %s", photo_dir)
            return index

        ext_set = {e.lower() for e in SUPPORTED_IMAGE_EXTENSIONS}
        dir_str = str(photo_dir)

        try:
            with os.scandir(dir_str) as entries:
                for entry in entries:
                    try:
                        name = entry.name
                        dot_idx = name.rfind(".")
                        if dot_idx == -1:
                            continue
                        ext = name[dot_idx:].lower()
                        if ext not in ext_set:
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue

                        raw_stem = name[:dot_idx]
                        _, normalized_stem = DataNormalizer.normalize_pin(raw_stem)
                        if normalized_stem:
                            index[normalized_stem].append(Path(entry.path))
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
    ) -> Tuple[Dict[str, List[Path]], Dict[str, List[Path]], int]:
        """Stream directory scan emitting batches of (stem, path_str) as items are discovered.
        
        Returns:
            Tuple of (exact_index, lower_index, total_indexed_files)
        """
        index: Dict[str, List[Path]] = defaultdict(list)
        lower_index: Dict[str, List[Path]] = defaultdict(list)
        photo_dir = Path(photo_dir)

        if not photo_dir.exists() or not photo_dir.is_dir():
            logger.warning("Photo directory does not exist: %s", photo_dir)
            return index, lower_index, 0

        ext_set = {e.lower() for e in SUPPORTED_IMAGE_EXTENSIONS}
        dir_str = str(photo_dir)
        sample_batch: List[Tuple[str, str]] = []
        total_files = 0
        last_emit = time.monotonic()

        try:
            with os.scandir(dir_str) as entries:
                for entry in entries:
                    if is_cancelled and is_cancelled():
                        logger.info("Photo scanning cancelled by user request.")
                        break

                    try:
                        name = entry.name
                        dot_idx = name.rfind(".")
                        if dot_idx == -1:
                            continue
                        ext = name[dot_idx:].lower()
                        if ext not in ext_set:
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue

                        raw_stem = name[:dot_idx]
                        _, normalized_stem = DataNormalizer.normalize_pin(raw_stem)
                        if not normalized_stem:
                            continue

                        path_obj = Path(entry.path)
                        index[normalized_stem].append(path_obj)
                        lower_stem = normalized_stem.lower()
                        lower_index[lower_stem].append(path_obj)

                        total_files += 1
                        sample_batch.append((normalized_stem, entry.path))
                        if len(sample_batch) > 20:
                            sample_batch.pop(0)

                        now = time.monotonic()
                        # Emit periodically or at batch threshold
                        if on_batch and (total_files % batch_size == 0 or (now - last_emit > 0.05 and sample_batch)):
                            on_batch(list(sample_batch), total_files, name)
                            last_emit = now
                            sample_batch.clear()

                    except (PermissionError, OSError):
                        continue

            # Emit final pending batch if any
            if on_batch and not (is_cancelled and is_cancelled()):
                latest_name = sample_batch[-1][1] if sample_batch else ""
                on_batch(list(sample_batch), total_files, latest_name)
                sample_batch.clear()

        except (PermissionError, OSError) as e:
            logger.error("Error reading directory %s: %s", photo_dir, e)

        return index, lower_index, total_files

    @staticmethod
    def get_all_photo_stems(index: Dict[str, List[Path]]) -> Set[str]:
        """Return all stems indexed."""
        return set(index.keys())
