"""Resource path helper and directory manager.

Works seamlessly in both local development environments and PyInstaller-packaged executables.
"""

import os
import sys
from pathlib import Path
from platformdirs import user_data_dir, user_log_dir, user_cache_dir
from id_card_generator.core.constants import APP_NAME, APP_ORG


def get_base_dir() -> Path:
    """Return the base directory of the running application.
    
    If packaged with PyInstaller, returns sys._MEIPASS.
    Otherwise returns the root of the source package.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    # When running from source: src/id_card_generator/resources -> parent is id_card_generator
    return Path(__file__).resolve().parent.parent


def get_resource_path(*relative_parts: str) -> Path:
    """Resolve an application resource path."""
    p = get_base_dir() / "resources" / Path(*relative_parts)
    if not p.exists():
        alt = get_base_dir() / "id_card_generator" / "resources" / Path(*relative_parts)
        if alt.exists():
            return alt
    return p


def get_builtin_templates_dir() -> Path:
    """Return the directory containing built-in template JSON definitions."""
    p = get_base_dir() / "templates" / "builtins"
    if not p.exists():
        alt = get_base_dir() / "id_card_generator" / "templates" / "builtins"
        if alt.exists():
            return alt
    return p


def get_app_data_dir() -> Path:
    """Return standard user data directory for the application, creating it if needed."""
    path = Path(user_data_dir(appname=APP_NAME, appauthor=APP_ORG))
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_log_dir() -> Path:
    """Return directory for rotating log files, creating it if needed."""
    path = Path(user_log_dir(appname=APP_NAME, appauthor=APP_ORG))
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_user_templates_dir() -> Path:
    """Return user custom templates directory, creating it if needed."""
    path = get_app_data_dir() / "templates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_user_template_dirs() -> list[Path]:
    """Return all directories where user custom templates may be located."""
    dirs = [get_user_templates_dir()]
    try:
        cf_dir = Path(user_data_dir(appname="CardForge")) / "templates"
        if cf_dir.exists() and cf_dir not in dirs:
            dirs.append(cf_dir)
    except Exception:
        pass
    return dirs


def get_projects_dir() -> Path:
    """Return default directory for saved projects."""
    path = get_app_data_dir() / "projects"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_staging_dir() -> Path:
    """Return temporary staging directory for card generation before final export."""
    path = get_app_data_dir() / "staging"
    path.mkdir(parents=True, exist_ok=True)
    return path
