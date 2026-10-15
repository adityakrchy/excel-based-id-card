#!/usr/bin/env python3
"""
Automated Package Version Increment Utility.

Synchronizes and increments the application version across:
  - pyproject.toml
  - src/id_card_generator/__init__.py
  - src/id_card_generator/core/constants.py
  - packaging/installer.iss

Usage:
  python scripts/increment_version.py [--mode {patch,minor,major,build-number,set}]
                                      [--build-number N]
                                      [--set VERSION]
                                      [--dry-run]
                                      [--github-output]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Tuple


def find_repo_root() -> Path:
    """Locate the git repository root directory."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").is_file():
            return current
        current = current.parent
    return Path.cwd().resolve()


def parse_semantic_version(version_str: str) -> Tuple[int, int, int, str]:
    """
    Parse a semantic version string into (major, minor, patch, prerelease).
    Supports formats like 1.0.0, 1.0.0.dev1, 1.0.0-rc1, etc.
    """
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?(.*)$", version_str.strip())
    if not match:
        raise ValueError(f"Invalid semantic version string: '{version_str}'")
    
    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3)) if match.group(3) is not None else 0
    extra = match.group(4) or ""
    return major, minor, patch, extra


def get_current_version(repo_root: Path) -> str:
    """Read the current version from pyproject.toml."""
    pyproject_path = repo_root / "pyproject.toml"
    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

    content = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    if not match:
        raise ValueError("Could not find 'version = \"...\"' in pyproject.toml")
    return match.group(1)


def compute_new_version(
    current_version: str,
    mode: str = "patch",
    build_number: int | None = None,
    explicit_version: str | None = None,
) -> str:
    """Compute the next version string based on current version and mode."""
    if explicit_version:
        # Validate format
        parse_semantic_version(explicit_version)
        return explicit_version.strip()

    major, minor, patch, extra = parse_semantic_version(current_version)

    if mode == "major":
        return f"{major + 1}.0.0"
    elif mode == "minor":
        return f"{major}.{minor + 1}.0"
    elif mode == "patch":
        return f"{major}.{minor}.{patch + 1}"
    elif mode == "build-number":
        if build_number is None:
            raise ValueError("Mode 'build-number' requires --build-number N")
        return f"{major}.{minor}.{build_number}"
    else:
        raise ValueError(f"Unknown version increment mode: {mode}")


def update_file_pattern(file_path: Path, pattern: str, replacement: str, dry_run: bool = False) -> bool:
    """Replace content matching pattern in file. Returns True if modified."""
    if not file_path.exists():
        print(f"Warning: File not found: {file_path}", file=sys.stderr)
        return False

    content = file_path.read_text(encoding="utf-8")
    new_content, count = re.subn(pattern, replacement, content, count=1, flags=re.MULTILINE)
    
    if count == 0:
        print(f"Warning: Pattern '{pattern}' not found in {file_path}", file=sys.stderr)
        return False

    if not dry_run and content != new_content:
        file_path.write_text(new_content, encoding="utf-8")
    return True


def update_all_version_files(repo_root: Path, new_version: str, dry_run: bool = False) -> list[Path]:
    """Update version across pyproject.toml, __init__.py, constants.py, and installer.iss."""
    targets = [
        (
            repo_root / "pyproject.toml",
            r'^(version\s*=\s*)["\']([^"\']+)["\']',
            rf'\g<1>"{new_version}"',
        ),
        (
            repo_root / "src" / "id_card_generator" / "__init__.py",
            r'^(__version__\s*=\s*)["\']([^"\']+)["\']',
            rf'\g<1>"{new_version}"',
        ),
        (
            repo_root / "src" / "id_card_generator" / "core" / "constants.py",
            r'^(APP_VERSION\s*=\s*)["\']([^"\']+)["\']',
            rf'\g<1>"{new_version}"',
        ),
        (
            repo_root / "packaging" / "installer.iss",
            r'^(#define\s+MyAppVersion\s+)["\']([^"\']+)["\']',
            rf'\g<1>"{new_version}"',
        ),
    ]

    updated = []
    for path, pattern, replacement in targets:
        if update_file_pattern(path, pattern, replacement, dry_run=dry_run):
            updated.append(path)
    return updated


def export_github_outputs(old_version: str, new_version: str) -> None:
    """Write step outputs to $GITHUB_OUTPUT and $GITHUB_ENV if in GitHub Actions."""
    gh_output_path = os.getenv("GITHUB_OUTPUT")
    if gh_output_path and os.path.exists(gh_output_path):
        with open(gh_output_path, "a", encoding="utf-8") as f:
            f.write(f"version={new_version}\n")
            f.write(f"new_version={new_version}\n")
            f.write(f"old_version={old_version}\n")

    gh_env_path = os.getenv("GITHUB_ENV")
    if gh_env_path and os.path.exists(gh_env_path):
        with open(gh_env_path, "a", encoding="utf-8") as f:
            f.write(f"PACKAGE_VERSION={new_version}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Increment and synchronize application package version.")
    parser.add_argument(
        "--mode",
        choices=["patch", "minor", "major", "build-number", "set"],
        default="patch",
        help="Increment strategy (default: patch)",
    )
    parser.add_argument(
        "--build-number",
        type=int,
        default=None,
        help="Build number to use (e.g. GITHUB_RUN_NUMBER) when mode is build-number",
    )
    parser.add_argument(
        "--set",
        dest="explicit_version",
        type=str,
        default=None,
        help="Explicit version string to set directly (e.g. 1.2.3)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying files",
    )
    parser.add_argument(
        "--github-output",
        action="store_true",
        help="Write outputs to GITHUB_OUTPUT and GITHUB_ENV if available",
    )

    args = parser.parse_args()

    repo_root = find_repo_root()
    old_version = get_current_version(repo_root)

    mode = "set" if args.explicit_version else args.mode
    new_version = compute_new_version(
        old_version,
        mode=mode,
        build_number=args.build_number,
        explicit_version=args.explicit_version,
    )

    prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"{prefix}Incrementing package version: {old_version} -> {new_version}")

    updated_files = update_all_version_files(repo_root, new_version, dry_run=args.dry_run)
    for f in updated_files:
        print(f"  - Synchronized: {f.relative_to(repo_root)}")

    if args.github_output or os.getenv("GITHUB_ACTIONS") == "true":
        export_github_outputs(old_version, new_version)

    return 0


if __name__ == "__main__":
    sys.exit(main())
