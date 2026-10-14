"""Project persistence: save, load, and relink missing external assets."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from id_card_generator.core.exceptions import ProjectError
from id_card_generator.core.models import ProjectConfiguration

logger = logging.getLogger(__name__)


class ProjectManager:
    """Handles saving, loading, validating, and relinking project files."""

    @staticmethod
    def save_project(config: ProjectConfiguration, file_path: Path) -> None:
        """Save project configuration to a JSON file."""
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            data = config.model_dump(mode="json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info("Project successfully saved to %s", file_path)
        except Exception as e:
            logger.error("Failed to save project to %s: %s", file_path, e)
            raise ProjectError(f"Could not save project: {e}") from e

    @staticmethod
    def load_project(file_path: Path) -> ProjectConfiguration:
        """Load and parse project configuration from a JSON file."""
        if not file_path.exists():
            raise ProjectError(f"Project file does not exist: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            config = ProjectConfiguration.model_validate(data)
            logger.info("Project successfully loaded from %s", file_path)
            return config
        except Exception as e:
            logger.error("Failed to load project from %s: %s", file_path, e)
            raise ProjectError(f"Could not load project: {e}") from e

    @staticmethod
    def check_missing_references(config: ProjectConfiguration) -> List[Tuple[str, str]]:
        """Return list of (key, missing_path) for external files referenced in the project.
        
        Keys: 'excel_file', 'photo_dir', 'background_image'
        """
        missing = []

        if config.excel_file_path:
            p = Path(config.excel_file_path)
            if not p.exists():
                missing.append(("excel_file", config.excel_file_path))

        if config.photo_dir_path:
            p = Path(config.photo_dir_path)
            if not p.exists() or not p.is_dir():
                missing.append(("photo_dir", config.photo_dir_path))

        if config.template and config.template.background_image_path:
            p = Path(config.template.background_image_path)
            if not p.exists():
                missing.append(("background_image", config.template.background_image_path))

        return missing

    @staticmethod
    def relink_references(config: ProjectConfiguration, replacements: Dict[str, str]) -> ProjectConfiguration:
        """Update file references in project configuration.
        
        replacements mapping: key ('excel_file', 'photo_dir', 'background_image') -> new_path
        """
        if "excel_file" in replacements:
            config.excel_file_path = replacements["excel_file"]
        if "photo_dir" in replacements:
            config.photo_dir_path = replacements["photo_dir"]
        if "background_image" in replacements and config.template:
            config.template.background_image_path = replacements["background_image"]
        return config
