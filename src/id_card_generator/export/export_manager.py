"""Coordinates final export of approved ID cards, manifests, and contact sheets."""

import logging
import os
import shutil
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
from id_card_generator.export.contact_sheet import ContactSheetGenerator
from id_card_generator.export.manifest_writer import ManifestWriter

logger = logging.getLogger(__name__)


class ExportManager:
    """Exports staged cards to final user destination and creates audit artifacts."""

    @staticmethod
    def export_batch(
        config: ExportConfiguration,
        review_records: List[ReviewRecord],
        source_records_map: Dict[str, SourceRecord],
        match_results_map: Dict[str, PhotoMatchResult],
    ) -> ExportResult:
        """Execute full export workflow based on configuration."""
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

        for rev in review_records:
            # Check policy: approved only vs all generated
            if config.approved_only and rev.status != ReviewStatus.APPROVED:
                result.skipped_count += 1
                continue

            if not rev.rendered_image_path or not Path(rev.rendered_image_path).exists():
                result.failed_count += 1
                result.errors.append({
                    "pin": rev.pin,
                    "error": "Card image not generated or missing from staging area.",
                })
                continue

            src_img_path = Path(rev.rendered_image_path)
            src_rec = source_records_map.get(rev.record_id)
            match_res = match_results_map.get(rev.record_id)

            dest_filename = src_img_path.name
            dest_file = out_dir / dest_filename

            # Handle format conversion if destination format differs from staging
            dest_ext = ".jpg" if config.format == OutputFormat.JPEG else ".png"
            if src_img_path.suffix.lower() != dest_ext:
                dest_filename = f"{src_img_path.stem}{dest_ext}"
                dest_file = out_dir / dest_filename

            try:
                if src_img_path.suffix.lower() != dest_ext or config.format == OutputFormat.JPEG:
                    with Image.open(src_img_path) as im:
                        img_dpi = im.info.get("dpi", (300, 300))
                        if config.format == OutputFormat.JPEG:
                            rgb_im = im.convert("RGB")
                            rgb_im.save(dest_file, format="JPEG", quality=config.jpeg_quality, optimize=True, dpi=img_dpi)
                        else:
                            im.save(dest_file, format="PNG", optimize=True, dpi=img_dpi)
                else:
                    shutil.copy2(src_img_path, dest_file)

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

            except Exception as e:
                logger.error("Failed to export card for PIN %s: %s", rev.pin, e)
                result.failed_count += 1
                result.errors.append({"pin": rev.pin, "error": str(e)})

        # Generate manifest if requested
        if config.export_manifest and manifest_entries:
            manifest_path = out_dir / "export_manifest.csv"
            ManifestWriter.write_manifest(manifest_entries, manifest_path)
            result.manifest_path = str(manifest_path)

        # Generate contact sheet if requested
        if config.export_contact_sheet and contact_sheet_items:
            contact_path = out_dir / "contact_sheet.pdf"
            ContactSheetGenerator.generate_pdf(contact_sheet_items, contact_path)
            result.contact_sheet_path = str(contact_path)

        logger.info(
            "Export complete: %d exported, %d skipped, %d failed.",
            result.exported_count,
            result.skipped_count,
            result.failed_count,
        )
        return result
