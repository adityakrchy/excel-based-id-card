"""Template manager for discovering built-ins, saving custom templates, and exporting/importing."""

import json
import logging
import shutil
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from id_card_generator.core.exceptions import TemplateValidationError
from id_card_generator.core.models import TemplateDefinition
from id_card_generator.resources.resource_loader import (
    get_builtin_templates_dir,
    get_user_template_dirs,
    get_user_templates_dir,
)
from id_card_generator.templates.template_validator import TemplateValidator

logger = logging.getLogger(__name__)


class TemplateManager:
    """Manages built-in and user-defined ID card templates."""

    def __init__(self) -> None:
        self._templates: Dict[str, TemplateDefinition] = {}
        self._template_paths: Dict[str, Path] = {}
        self._builtin_ids: set[str] = set()
        self.reload()

    def reload(self) -> None:
        """Scan built-in and user template directories and populate template cache."""
        self._templates.clear()
        self._template_paths.clear()
        self._builtin_ids.clear()

        # 1. Load built-ins
        builtins_dir = get_builtin_templates_dir()
        if builtins_dir.exists():
            for f in builtins_dir.glob("*.json"):
                try:
                    tmpl = TemplateValidator.validate_file(f)
                    self._templates[tmpl.id] = tmpl
                    self._template_paths[tmpl.id] = f
                    self._builtin_ids.add(tmpl.id)
                    logger.debug("Loaded built-in template: %s (%s)", tmpl.name, tmpl.id)
                except Exception as e:
                    logger.warning("Failed to load built-in template %s: %s", f.name, e)

        # 2. Load user templates from all user template directories
        for user_dir in get_user_template_dirs():
            if user_dir.exists():
                for f in user_dir.glob("*.json"):
                    try:
                        tmpl = TemplateValidator.validate_file(f)
                        self._templates[tmpl.id] = tmpl
                        self._template_paths[tmpl.id] = f
                        logger.debug("Loaded user template: %s (%s)", tmpl.name, tmpl.id)
                    except Exception as e:
                        logger.warning("Failed to load user template %s: %s", f.name, e)

        logger.info(
            "TemplateManager initialized with %d templates (%d built-in).",
            len(self._templates),
            len(self._builtin_ids),
        )

    def list_templates(self) -> List[TemplateDefinition]:
        """Return list of all available templates."""
        return list(self._templates.values())

    def get_template(self, template_id: str) -> Optional[TemplateDefinition]:
        """Get template by unique ID."""
        return self._templates.get(template_id)

    def get_template_file_path(self, template_id: str) -> Optional[Path]:
        """Return the on-disk file path for a template if available."""
        if template_id in self._template_paths:
            return self._template_paths[template_id]
        # Fallback check standard user directory
        user_path = get_user_templates_dir() / f"{template_id}.json"
        if user_path.exists():
            return user_path
        return None

    def is_builtin(self, template_id: str) -> bool:
        """Check if template is built-in."""
        return template_id in self._builtin_ids

    def save_user_template(self, template: TemplateDefinition) -> Path:
        """Save or update a user template in the user templates directory."""
        # Ensure it has a unique non-builtin ID
        if self.is_builtin(template.id):
            template.id = str(uuid.uuid4())

        user_dir = get_user_templates_dir()
        file_path = user_dir / f"{template.id}.json"

        # Validate before writing
        validated = TemplateValidator.validate_dict(template.model_dump(mode="json"))

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(validated.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

        self._templates[validated.id] = validated
        self._template_paths[validated.id] = file_path
        logger.info("Saved user template '%s' to %s", validated.name, file_path)
        return file_path

    def delete_user_template(self, template_id: str) -> bool:
        """Delete a user template. Built-in templates cannot be deleted."""
        if self.is_builtin(template_id):
            raise TemplateValidationError("Cannot delete a built-in template.")

        # Check cached path or user dirs
        file_path = self.get_template_file_path(template_id)
        if file_path and file_path.exists():
            try:
                file_path.unlink()
            except Exception as e:
                logger.error("Failed to delete file %s: %s", file_path, e)
                raise

        # Check standard user dir just in case
        std_path = get_user_templates_dir() / f"{template_id}.json"
        if std_path.exists():
            try:
                std_path.unlink()
            except Exception as e:
                logger.error("Failed to delete file %s: %s", std_path, e)

        self._template_paths.pop(template_id, None)

        if template_id in self._templates:
            del self._templates[template_id]
            logger.info("Deleted user template: %s", template_id)
            return True
        return False

    def delete_user_templates_batch(self, template_ids: List[str]) -> int:
        """Delete multiple user templates in batch. Built-in templates are skipped."""
        deleted_count = 0
        for tid in template_ids:
            if self.is_builtin(tid):
                continue
            try:
                if self.delete_user_template(tid):
                    deleted_count += 1
            except Exception as e:
                logger.warning("Failed to delete user template %s in batch: %s", tid, e)
        return deleted_count

    def duplicate_template(self, template_id: str, new_name: str) -> TemplateDefinition:
        """Duplicate an existing template with a new ID and name."""
        source = self.get_template(template_id)
        if not source:
            raise TemplateValidationError(f"Source template '{template_id}' not found.")

        data = source.model_dump(mode="json")
        data["id"] = str(uuid.uuid4())
        data["name"] = new_name
        data["description"] = f"Copy of {source.name}"

        # Assign new unique IDs to all elements
        for el in data.get("elements", []):
            el["id"] = str(uuid.uuid4())

        new_tmpl = TemplateDefinition.model_validate(data)
        self.save_user_template(new_tmpl)
        return new_tmpl

    def import_template(self, file_path: Path) -> TemplateDefinition:
        """Import an external template JSON file into user templates."""
        tmpl = TemplateValidator.validate_file(file_path)
        # Assign new ID to prevent colliding with existing or built-in IDs
        tmpl.id = str(uuid.uuid4())
        self.save_user_template(tmpl)
        return tmpl

    def export_template(self, template_id: str, destination: Path) -> None:
        """Export a template definition to a file."""
        tmpl = self.get_template(template_id)
        if not tmpl:
            raise TemplateValidationError(f"Template '{template_id}' not found.")

        destination.parent.mkdir(parents=True, exist_ok=True)
        with open(destination, "w", encoding="utf-8") as f:
            json.dump(tmpl.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
        logger.info("Exported template %s to %s", template_id, destination)
