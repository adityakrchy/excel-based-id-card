"""Unit tests for template validation, loading, and management."""

import json
from pathlib import Path
import pytest
from id_card_generator.core.exceptions import TemplateValidationError
from id_card_generator.core.models import CanvasElement, TemplateDefinition
from id_card_generator.templates.template_manager import TemplateManager
from id_card_generator.templates.template_validator import TemplateValidator


def test_builtin_templates_load_and_validate():
    mgr = TemplateManager()
    templates = mgr.list_templates()
    assert len(templates) >= 3

    ids = [t.id for t in templates]
    assert "builtin-classic-portrait" in ids
    assert "builtin-modern-corporate" in ids
    assert "builtin-office-id-card" in ids

    # Check classic portrait
    classic = mgr.get_template("builtin-classic-portrait")
    assert classic is not None
    assert classic.width_px == 638
    assert classic.height_px == 1012
    assert len(classic.elements) > 5


def test_template_validation_errors():
    # Dimension too small
    with pytest.raises(TemplateValidationError):
        TemplateValidator.validate_dict({
            "name": "Tiny Card",
            "width_px": 50,
            "height_px": 50,
        })

    # Unsupported element type
    with pytest.raises(TemplateValidationError):
        TemplateValidator.validate_dict({
            "name": "Bad Element Card",
            "width_px": 600,
            "height_px": 1000,
            "elements": [
                {"id": "bad1", "name": "Hack", "type": "malicious_script", "width": 100, "height": 100}
            ]
        })

    # Element dimension <= 0
    with pytest.raises(TemplateValidationError):
        TemplateValidator.validate_dict({
            "name": "Zero Width",
            "width_px": 600,
            "height_px": 1000,
            "elements": [
                {"id": "el1", "name": "Item", "type": "rect", "width": 0, "height": 100}
            ]
        })


def test_duplicate_and_export_template(temp_dir: Path):
    mgr = TemplateManager()
    dup = mgr.duplicate_template("builtin-classic-portrait", "My Custom Badge")
    assert dup.name == "My Custom Badge"
    assert dup.id != "builtin-classic-portrait"
    assert not mgr.is_builtin(dup.id)

    # Export
    export_path = temp_dir / "exported_template.json"
    mgr.export_template(dup.id, export_path)
    assert export_path.exists()

    # Re-import
    imported = mgr.import_template(export_path)
    assert imported.name == "My Custom Badge"

    # Cleanup user template
    assert mgr.delete_user_template(dup.id) is True
    assert mgr.delete_user_template(imported.id) is True
