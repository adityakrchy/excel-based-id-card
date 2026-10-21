"""Project persistence: save, load, and relink missing external assets, with workspace support."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from id_card_generator.core.constants import MatchStatus
from id_card_generator.core.exceptions import ProjectError
from id_card_generator.core.models import PhotoMatchResult, ProjectConfiguration

logger = logging.getLogger(__name__)

# Photographs above this count are copied with a thread pool.
COPY_PARALLEL_THRESHOLD = 200

# Upper bound of copy workers.
MAX_COPY_WORKERS = 8


class ProjectManager:
    """Handles saving, loading, validating, workspace operations, and relinking project files."""

    @staticmethod
    def create_workspace(project_name: str, workspace_path: Path) -> ProjectConfiguration:
        """Initialize a new project workspace directory with standard subdirectories and project.json."""
        try:
            workspace_path = Path(workspace_path).resolve()
            workspace_path.mkdir(parents=True, exist_ok=True)

            # The folders of the workspace: the imported sheet, the matched
            # photographs and the cards that are written.
            data_dir = workspace_path / "data"
            data_dir.mkdir(parents=True, exist_ok=True)

            photos_dir = workspace_path / "photos"
            photos_dir.mkdir(parents=True, exist_ok=True)

            export_dir = workspace_path / "export"
            export_dir.mkdir(parents=True, exist_ok=True)

            config = ProjectConfiguration(
                project_name=project_name.strip() or "Untitled Project",
                workspace_dir=str(workspace_path),
                last_export_dir=str(export_dir),
            )

            project_file = workspace_path / "project.json"
            ProjectManager.save_project(config, project_file)
            logger.info("Workspace successfully created at %s", workspace_path)
            return config
        except Exception as e:
            logger.error("Failed to create workspace at %s: %s", workspace_path, e)
            raise ProjectError(f"Could not create workspace: {e}") from e

    @staticmethod
    def copy_excel_to_workspace(config: ProjectConfiguration, source_excel: Path) -> Path:
        """Copy imported spreadsheet into workspace data/ directory for self-contained reuse."""
        source_path = Path(source_excel).resolve()
        if not source_path.exists():
            raise ProjectError(f"Source spreadsheet not found: {source_path}")

        if not config.workspace_dir:
            return source_path

        data_dir = config.data_dir
        if not data_dir:
            return source_path

        data_dir.mkdir(parents=True, exist_ok=True)
        target_path = (data_dir / source_path.name).resolve()

        if source_path != target_path:
            try:
                shutil.copy2(source_path, target_path)
                logger.info("Copied spreadsheet from %s to workspace data %s", source_path, target_path)
            except shutil.SameFileError:
                pass
            except Exception as e:
                logger.error("Failed to copy spreadsheet to workspace: %s", e)
                raise ProjectError(f"Could not copy spreadsheet to workspace: {e}") from e

        config.excel_file_path = str(target_path)
        if config.project_file_path and config.project_file_path.exists():
            try:
                ProjectManager.save_project(config, config.project_file_path)
            except Exception as e:
                logger.warning("Could not auto-save project after copying excel: %s", e)

        return target_path

    @staticmethod
    def copy_single_photo_to_workspace(config: ProjectConfiguration, source_photo: Path, pin: str = "") -> Path:
        """Copy a single photograph into workspace photos/ folder."""
        source_path = Path(source_photo).resolve()
        if not source_path.exists() or not config.photos_dir:
            return source_path

        photos_dir = config.photos_dir
        photos_dir.mkdir(parents=True, exist_ok=True)
        target_path = (photos_dir / source_path.name).resolve()

        if target_path.exists():
            try:
                if not source_path.samefile(target_path):
                    target_path = (photos_dir / f"{source_path.stem}_{pin or 'override'}{source_path.suffix}").resolve()
            except OSError:
                pass

        if source_path != target_path:
            try:
                shutil.copy2(source_path, target_path)
                logger.info("Copied photo %s to workspace photos %s", source_path.name, target_path)
            except shutil.SameFileError:
                pass
            except Exception as e:
                logger.warning("Failed to copy photo to workspace: %s", e)
                return source_path

        return target_path

    @staticmethod
    def copy_matched_photos_to_workspace(
        config: ProjectConfiguration,
        match_results: Dict[str, PhotoMatchResult],
        workers: int = 0,
    ) -> Tuple[Dict[str, PhotoMatchResult], int]:
        """Copy ONLY matched (and manually overridden) photographs into the workspace photos/ directory.

        Leaves unmatched photos untouched and updates match_results with the
        workspace paths.  The copies run on a thread pool - copying thousands
        of photographs is I/O bound and used to freeze the interface.
        """
        if not config.photos_dir:
            return match_results, 0

        photos_dir = config.photos_dir
        photos_dir.mkdir(parents=True, exist_ok=True)

        def _is_matched(result: PhotoMatchResult) -> bool:
            return result.status in (MatchStatus.MATCHED, MatchStatus.OVERRIDDEN) or (
                hasattr(result.status, "value")
                and result.status.value in ("matched", "overridden")
            )

        candidates = [
            (record_id, result)
            for record_id, result in match_results.items()
            if _is_matched(result) and result.photo_path
        ]
        if not candidates:
            return match_results, 0

        def _copy_one(item) -> Optional[Path]:
            """Copy one photograph into the workspace and return the new path."""
            record_id, result = item
            try:
                src = Path(result.photo_path).resolve()
                if not src.exists():
                    return None

                target = (photos_dir / src.name).resolve()
                if target.exists():
                    try:
                        if not src.samefile(target):
                            target = (
                                photos_dir
                                / f"{src.stem}_{result.pin or record_id}{src.suffix}"
                            ).resolve()
                    except OSError:
                        pass

                if src != target:
                    try:
                        shutil.copy2(src, target)
                    except shutil.SameFileError:
                        pass
                    except Exception as e:
                        logger.warning("Failed to copy matched photo %s: %s", src, e)
                        return None
                return target
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("Failed to copy matched photo: %s", e)
                return None

        if workers <= 0:
            workers = min(MAX_COPY_WORKERS, (len(candidates) // COPY_PARALLEL_THRESHOLD) + 1)
        else:
            workers = max(1, min(workers, MAX_COPY_WORKERS))

        copied_count = 0
        if workers > 1 and len(candidates) >= COPY_PARALLEL_THRESHOLD:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                targets = list(pool.map(_copy_one, candidates))
        else:
            targets = [_copy_one(item) for item in candidates]

        for (record_id, result), target in zip(candidates, targets):
            if target is None:
                continue
            result.photo_path = str(target)
            result.matched_filename = target.name
            copied_count += 1

        if config.project_file_path and config.project_file_path.exists():
            try:
                ProjectManager.save_project(config, config.project_file_path)
            except Exception as e:
                logger.warning("Could not auto-save project after copying matched photos: %s", e)

        return match_results, copied_count

    @staticmethod
    def save_project(config: ProjectConfiguration, file_path: Path) -> None:
        """Save project configuration to a JSON file."""
        try:
            file_path = Path(file_path).resolve()
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
        """Load and parse project configuration from a JSON file (or workspace directory)."""
        file_path = Path(file_path).resolve()
        if file_path.is_dir():
            candidate = file_path / "project.json"
            if candidate.exists():
                file_path = candidate
            else:
                raise ProjectError(f"No project.json found in workspace directory: {file_path}")

        if not file_path.exists():
            raise ProjectError(f"Project file does not exist: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            config = ProjectConfiguration.model_validate(data)

            # Auto-assign or heal workspace directory if legacy project file is in a workspace folder
            if file_path.name == "project.json" or (file_path.parent / "data").is_dir():
                if not config.workspace_dir or not Path(config.workspace_dir).exists():
                    config.workspace_dir = str(file_path.parent.resolve())

            # Heal relative/moved paths within workspace
            if config.workspace_dir:
                ws = Path(config.workspace_dir)
                if config.excel_file_path and not Path(config.excel_file_path).exists():
                    candidate_excel = ws / "data" / Path(config.excel_file_path).name
                    if candidate_excel.exists():
                        config.excel_file_path = str(candidate_excel)

                if config.photo_dir_path and not Path(config.photo_dir_path).exists():
                    candidate_photos = ws / "photos"
                    if candidate_photos.exists():
                        config.photo_dir_path = str(candidate_photos)

                if not config.last_export_dir or not Path(config.last_export_dir).exists():
                    # The folder was renamed from "exports" to "export".
                    for folder in ("export", "exports"):
                        candidate = ws / folder
                        if candidate.exists():
                            config.last_export_dir = str(candidate)
                            break

            logger.info("Project successfully loaded from %s", file_path)
            return config
        except Exception as e:
            logger.error("Failed to load project from %s: %s", file_path, e)
            raise ProjectError(f"Could not load project: {e}") from e

    @staticmethod
    def check_missing_references(config: ProjectConfiguration) -> List[Tuple[str, str]]:
        """Return list of (key, missing_path) for external files referenced in the project."""
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
        """Update file references in project configuration."""
        if "excel_file" in replacements:
            config.excel_file_path = replacements["excel_file"]
        if "photo_dir" in replacements:
            config.photo_dir_path = replacements["photo_dir"]
        if "background_image" in replacements and config.template:
            config.template.background_image_path = replacements["background_image"]
        return config

