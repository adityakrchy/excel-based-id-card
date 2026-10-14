"""Scans photograph directories and indexes images by normalized filename stem."""

import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set
from id_card_generator.core.constants import SUPPORTED_IMAGE_EXTENSIONS
from id_card_generator.data.data_normalizer import DataNormalizer

logger = logging.getLogger(__name__)


class PhotoScanner:
    """Scans and indexes image files by their filename stem."""

    @staticmethod
    def scan_directory(photo_dir: Path) -> Dict[str, List[Path]]:
        """Scan a directory and index image files by normalized stem.
        
        Returns:
            Dictionary mapping normalized_stem -> List[Path to image files]
        """
        index: Dict[str, List[Path]] = defaultdict(list)
        if not photo_dir.exists() or not photo_dir.is_dir():
            logger.warning("Photo directory does not exist or is not a directory: %s", photo_dir)
            return index

        for entry in photo_dir.iterdir():
            if not entry.is_file():
                continue

            ext = entry.suffix.lower()
            if ext not in SUPPORTED_IMAGE_EXTENSIONS:
                continue

            raw_stem = entry.stem
            _, normalized_stem = DataNormalizer.normalize_pin(raw_stem)

            if normalized_stem:
                index[normalized_stem].append(entry)

        logger.info(
            "Scanned photo directory %s: indexed %d unique stems across all image files.",
            photo_dir,
            len(index),
        )
        return index

    @staticmethod
    def get_all_photo_stems(index: Dict[str, List[Path]]) -> Set[str]:
        """Return all stems indexed."""
        return set(index.keys())
