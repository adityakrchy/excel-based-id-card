"""Core batch generation engine handling records, staging, and naming."""

import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional
from PIL import Image

from id_card_generator.core.constants import (
    MatchStatus,
    MissingPhotoPolicy,
    OutputFormat,
)
from id_card_generator.core.models import (
    PhotoMatchResult,
    RenderResult,
    RenderSettings,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.data.data_normalizer import DataNormalizer
from id_card_generator.rendering.pillow_renderer import PillowRenderer
from id_card_generator.resources.resource_loader import get_staging_dir

logger = logging.getLogger(__name__)


class GenerationSummary:
    """Summary of batch generation process."""

    def __init__(self) -> None:
        self.total_records: int = 0
        self.completed_count: int = 0
        self.skipped_count: int = 0
        self.failed_count: int = 0
        self.cancelled: bool = False
        self.results: List[RenderResult] = []


class BatchGenerator:
    """Processes records sequentially, producing rendered cards in the staging area."""

    @staticmethod
    def generate_single_card(
        template: TemplateDefinition,
        record: SourceRecord,
        match_result: Optional[PhotoMatchResult],
        column_mappings: Dict[str, str],
        settings: RenderSettings,
        target_dir: Path,
    ) -> RenderResult:
        """Render and save a single record's ID card."""
        warnings: List[str] = []

        # Validate PIN
        if not record.pin:
            return RenderResult(
                record_id=record.record_id,
                pin=record.pin or "",
                success=False,
                error_message="Missing PIN Number: card cannot be generated.",
            )

        # Evaluate photo availability against policy
        photo_path = match_result.photo_path if match_result else None
        if not photo_path or not Path(photo_path).exists():
            if settings.missing_photo_policy == MissingPhotoPolicy.SKIP_RECORD:
                return RenderResult(
                    record_id=record.record_id,
                    pin=record.pin,
                    success=False,
                    warnings=["Skipped: Missing photograph policy is set to Skip."],
                )
            elif settings.missing_photo_policy == MissingPhotoPolicy.FAIL_RECORD:
                return RenderResult(
                    record_id=record.record_id,
                    pin=record.pin,
                    success=False,
                    error_message=f"Missing photograph for PIN {record.pin}",
                )

        # Generate unique sanitized filename
        raw_name = record.get_value("Name", "Card")
        sanitized_name = DataNormalizer.sanitize_filename(raw_name)
        sanitized_pin = DataNormalizer.sanitize_filename(record.pin)
        ext = ".jpg" if settings.output_format == OutputFormat.JPEG else ".png"

        filename = f"{sanitized_pin}_{sanitized_name}{ext}"
        out_path = target_dir / filename

        # Resolve collisions if duplicate names/PINs exist
        if out_path.exists():
            filename = f"{sanitized_pin}_{sanitized_name}_row{record.row_index}{ext}"
            out_path = target_dir / filename

        try:
            img, render_warnings = PillowRenderer.render_card(
                template=template,
                record=record,
                photo_path=photo_path,
                column_mappings=column_mappings,
                settings=settings,
            )
            warnings.extend(render_warnings)

            # Save image
            target_dir.mkdir(parents=True, exist_ok=True)
            if settings.output_format == OutputFormat.JPEG:
                img.save(out_path, format="JPEG", quality=settings.jpeg_quality, optimize=True)
            else:
                img.save(out_path, format="PNG", optimize=True)

            return RenderResult(
                record_id=record.record_id,
                pin=record.pin,
                success=True,
                image_path=str(out_path),
                warnings=warnings,
            )
        except Exception as e:
            logger.error("Generation failed for record PIN %s: %s", record.pin, e)
            return RenderResult(
                record_id=record.record_id,
                pin=record.pin,
                success=False,
                error_message=str(e),
                warnings=warnings,
            )

    @staticmethod
    def generate_batch(
        template: TemplateDefinition,
        records: List[SourceRecord],
        match_results: Dict[str, PhotoMatchResult],
        column_mappings: Dict[str, str],
        settings: RenderSettings,
        target_dir: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> GenerationSummary:
        """Batch generate cards for all provided records."""
        staging_dir = target_dir or get_staging_dir()
        staging_dir.mkdir(parents=True, exist_ok=True)

        summary = GenerationSummary()
        summary.total_records = len(records)

        for i, rec in enumerate(records):
            if cancel_check and cancel_check():
                summary.cancelled = True
                logger.info("Batch generation cancelled by user at record %d/%d", i, len(records))
                break

            match = match_results.get(rec.record_id)
            res = BatchGenerator.generate_single_card(
                template=template,
                record=rec,
                match_result=match,
                column_mappings=column_mappings,
                settings=settings,
                target_dir=staging_dir,
            )
            summary.results.append(res)

            if res.success:
                summary.completed_count += 1
                status_msg = "Generated"
            elif res.warnings and any("Skipped" in w for w in res.warnings):
                summary.skipped_count += 1
                status_msg = "Skipped"
            else:
                summary.failed_count += 1
                status_msg = f"Failed: {res.error_message}"

            if progress_callback:
                progress_callback(i + 1, len(records), rec.pin, status_msg)

        logger.info(
            "Batch generation completed: %d success, %d skipped, %d failed out of %d",
            summary.completed_count,
            summary.skipped_count,
            summary.failed_count,
            summary.total_records,
        )
        return summary
