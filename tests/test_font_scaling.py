"""Tests for the screen aware UI font scaling.

The UI chrome type scales with the main screen: dense (retina) panels and
tall resolutions get larger glyphs than the compact 10-12px base scale.
Card (canvas) rendering is typographic geometry and must stay untouched.

The scale is forced through the ``ID_CARD_FONT_SCALE`` environment
variable in these tests, so the results never depend on the display the
suite runs on.
"""

import pytest
from PySide6.QtWidgets import QLabel, QWidget

import id_card_generator.ui.font_scaling as font_scaling
from id_card_generator.ui.font_scaling import (
    install_font_scaling,
    scale_stylesheet_text,
    scaled_point_size,
)
from id_card_generator.ui.theme_manager import ThemeManager

# A scale without rounding ties: 11 * 1.4 = 15.4 -> 15.
FORCED_SCALE = "1.4"


@pytest.fixture
def scaled_env(monkeypatch):
    """Force a deterministic font scale and keep the session cache clean."""
    monkeypatch.setenv(font_scaling.SCALE_ENV_VAR, FORCED_SCALE)
    monkeypatch.setattr(font_scaling, "_scale", None)
    yield font_scaling
    monkeypatch.setattr(font_scaling, "_scale", None)


def test_scale_stylesheet_text_scales_px_rules():
    stylesheet = "QLabel { color: #ffffff; font-size: 11px; padding: 0 4px; }"
    scaled = scale_stylesheet_text(stylesheet, 1.4)
    assert "font-size: 15px" in scaled
    # Colors and spacing metrics are untouched.
    assert "color: #ffffff" in scaled
    assert "padding: 0 4px" in scaled


def test_scale_stylesheet_text_scales_fractional_and_small_sizes():
    stylesheet = "QLabel { font-size: 10.5px; } QFrame { font-size: 9px; }"
    scaled = scale_stylesheet_text(stylesheet, 1.4)
    assert "font-size: 15px" in scaled   # 10.5 * 1.4 = 14.7
    assert "font-size: 13px" in scaled   # 9 * 1.4 = 12.6


def test_scale_stylesheet_text_leaves_points_and_other_metrics():
    stylesheet = "QLabel { font-size: 10pt; min-height: 11px; font-weight: 600; }"
    scaled = scale_stylesheet_text(stylesheet, 1.4)
    assert "font-size: 10pt" in scaled
    assert "min-height: 11px" in scaled


def test_compute_font_scale_uses_the_env_override(scaled_env):
    assert scaled_env.compute_font_scale() == 1.4


def test_compute_font_scale_clamps_the_override(monkeypatch):
    monkeypatch.setenv(font_scaling.SCALE_ENV_VAR, "9.0")
    assert font_scaling.compute_font_scale() == 2.0
    monkeypatch.setenv(font_scaling.SCALE_ENV_VAR, "0.1")
    assert font_scaling.compute_font_scale() == 0.75


def test_scaled_point_size_grows_with_the_scale(scaled_env):
    assert scaled_point_size(10) == 14   # 10 * 1.4
    assert scaled_point_size(6) == 8     # never below the 8pt floor


def test_scaled_point_grows_in_half_point_steps(scaled_env):
    from id_card_generator.ui.font_scaling import scaled_point

    assert scaled_point(10.0) == 14.0    # 10 * 1.4
    assert scaled_point(9.0) == 12.5     # 9 * 1.4 = 12.6 -> 12.5
    assert scaled_point(4.0) == 6.0      # never below the 6pt floor


def test_painted_record_list_grows_with_the_scale(qtbot, scaled_env):
    """The custom painted record list scales its fonts and row bands."""
    from PySide6.QtCore import QModelIndex
    from PySide6.QtWidgets import QStyleOptionViewItem

    from id_card_generator.ui.components.record_list import (
        RecordListDelegate,
        RecordListEntry,
        RecordListModel,
    )

    delegate = RecordListDelegate()
    option = QStyleOptionViewItem()
    option.rect.setWidth(300)
    assert delegate.sizeHint(option, QModelIndex()).height() == round(46 * 1.4)

    # The paint path must render the larger fonts without errors.
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter

    model = RecordListModel()
    model.set_entries([RecordListEntry(record_id="1", pin="130731", name="Manoj Kumar Jha")])
    entry_index = model.index(0)

    image = QImage(300, 80, QImage.Format_ARGB32)
    image.fill(Qt.white)
    painter = QPainter(image)
    option.rect.setRect(0, 0, 300, 64)
    delegate.paint(painter, option, entry_index)
    painter.end()
    assert not image.isNull()


def test_install_is_a_noop_at_base_scale(qtbot, monkeypatch):
    monkeypatch.setenv(font_scaling.SCALE_ENV_VAR, "1.0")
    monkeypatch.setattr(font_scaling, "_scale", None)
    original = QWidget.setStyleSheet
    try:
        assert install_font_scaling() == 1.0
        assert QWidget.setStyleSheet is original
    finally:
        monkeypatch.setattr(font_scaling, "_scale", None)


def test_applied_stylesheets_scale_once_without_compounding(qtbot, scaled_env):
    """Re-applying the unscaled source must never grow the glyphs again."""
    original = QWidget.setStyleSheet
    try:
        install_font_scaling()
        label = QLabel()
        qtbot.addWidget(label)

        label.setStyleSheet("QLabel { font-size: 11px; }")
        assert label.styleSheet() == "QLabel { font-size: 15px; }"
        # The unscaled source is remembered for lossless re-application.
        assert label.property("unscaled_stylesheet") == "QLabel { font-size: 11px; }"

        label.setStyleSheet(label.property("unscaled_stylesheet"))
        assert label.styleSheet() == "QLabel { font-size: 15px; }"
    finally:
        QWidget.setStyleSheet = original
        scaled_env._installed = False


def test_theme_retarget_never_compounds_the_scale(qtbot, scaled_env):
    """The theme retarget pass re-applies stylesheets; the scale holds."""
    original = QWidget.setStyleSheet
    try:
        install_font_scaling()
        label = QLabel()
        qtbot.addWidget(label)
        # A legacy hard coded colour the retarget pass rewrites.
        label.setStyleSheet("QLabel { color: #8e909f; font-size: 11px; }")

        ThemeManager.retarget_widget(label, "white")
        first = label.styleSheet()
        assert "font-size: 15px" in first

        # Switching themes back and forth must not grow the type.
        ThemeManager.retarget_widget(label, "black")
        ThemeManager.retarget_widget(label, "white")
        assert label.styleSheet() == first
    finally:
        QWidget.setStyleSheet = original
        scaled_env._installed = False
