"""Template validation against schema and security constraints."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple
from pydantic import ValidationError

from id_card_generator.core.exceptions import TemplateValidationError
from id_card_generator.core.models import TemplateDefinition

logger = logging.getLogger(__name__)

ALLOWED_ELEMENT_TYPES = {
    "dynamic_text",
    "static_text",
    "photo",
    "pin_field",
    "rect",
    "round_rect",
    "line",
    "image",
}


class TemplateFinalizationReport:
    """Report produced when validating a template prior to finalization."""

    def __init__(self) -> None:
        self.is_valid: bool = True
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def add_error(self, msg: str) -> None:
        self.is_valid = False
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


class TemplateValidator:
    """Validates template schema, dimensions, element properties, and asset safety."""

    @staticmethod
    def validate_for_finalization(tmpl: TemplateDefinition) -> TemplateFinalizationReport:
        """Validate template design before finalization and moving to mapping."""
        report = TemplateFinalizationReport()

        # 1. Document Dimensions & DPI
        if tmpl.width_px < 100 or tmpl.height_px < 100:
            report.add_error(f"Card dimensions too small: {tmpl.width_px}×{tmpl.height_px} px (minimum 100×100 px).")
        if tmpl.width_px > 10000 or tmpl.height_px > 10000:
            report.add_error(f"Card dimensions excessively large: {tmpl.width_px}×{tmpl.height_px} px.")
        if tmpl.dpi < 72 or tmpl.dpi > 2400:
            report.add_warning(f"Unusual DPI resolution: {tmpl.dpi} (standard is 300 DPI).")

        # 2. Background image asset check
        if tmpl.background_image_path:
            p = Path(tmpl.background_image_path)
            if ".." in p.parts:
                report.add_error(f"Unsafe background image path: {tmpl.background_image_path}")
            elif not p.exists():
                report.add_warning(f"Background image file not found: {p.name}")

        # 3. Validate elements
        seen_ids = set()
        for el in tmpl.elements:
            if not el.id:
                report.add_error(f"Element '{el.name}' is missing an internal ID.")
            elif el.id in seen_ids:
                report.add_error(f"Duplicate element ID: '{el.id}'.")
            seen_ids.add(el.id)

            if el.type not in ALLOWED_ELEMENT_TYPES:
                report.add_error(f"Element '{el.name}' has unsupported type '{el.type}'.")

            if el.width <= 0 or el.height <= 0:
                report.add_error(f"Element '{el.name}' has non-positive dimensions ({el.width}×{el.height}).")

            # Geometry boundary warning
            if el.x >= tmpl.width_px or el.y >= tmpl.height_px or (el.x + el.width) <= 0 or (el.y + el.height) <= 0:
                report.add_warning(f"Element '{el.name}' is positioned completely outside the card canvas.")

            # Styling bounds
            if el.style.opacity < 0.0 or el.style.opacity > 1.0:
                report.add_warning(f"Element '{el.name}' has invalid opacity ({el.style.opacity}).")
            if el.style.border_width < 0:
                report.add_error(f"Element '{el.name}' has negative border width.")
            if el.style.font_size <= 0:
                report.add_error(f"Text element '{el.name}' has non-positive font size.")

            # Static image file check
            if el.type == "image" and el.static_content:
                ip = Path(el.static_content)
                if ".." in ip.parts:
                    report.add_error(f"Unsafe image asset path in element '{el.name}': {el.static_content}")
                elif not ip.exists():
                    report.add_warning(f"Static image file for element '{el.name}' not found: {ip.name}")

            # Static text overflow detection
            if el.type == "static_text" and el.static_content:
                approx_char_w = el.style.font_size * 0.6
                text_len_px = len(el.static_content) * approx_char_w
                if not el.style.wrap and text_len_px > el.width * 1.5:
                    report.add_warning(f"Static text '{el.name}' may overflow its bounding box ({len(el.static_content)} chars).")

        return report

    @staticmethod
    def validate_dict(data: Dict[str, Any]) -> TemplateDefinition:
        """Validate a dictionary representing template definition."""
        try:
            tmpl = TemplateDefinition.model_validate(data)
        except ValidationError as e:
            logger.error("Template validation failed: %s", e)
            raise TemplateValidationError(f"Invalid template structure: {e}") from e

        # Validate card dimensions
        if tmpl.width_px < 100 or tmpl.height_px < 100:
            raise TemplateValidationError(
                f"Card dimensions too small: {tmpl.width_px}x{tmpl.height_px} (minimum 100x100)"
            )
        if tmpl.width_px > 10000 or tmpl.height_px > 10000:
            raise TemplateValidationError(
                f"Card dimensions excessively large: {tmpl.width_px}x{tmpl.height_px}"
            )

        # Validate elements
        seen_ids = set()
        for el in tmpl.elements:
            if not el.id:
                raise TemplateValidationError("Canvas element missing ID")
            if el.id in seen_ids:
                raise TemplateValidationError(f"Duplicate element ID: '{el.id}'")
            seen_ids.add(el.id)

            if el.type not in ALLOWED_ELEMENT_TYPES:
                raise TemplateValidationError(f"Unsupported element type: '{el.type}'")

            if el.width <= 0 or el.height <= 0:
                raise TemplateValidationError(
                    f"Element '{el.name}' ({el.id}) has invalid dimensions: {el.width}x{el.height}"
                )

        # Validate assets
        if tmpl.background_image_path:
            TemplateValidator._validate_asset_path(tmpl.background_image_path)

        for el in tmpl.elements:
            if el.type == "image" and el.static_content:
                TemplateValidator._validate_asset_path(el.static_content)

        return tmpl

    @staticmethod
    def validate_file(file_path: Path) -> TemplateDefinition:
        """Read and validate a template JSON file."""
        if not file_path.exists():
            raise TemplateValidationError(f"Template file not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise TemplateValidationError(f"Template is not valid JSON: {e}") from e

        return TemplateValidator.validate_dict(data)

    @staticmethod
    def _validate_asset_path(path_str: str) -> None:
        """Verify that an asset path is safe."""
        p = Path(path_str)
        # Check against path traversal
        if ".." in p.parts:
            raise TemplateValidationError(f"Unsafe asset path with parent traversal: {path_str}")
