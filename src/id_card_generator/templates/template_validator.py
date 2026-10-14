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


class TemplateValidator:
    """Validates template schema, dimensions, element properties, and asset safety."""

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
