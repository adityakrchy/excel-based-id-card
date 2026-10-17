"""Tests for template cleanup, delete functionality, and UI integration."""

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from id_card_generator.core.exceptions import TemplateValidationError
from id_card_generator.core.models import TemplateDefinition
from id_card_generator.templates.template_manager import TemplateManager
from id_card_generator.ui.dialogs.template_cleanup_dialog import TemplateCleanupDialog
from id_card_generator.ui.editor_page import EditorPage
from id_card_generator.ui.template_page import TemplatePage


@pytest.fixture
def manager(temp_dir: Path, monkeypatch):
    """TemplateManager isolated to a temporary directory."""
    user_dir = temp_dir / "user_templates"
    user_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "id_card_generator.templates.template_manager.get_user_templates_dir",
        lambda: user_dir,
    )
    monkeypatch.setattr(
        "id_card_generator.templates.template_manager.get_user_template_dirs",
        lambda: [user_dir],
    )
    mgr = TemplateManager()
    return mgr


def test_template_manager_file_path_and_protection(manager: TemplateManager):
    """Built-ins should have paths and should be protected from deletion."""
    templates = manager.list_templates()
    builtin = next((t for t in templates if manager.is_builtin(t.id)), None)
    assert builtin is not None

    path = manager.get_template_file_path(builtin.id)
    assert path is not None
    assert path.exists()

    with pytest.raises(TemplateValidationError):
        manager.delete_user_template(builtin.id)


def test_template_manager_batch_delete(manager: TemplateManager):
    """Custom templates can be saved, located, and batch deleted."""
    # Create two custom templates
    tmpl1 = TemplateDefinition(
        id=str(uuid.uuid4()),
        name="Test Card Alpha",
        width_px=1016,
        height_px=638,
        dpi=300,
        elements=[],
    )
    tmpl2 = TemplateDefinition(
        id=str(uuid.uuid4()),
        name="Test Card Beta",
        width_px=1016,
        height_px=638,
        dpi=300,
        elements=[],
    )
    p1 = manager.save_user_template(tmpl1)
    p2 = manager.save_user_template(tmpl2)
    assert p1.exists()
    assert p2.exists()
    assert manager.get_template(tmpl1.id) is not None
    assert manager.get_template(tmpl2.id) is not None

    # Batch delete including one built-in ID
    builtin = next((t for t in manager.list_templates() if manager.is_builtin(t.id)), None)
    ids_to_delete = [tmpl1.id, tmpl2.id]
    if builtin:
        ids_to_delete.append(builtin.id)

    deleted_count = manager.delete_user_templates_batch(ids_to_delete)
    assert deleted_count == 2
    assert not p1.exists()
    assert not p2.exists()
    assert manager.get_template(tmpl1.id) is None
    assert manager.get_template(tmpl2.id) is None
    if builtin:
        assert manager.get_template(builtin.id) is not None


def test_template_cleanup_dialog_ui(qtbot, manager: TemplateManager, monkeypatch):
    """Test TemplateCleanupDialog table population, search filtering, and selection."""
    tmpl = TemplateDefinition(
        id=str(uuid.uuid4()),
        name="Unique Searchable Custom",
        description="Cleanup test description",
        width_px=1016,
        height_px=638,
        dpi=300,
        elements=[],
    )
    manager.save_user_template(tmpl)

    dialog = TemplateCleanupDialog(active_template_id=tmpl.id)
    qtbot.addWidget(dialog)

    # Check table row count
    total_templates = len(manager.list_templates())
    assert dialog.table.rowCount() == total_templates

    # Test search filter
    dialog.txt_search.setText("Unique Searchable")
    visible_rows = [r for r in range(dialog.table.rowCount()) if not dialog.table.isRowHidden(r)]
    assert len(visible_rows) == 1

    # Clear filter
    dialog.txt_search.setText("")
    visible_rows = [r for r in range(dialog.table.rowCount()) if not dialog.table.isRowHidden(r)]
    assert len(visible_rows) == total_templates

    # Test selection
    dialog._select_all_filtered()
    selected_ids = dialog._get_selected_ids()
    # Only custom templates have checkboxes
    assert tmpl.id in selected_ids
    assert dialog.btn_del_selected.isEnabled()

    dialog._deselect_all()
    assert len(dialog._get_selected_ids()) == 0
    assert not dialog.btn_del_selected.isEnabled()


def test_template_cleanup_dialog_single_delete(qtbot, manager: TemplateManager, monkeypatch):
    """Test deleting a single template from the dialog."""
    tmpl = TemplateDefinition(
        id=str(uuid.uuid4()),
        name="To Be Deleted",
        width_px=1016,
        height_px=638,
        dpi=300,
        elements=[],
    )
    manager.save_user_template(tmpl)

    dialog = TemplateCleanupDialog()
    qtbot.addWidget(dialog)

    # Mock QMessageBox to accept deletion and dismiss info
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    dialog._delete_single_template(tmpl.id, tmpl.name)
    assert dialog.manager.get_template(tmpl.id) is None


def test_editor_page_template_bar(qtbot, monkeypatch):
    """Test that EditorPage displays template bar and enables/disables delete appropriately."""
    editor = EditorPage()
    qtbot.addWidget(editor)

    builtins = [t for t in editor.template_manager.list_templates() if editor.template_manager.is_builtin(t.id)]
    assert len(builtins) > 0
    builtin = builtins[0]

    # Load built-in template
    editor.load_template(builtin)
    assert editor.lbl_tmpl_name.text() == f"<b>Template:</b> {builtin.name}"
    assert editor.lbl_tmpl_badge.text() == "Built-in"
    assert not editor.btn_tmpl_delete.isEnabled()

    # Create a custom template definition and load it
    custom_tmpl = TemplateDefinition(
        id=str(uuid.uuid4()),
        name="Custom Editor Card",
        width_px=1016,
        height_px=638,
        dpi=300,
        elements=[],
    )
    editor.template_manager.save_user_template(custom_tmpl)
    editor.load_template(custom_tmpl)
    assert editor.lbl_tmpl_name.text() == f"<b>Template:</b> {custom_tmpl.name}"
    assert editor.lbl_tmpl_badge.text() == "Custom Saved"
    assert editor.btn_tmpl_delete.isEnabled()

    # Clean up created custom template
    editor.template_manager.delete_user_template(custom_tmpl.id)


def test_template_page_filter_and_cleanup_button(qtbot):
    """Test that TemplatePage has the search filter and cleanup button."""
    tmpl_page = TemplatePage()
    qtbot.addWidget(tmpl_page)

    assert hasattr(tmpl_page, "btn_cleanup")
    assert hasattr(tmpl_page, "txt_filter")

    # Filter by non-existent term
    tmpl_page.txt_filter.setText("ZZZ_NO_MATCH_HERE_12345")
    visible_count = sum(
        1 for idx in range(tmpl_page.list_widget.count()) if not tmpl_page.list_widget.item(idx).isHidden()
    )
    assert visible_count == 0

    # Clear filter
    tmpl_page.txt_filter.setText("")
    visible_count = sum(
        1 for idx in range(tmpl_page.list_widget.count()) if not tmpl_page.list_widget.item(idx).isHidden()
    )
    assert visible_count == tmpl_page.list_widget.count()
