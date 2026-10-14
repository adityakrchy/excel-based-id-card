"""Field mapping manager between spreadsheet columns and canvas elements."""

import logging
from typing import Dict, List, Optional
from id_card_generator.core.models import CanvasElement, SourceRecord, TemplateDefinition

logger = logging.getLogger(__name__)


class MappingValidationReport:
    """Report on mapping completeness and integrity."""

    def __init__(self) -> None:
        self.is_valid: bool = True
        self.unmapped_elements: List[CanvasElement] = []
        self.unmapped_columns: List[str] = []
        self.photo_element_present: bool = False
        self.pin_element_present: bool = False
        self.errors: List[str] = []
        self.warnings: List[str] = []


class MappingManager:
    """Coordinates and validates bindings between imported dataset columns and canvas elements."""

    def __init__(self) -> None:
        self.mappings: Dict[str, str] = {}  # element_id -> column_name

    def auto_map(self, template: TemplateDefinition, available_columns: List[str]) -> Dict[str, str]:
        """Automatically suggest mappings based on element names, bindings, and column names."""
        col_lower = {c.lower(): c for c in available_columns}

        for el in template.elements:
            if el.type in ("dynamic_text", "pin_field"):
                # Check binding attribute first
                if el.binding and el.binding.lower() in col_lower:
                    self.mappings[el.id] = col_lower[el.binding.lower()]
                    continue

                # Check element name
                if el.name.lower() in col_lower:
                    self.mappings[el.id] = col_lower[el.name.lower()]
                    continue

                # Fuzzy keyword checks
                for col_name in available_columns:
                    cl = col_name.lower()
                    nl = el.name.lower()
                    if ("name" in cl and "name" in nl) or ("pin" in cl and "pin" in nl) or ("designation" in cl and "designation" in nl):
                        self.mappings[el.id] = col_name
                        break

            elif el.type == "photo":
                self.mappings[el.id] = "photo"

        logger.info("Auto-mapped %d elements to dataset columns.", len(self.mappings))
        return self.mappings

    def set_mapping(self, element_id: str, column_name: str) -> None:
        self.mappings[element_id] = column_name

    def remove_mapping(self, element_id: str) -> None:
        self.mappings.pop(element_id, None)

    def validate_mappings(
        self,
        template: TemplateDefinition,
        available_columns: List[str],
    ) -> MappingValidationReport:
        """Verify that all required elements are properly mapped."""
        report = MappingValidationReport()

        for el in template.elements:
            if el.type == "photo":
                report.photo_element_present = True
            if el.type == "pin_field" or (el.binding and el.binding.lower() in ("pin", "pin number")):
                report.pin_element_present = True

            if el.type in ("dynamic_text", "pin_field"):
                mapped_col = self.mappings.get(el.id) or el.binding
                if not mapped_col or (mapped_col not in available_columns and mapped_col != "photo"):
                    report.unmapped_elements.append(el)
                    report.warnings.append(f"Element '{el.name}' has no active spreadsheet column mapping.")

        if not report.pin_element_present:
            report.warnings.append("Template does not contain a dedicated PIN Number field.")

        if not report.photo_element_present:
            report.warnings.append("Template does not contain a profile photograph element.")

        return report
