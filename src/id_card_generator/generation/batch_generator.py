"""Core batch generation engine handling records, staging, and naming."""

import logging
from concurrent.futures import ThreadPoolExecutor
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

# Records above this count are rendered on a thread pool.
PARALLEL_RENDER_THRESHOLD = 20

# Upper bound of render workers.
MAX_RENDER_WORKERS = 8


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
        raw_name = record.get_value("Name", "")
        if not raw_name:
            for k, v in record.data.items():
                if "name" in k.lower() and v:
                    raw_name = str(v)
                    break
        raw_name = raw_name or "Card"

        sanitized_name = DataNormalizer.sanitize_filename(raw_name)
        sanitized_pin = DataNormalizer.sanitize_filename(record.pin or record.raw_pin or "ID")
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

            # Save image with authoritative DPI metadata
            target_dir.mkdir(parents=True, exist_ok=True)
            card_dpi = (template.dpi, template.dpi)
            if settings.output_format == OutputFormat.JPEG:
                img.save(out_path, format="JPEG", quality=settings.jpeg_quality, optimize=True, dpi=card_dpi)
            else:
                img.save(out_path, format="PNG", optimize=True, dpi=card_dpi)

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
    def resolve_workers(record_count: int, workers: int = 0) -> int:
        """Return the number of render workers used for a batch."""
        if workers <= 0:
            return min(
                MAX_RENDER_WORKERS,
                max(1, record_count // PARALLEL_RENDER_THRESHOLD),
            )
        return max(1, min(workers, MAX_RENDER_WORKERS))

    @staticmethod
    def generate_batch(
        template: TemplateDefinition,
        records: List[SourceRecord],
        match_results: Dict[str, PhotoMatchResult],
        column_mappings: Dict[str, str],
        settings: RenderSettings,
        target_dir: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
        record_callback: Optional[Callable[[RenderResult], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        workers: int = 0,
    ) -> GenerationSummary:
        """Batch generate cards for all provided records.

        The cards are rendered on a thread pool (Pillow releases the GIL while
        rasterising, so this really runs in parallel).  The results keep the
        order of the records, no matter in which order they were rendered.
        """
        staging_dir = target_dir or get_staging_dir()
        staging_dir.mkdir(parents=True, exist_ok=True)

        summary = GenerationSummary()
        summary.total_records = len(records)
        if not records:
            return summary

        total = len(records)

        def _render_one(rec: SourceRecord) -> RenderResult:
            match = match_results.get(rec.record_id)
            return BatchGenerator.generate_single_card(
                template=template,
                record=rec,
                match_result=match,
                column_mappings=column_mappings,
                settings=settings,
                target_dir=staging_dir,
            )

        def _consume(index: int, res: RenderResult) -> None:
            """Book a rendered card and report it."""
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

            if record_callback:
                record_callback(res)
            if progress_callback:
                progress_callback(index + 1, total, records[index].pin, status_msg)

        def _cancelled() -> bool:
            return bool(cancel_check and cancel_check())

        workers = BatchGenerator.resolve_workers(total, workers)

        if workers > 1 and total >= PARALLEL_RENDER_THRESHOLD:
            # Render in chunks so the memory stays bounded and a cancel is
            # honoured quickly.
            chunk_size = max(workers * 2, 8)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for start in range(0, total, chunk_size):
                    if _cancelled():
                        summary.cancelled = True
                        logger.info(
                            "Batch generation cancelled by user at record %d/%d",
                            start,
                            total,
                        )
                        break

                    chunk = records[start:start + chunk_size]
                    for offset, res in enumerate(pool.map(_render_one, chunk)):
                        _consume(start + offset, res)
                        if _cancelled():
                            summary.cancelled = True
                            break

                    if summary.cancelled:
                        break
        else:
            for index, rec in enumerate(records):
                if _cancelled():
                    summary.cancelled = True
                    logger.info(
                        "Batch generation cancelled by user at record %d/%d",
                        index,
                        total,
                    )
                    break
                _consume(index, _render_one(rec))

        logger.info(
            "Batch generation completed: %d success, %d skipped, %d failed out of %d",
            summary.completed_count,
            summary.skipped_count,
            summary.failed_count,
            summary.total_records,
        )
        return summary
