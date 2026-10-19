"""Dialogs package."""

from id_card_generator.ui.dialogs.blank_canvas_dialog import (
    BlankCanvasDialog,
    CanvasPropertiesDialog,
)
from id_card_generator.ui.dialogs.new_project_dialog import NewProjectDialog
from id_card_generator.ui.dialogs.project_dialog import ProjectDialog
from id_card_generator.ui.dialogs.relink_dialog import RelinkDialog
from id_card_generator.ui.dialogs.template_cleanup_dialog import TemplateCleanupDialog

__all__ = [
    "BlankCanvasDialog",
    "CanvasPropertiesDialog",
    "NewProjectDialog",
    "ProjectDialog",
    "RelinkDialog",
    "TemplateCleanupDialog",
]


