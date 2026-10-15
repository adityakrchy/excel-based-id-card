"""Unit tests for the automated package version increment utility."""

import os
from pathlib import Path
import pytest

from scripts.increment_version import (
    compute_new_version,
    export_github_outputs,
    find_repo_root,
    get_current_version,
    parse_semantic_version,
    update_all_version_files,
    update_file_pattern,
)


def test_parse_semantic_version():
    """Test parsing standard semantic versions and variations."""
    assert parse_semantic_version("1.0.0") == (1, 0, 0, "")
    assert parse_semantic_version("2.15.8") == (2, 15, 8, "")
    assert parse_semantic_version("0.1.0-alpha.1") == (0, 1, 0, "-alpha.1")
    assert parse_semantic_version("1.0") == (1, 0, 0, "")

    with pytest.raises(ValueError):
        parse_semantic_version("invalid_version")


def test_compute_new_version_modes():
    """Test version increment calculations for patch, minor, major, and build numbers."""
    # Default patch increment
    assert compute_new_version("1.0.0", mode="patch") == "1.0.1"
    assert compute_new_version("1.0.9", mode="patch") == "1.0.10"

    # Minor increment resets patch
    assert compute_new_version("1.0.5", mode="minor") == "1.1.0"

    # Major increment resets minor and patch
    assert compute_new_version("1.2.3", mode="major") == "2.0.0"

    # Build number mode
    assert compute_new_version("1.0.0", mode="build-number", build_number=45) == "1.0.45"

    # Explicit set
    assert compute_new_version("1.0.0", explicit_version="2.5.1") == "2.5.1"


def test_update_all_version_files_on_temp_dir(tmp_path: Path):
    """Test synchronizing version across all 4 target files in an isolated folder."""
    # Setup mock files
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "excel-id-card-generator"\nversion = "1.0.0"\ndescription = "Test"\n',
        encoding="utf-8",
    )

    src_init = tmp_path / "src" / "id_card_generator" / "__init__.py"
    src_init.parent.mkdir(parents=True, exist_ok=True)
    src_init.write_text('__version__ = "1.0.0"\n__app_name__ = "Test"\n', encoding="utf-8")

    constants = tmp_path / "src" / "id_card_generator" / "core" / "constants.py"
    constants.parent.mkdir(parents=True, exist_ok=True)
    constants.write_text('APP_NAME = "Test"\nAPP_VERSION = "1.0.0"\nDEFAULT_DPI = 300\n', encoding="utf-8")

    installer = tmp_path / "packaging" / "installer.iss"
    installer.parent.mkdir(parents=True, exist_ok=True)
    installer.write_text(
        '#define MyAppName "Test"\n#define MyAppVersion "1.0.0"\n#define MyAppPublisher "CardForge"\n',
        encoding="utf-8",
    )

    # Execute synchronization
    updated = update_all_version_files(tmp_path, "1.0.1", dry_run=False)
    assert len(updated) == 4

    # Verify updated contents
    assert 'version = "1.0.1"' in pyproject.read_text(encoding="utf-8")
    assert '__version__ = "1.0.1"' in src_init.read_text(encoding="utf-8")
    assert 'APP_VERSION = "1.0.1"' in constants.read_text(encoding="utf-8")
    assert '#define MyAppVersion "1.0.1"' in installer.read_text(encoding="utf-8")


def test_export_github_outputs(tmp_path: Path, monkeypatch):
    """Test exporting outputs to GITHUB_OUTPUT and GITHUB_ENV files."""
    gh_output = tmp_path / "github_output.txt"
    gh_env = tmp_path / "github_env.txt"
    gh_output.touch()
    gh_env.touch()

    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_output))
    monkeypatch.setenv("GITHUB_ENV", str(gh_env))

    export_github_outputs("1.0.0", "1.0.1")

    output_content = gh_output.read_text(encoding="utf-8")
    assert "version=1.0.1" in output_content
    assert "new_version=1.0.1" in output_content
    assert "old_version=1.0.0" in output_content

    env_content = gh_env.read_text(encoding="utf-8")
    assert "PACKAGE_VERSION=1.0.1" in env_content
