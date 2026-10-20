"""Coordinates the final export of approved ID cards, manifests and contact sheets.

The export writes **one file per card** - an entire sheet is never produced
unless the optional printable contact sheet is explicitly requested.
"""

import logging
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PIL import Image

from id_card_generator.core.constants import OutputFormat, ReviewStatus
from id_card_generator.core.exceptions import ExportError
from id_card_generator.core.models import (
    ExportConfiguration,
    ExportResult,
    PhotoMatchResult,
    ReviewRecord,
    SourceRecord,
)
from id_card_generator.data.data_normalizer import DataNormalizer
from id_card_generator.export.contact_sheet import ContactSheetGenerator
from id_card_generator.export.manifest_writer import ManifestWriter

logger = logging.getLogger(__name__)

# Cards above this count are exported on a thread pool.
PARALLEL_EXPORT_THRESHOLD = 25

# Upper bound of export workers.
MAX_EXPORT_WORKERS = 8

# Placeholders understood by the file name pattern.
FILENAME_TOKENS = ("PIN_NUMBER", "NAME", "ROW", "ID")


class ExportManager:
    """Exports staged cards to the final destination and creates audit artifacts."""

    @staticmethod
    def build_filename(
        config: ExportConfiguration,
        review: ReviewRecord,
        source_record: Optional[SourceRecord] = None,
        index: int = 0,
    ) -> str:
        """Build the destination file name for a card.

        The ``{PIN_NUMBER}``, ``{NAME}``, ``{ROW}`` and ``{ID}`` tokens are
        replaced; unknown tokens fall back to a safe ``PIN_NAME`` pattern.
        """
        pattern = (config.naming_pattern or "").strip() or "{PIN_NUMBER}_{NAME}"

        values = {
            "PIN_NUMBER": review.pin or (source_record.pin if source_record else ""),
            "NAME": review.name or (
                source_record.get_value("Name", "") if source_record else ""
            ),
            "ROW": str(source_record.row_index if source_record else index),
            "ID": (review.record_id or "")[:8],
        }

        try:
            name = pattern.format(**values)
        except (KeyError, IndexError, ValueError):
            logger.warning("Invalid naming pattern %r - using the default.", pattern)
            name = f"{values['PIN_NUMBER']}_{values['NAME']}"

        name = DataNormalizer.sanitize_filename(name) or f"card_{index + 1:05d}"
        extension = ".jpg" if config.format == OutputFormat.JPEG else ".png"
        return f"{name}{extension}"

    @staticmethod
    def _write_card(
        src_img_path: Path,
        dest_file: Path,
        config: ExportConfiguration,
    ) -> None:
        """Copy or re-encode a single card into the destination folder."""
        dest_ext = ".jpg" if config.format == OutputFormat.JPEG else ".png"
        needs_reencode = (
            src_img_path.suffix.lower() != dest_ext or config.format == OutputFormat.JPEG
        )

        if not needs_reencode:
            shutil.copy2(src_img_path, dest_file)
            return

        with Image.open(src_img_path) as im:
            img_dpi = im.info.get("dpi", (300, 300))
            if config.format == OutputFormat.JPEG:
                rgb_im = im.convert("RGB")
                rgb_im.save(
                    dest_file,
                    format="JPEG",
                    quality=config.jpeg_quality,
                    optimize=True,
                    dpi=img_dpi,
                )
            else:
                im.save(dest_file, format="PNG", optimize=True, dpi=img_dpi)

    @staticmethod
    def export_batch(
        config: ExportConfiguration,
        review_records: List[ReviewRecord],
        source_records_map: Dict[str, SourceRecord],
        match_results_map: Dict[str, PhotoMatchResult],
    ) -> ExportResult:
        """Execute the export workflow based on the configuration.

        Every approved card is written as its own image file.  The copies run
        on a thread pool because a batch of cards is I/O bound.
        """
        out_dir = Path(config.output_dir)
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            # Test writability
            test_file = out_dir / ".write_test"
            test_file.touch()
            test_file.unlink()
        except Exception as e:
            raise ExportError(f"Output directory is not writable: {e}") from e

        result = ExportResult()
        result.total_records = len(review_records)

        manifest_entries: List[Dict[str, str]] = []
        contact_sheet_items: List[Tuple[Path, str, str]] = []

        # 1. Work out which cards are exported (policy check).
        selected: List[Tuple[int, ReviewRecord]] = []
        for index, rev in enumerate(review_records):
            if config.approved_only and rev.status != ReviewStatus.APPROVED:
                result.skipped_count += 1
                continue
            selected.append((index, rev))

        if not selected:
            logger.info("Nothing to export - no card passed the export policy.")
            return result

        # 2. Copy / convert the cards in parallel.
        def _export_one(item) -> Dict[str, object]:
            index, rev = item
            entry: Dict[str, object] = {"index": index, "pin": rev.pin}

            if not rev.rendered_image_path or not Path(rev.rendered_image_path).exists():
                entry["error"] = "Card image not generated or missing from staging area."
                return entry

            src_img_path = Path(rev.rendered_image_path)
            source_record = source_records_map.get(rev.record_id)
            dest_filename = ExportManager.build_filename(
                config, rev, source_record, index
            )
            dest_file = out_dir / dest_filename

            # Never overwrite a different card with the same name.
            if dest_file.exists() and dest_file.resolve() != src_img_path.resolve():
                stem, suffix = dest_file.stem, dest_file.suffix
                candidate = dest_file
                counter = 1
                while candidate.exists():
                    candidate = out_dir / f"{stem}_{counter}{suffix}"
                    counter += 1
                dest_file = candidate
                dest_filename = candidate.name

            try:
                ExportManager._write_card(src_img_path, dest_file, config)
            except Exception as e:
                logger.error("Failed to export card for PIN %s: %s", rev.pin, e)
                entry["error"] = str(e)
                return entry

            entry["dest_file"] = dest_file
            entry["dest_filename"] = dest_filename
            return entry

        workers = ExportManager._resolve_workers(len(selected))
        if workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                outcomes = list(pool.map(_export_one, selected))
        else:
            outcomes = [_export_one(item) for item in selected]

        # 3. Book the results (in record order) and build the manifest.
        for (index, rev), outcome in zip(selected, outcomes):
            error = outcome.get("error")
            if error:
                result.failed_count += 1
                result.errors.append({"pin": rev.pin, "error": str(error)})
                continue

            dest_file = outcome["dest_file"]
            dest_filename = outcome["dest_filename"]
            src_rec = source_records_map.get(rev.record_id)
            match_res = match_results_map.get(rev.record_id)

            result.exported_count += 1
            result.exported_files.append(str(dest_file))
            contact_sheet_items.append((dest_file, rev.pin, rev.name))

            # Collect manifest metadata (include all arbitrary columns)
            entry = {
                "pin": rev.pin,
                "name": rev.name,
                "source_row": str(src_rec.row_index) if src_rec else "",
                "photo_path": match_res.photo_path if match_res else "",
                "output_filename": dest_filename,
                "review_status": str(rev.status.value),
                "export_status": "Success",
            }
            if src_rec:
                for k, v in src_rec.data.items():
                    if k not in entry:
                        entry[k] = str(v)
            manifest_entries.append(entry)

        # Generate manifest if requested
        if config.export_manifest and manifest_entries:
            manifest_path = out_dir / "export_manifest.csv"
            ManifestWriter.write_manifest(manifest_entries, manifest_path)
            result.manifest_path = str(manifest_path)

        # Generate the optional printable contact sheet
        if config.export_contact_sheet and contact_sheet_items:
            contact_path = out_dir / "contact_sheet.pdf"
            ContactSheetGenerator.generate_pdf(
                contact_sheet_items,
                contact_path,
                columns=config.sheet_columns,
                rows=config.sheet_rows,
                margin_mm=config.sheet_margin_mm,
            )
            result.contact_sheet_path = str(contact_path)

        logger.info(
            "Export complete: %d exported, %d skipped, %d failed.",
            result.exported_count,
            result.skipped_count,
            result.failed_count,
        )
        return result

    @staticmethod
    def _resolve_workers(card_count: int) -> int:
        """Return the number of export workers used for a batch."""
        return min(
            MAX_EXPORT_WORKERS,
            max(1, card_count // PARALLEL_EXPORT_THRESHOLD),
        )
