"""Comprehensive tests for Photoshop/Figma-Style Smart Alignment, Snapping, and Spacing."""

import time
import pytest
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from id_card_generator.core.models import CanvasElement, TemplateDefinition
from id_card_generator.editor.canvas_items import CanvasItem
from id_card_generator.editor.canvas_scene import CanvasScene
from id_card_generator.editor.smart_alignment import (
    GuideLabel,
    GuideLine,
    GuideRenderer,
    GuideType,
    SmartAlignmentEngine,
    SmartSpacingEngine,
    SnapSettings,
    SpacingBadge,
    format_distance,
)


@pytest.fixture
def snap_engine() -> SmartAlignmentEngine:
    settings = SnapSettings(
        smart_guides_enabled=True,
        object_snapping_enabled=True,
        smart_spacing_enabled=True,
        snap_to_canvas_enabled=True,
        snap_threshold_screen=8.0,
    )
    return SmartAlignmentEngine(settings)


@pytest.fixture
def canvas_scene(qtbot) -> CanvasScene:
    scene = CanvasScene()
    tmpl = TemplateDefinition(name="Test Card", width_px=1000, height_px=600)
    scene.load_template(tmpl)
    return scene


# ============================================================================
# 1. Edge and Center Alignments
# ============================================================================

def test_edge_alignments(snap_engine: SmartAlignmentEngine):
    """Test Left-to-Left, Left-to-Right, Right-to-Left, Right-to-Right, Top-to-Top, Bottom-to-Bottom edge snapping."""
    target = QRectF(200, 200, 100, 100)  # Left: 200, Right: 300, Top: 200, Bottom: 300

    # 1. Left-to-Left: Moving element at x=204, width=50 (delta should be -4 to snap to 200)
    m1 = QRectF(204, 400, 50, 50)
    res1 = snap_engine.snap_move(m1, [target], zoom_factor=1.0)
    assert res1.has_horizontal_snap
    assert res1.delta_x == -4.0
    assert res1.snapped_x == 200.0
    assert any(g.p1.x() == 200.0 for g in res1.guides)

    # 2. Right-to-Left: Moving element right at x=197 (width=50, right=197 -> delta +3 to snap right to 200)
    m2 = QRectF(147, 400, 50, 50)  # right is 197
    res2 = snap_engine.snap_move(m2, [target], zoom_factor=1.0)
    assert res2.has_horizontal_snap
    assert res2.delta_x == 3.0
    assert res2.snapped_x + 50 == 200.0

    # 3. Left-to-Right: Moving element left at x=298 (delta +2 to snap left to target right 300)
    m3 = QRectF(298, 400, 50, 50)
    res3 = snap_engine.snap_move(m3, [target], zoom_factor=1.0)
    assert res3.has_horizontal_snap
    assert res3.delta_x == 2.0
    assert res3.snapped_x == 300.0

    # 4. Right-to-Right: Moving element right at x=304 (width=50, left=254, right=304 -> delta -4)
    m4 = QRectF(254, 400, 50, 50)
    res4 = snap_engine.snap_move(m4, [target], zoom_factor=1.0)
    assert res4.has_horizontal_snap
    assert res4.delta_x == -4.0
    assert res4.snapped_x + 50 == 300.0

    # 5. Top-to-Top: Moving element at y=203, height=60 (delta -3)
    m5 = QRectF(400, 203, 60, 60)
    res5 = snap_engine.snap_move(m5, [target], zoom_factor=1.0)
    assert res5.has_vertical_snap
    assert res5.delta_y == -3.0
    assert res5.snapped_y == 200.0

    # 6. Bottom-to-Bottom: Moving element bottom at y=296 (height=60, top=236, bottom=296 -> delta +4)
    m6 = QRectF(400, 236, 60, 60)
    res6 = snap_engine.snap_move(m6, [target], zoom_factor=1.0)
    assert res6.has_vertical_snap
    assert res6.delta_y == 4.0
    assert res6.snapped_y + 60 == 300.0


def test_center_alignments(snap_engine: SmartAlignmentEngine):
    """Test horizontal center and vertical center alignment between elements."""
    target = QRectF(200, 200, 100, 100)  # Center X: 250, Center Y: 250

    # Moving rect width=60, currently at x=217 (center_x = 217 + 30 = 247 -> delta +3 to snap to 250)
    m_h = QRectF(217, 400, 60, 40)
    res_h = snap_engine.snap_move(m_h, [target], zoom_factor=1.0)
    assert res_h.has_horizontal_snap
    assert res_h.delta_x == 3.0
    assert (res_h.snapped_x + 30) == 250.0
    assert any(g.is_center for g in res_h.guides)

    # Moving rect height=40, currently at y=233 (center_y = 233 + 20 = 253 -> delta -3 to snap to 250)
    m_v = QRectF(400, 233, 40, 40)
    res_v = snap_engine.snap_move(m_v, [target], zoom_factor=1.0)
    assert res_v.has_vertical_snap
    assert res_v.delta_y == -3.0
    assert (res_v.snapped_y + 20) == 250.0
    assert any(g.is_center for g in res_v.guides)


# ============================================================================
# 2. Canvas Edge and Center Snapping
# ============================================================================

def test_canvas_edge_and_center_snapping(snap_engine: SmartAlignmentEngine):
    """Test snapping against canvas boundaries and center axes."""
    canvas = QRectF(0, 0, 1000, 600)  # Canvas W: 1000, H: 600, Center: (500, 300)

    # 1. Canvas Left Edge (x=0)
    m_left = QRectF(4, 100, 50, 50)
    res_left = snap_engine.snap_move(m_left, [], canvas_rect=canvas, zoom_factor=1.0)
    assert res_left.delta_x == -4.0
    assert res_left.snapped_x == 0.0

    # 2. Canvas Right Edge (x=1000)
    m_right = QRectF(945, 100, 50, 50)  # right is 995 -> delta +5
    res_right = snap_engine.snap_move(m_right, [], canvas_rect=canvas, zoom_factor=1.0)
    assert res_right.delta_x == 5.0
    assert res_right.snapped_x + 50 == 1000.0

    # 3. Canvas Center X (x=500)
    m_cx = QRectF(467, 100, 60, 50)  # center_x is 497 -> delta +3
    res_cx = snap_engine.snap_move(m_cx, [], canvas_rect=canvas, zoom_factor=1.0)
    assert res_cx.delta_x == 3.0
    assert res_cx.snapped_x + 30 == 500.0
    assert any(g.guide_type == GuideType.CANVAS_CENTER_X for g in res_cx.guides)

    # 4. Canvas Top Edge (y=0)
    m_top = QRectF(100, 3, 50, 50)
    res_top = snap_engine.snap_move(m_top, [], canvas_rect=canvas, zoom_factor=1.0)
    assert res_top.delta_y == -3.0
    assert res_top.snapped_y == 0.0

    # 5. Canvas Bottom Edge (y=600)
    m_bottom = QRectF(100, 546, 50, 50)  # bottom is 596 -> delta +4
    res_bottom = snap_engine.snap_move(m_bottom, [], canvas_rect=canvas, zoom_factor=1.0)
    assert res_bottom.delta_y == 4.0
    assert res_bottom.snapped_y + 50 == 600.0

    # 6. Canvas Center Y (y=300)
    m_cy = QRectF(100, 276, 50, 50)  # center_y is 301 -> delta -1
    res_cy = snap_engine.snap_move(m_cy, [], canvas_rect=canvas, zoom_factor=1.0)
    assert res_cy.delta_y == -1.0
    assert res_cy.snapped_y + 25 == 300.0
    assert any(g.guide_type == GuideType.CANVAS_CENTER_Y for g in res_cy.guides)


# ============================================================================
# 3. Simultaneous Horizontal and Vertical Snapping
# ============================================================================

def test_simultaneous_horizontal_and_vertical_snapping(snap_engine: SmartAlignmentEngine):
    """Test both X and Y snapping together simultaneously."""
    target1 = QRectF(100, 50, 80, 80)   # Left: 100, Right: 180
    target2 = QRectF(300, 400, 80, 80)  # Top: 400, Bottom: 480

    # Moving rect placed near target1's left (103) and target2's top (397)
    moving = QRectF(103, 397, 60, 60)
    res = snap_engine.snap_move(moving, [target1, target2], zoom_factor=1.0)

    assert res.has_horizontal_snap
    assert res.has_vertical_snap
    assert res.delta_x == -3.0
    assert res.delta_y == 3.0
    assert res.snapped_x == 100.0
    assert res.snapped_y == 400.0
    assert len(res.guides) >= 2


# ============================================================================
# 4. Multiple Competing Candidates and Threshold Boundaries
# ============================================================================

def test_multiple_competing_candidates(snap_engine: SmartAlignmentEngine):
    """Test picking candidate with smallest error and combining co-aligned lines."""
    t1 = QRectF(100, 100, 50, 50)  # Right at 150
    t2 = QRectF(155, 300, 50, 50)  # Left at 155

    # Moving element at x=151 (delta to t1's right is -1; delta to t2's left is +4)
    # The engine must choose t1 (delta -1) as it is closer
    m = QRectF(151, 200, 40, 40)
    res = snap_engine.snap_move(m, [t1, t2], zoom_factor=1.0)
    assert res.delta_x == -1.0
    assert res.snapped_x == 150.0

    # Co-aligned targets: two targets sharing the exact same left coordinate
    t3 = QRectF(200, 50, 40, 40)
    t4 = QRectF(200, 450, 40, 40)
    m_co = QRectF(203, 250, 40, 40)
    res_co = snap_engine.snap_move(m_co, [t3, t4], zoom_factor=1.0)
    assert res_co.delta_x == -3.0
    assert res_co.snapped_x == 200.0
    # Guide line should span across t3, m_co, and t4
    g = [g for g in res_co.guides if g.p1.x() == 200.0][0]
    assert g.p1.y() <= 50.0
    assert g.p2.y() >= 490.0


def test_threshold_boundaries_and_release(snap_engine: SmartAlignmentEngine):
    """Test that items snap within threshold and release cleanly beyond it."""
    target = QRectF(200, 200, 100, 100)

    # Threshold is 8.0 px
    # At offset 7.5 px -> should snap
    m_in = QRectF(207.5, 300, 50, 50)
    res_in = snap_engine.snap_move(m_in, [target], zoom_factor=1.0)
    assert res_in.has_horizontal_snap
    assert res_in.delta_x == -7.5
    assert res_in.snapped_x == 200.0

    # At offset 8.5 px -> outside threshold -> should release (delta 0)
    m_out = QRectF(208.5, 300, 50, 50)
    res_out = snap_engine.snap_move(m_out, [target], zoom_factor=1.0)
    assert not res_out.has_horizontal_snap
    assert res_out.delta_x == 0.0
    assert res_out.snapped_x == 208.5


# ============================================================================
# 5. Zoom Independence
# ============================================================================

def test_zoom_independence(snap_engine: SmartAlignmentEngine):
    """Test screen-space threshold consistency across different zoom factors."""
    target = QRectF(200, 200, 100, 100)

    # 1. At 200% zoom (zoom=2.0), 8 screen px corresponds to 4 scene px
    # Offset of 3.5 scene px is within threshold (3.5 * 2 = 7 screen px <= 8)
    m_2x = QRectF(203.5, 300, 50, 50)
    res_2x = snap_engine.snap_move(m_2x, [target], zoom_factor=2.0)
    assert res_2x.has_horizontal_snap
    assert res_2x.delta_x == -3.5

    # Offset of 4.5 scene px is outside threshold (4.5 * 2 = 9 screen px > 8)
    m_2x_out = QRectF(204.5, 300, 50, 50)
    res_2x_out = snap_engine.snap_move(m_2x_out, [target], zoom_factor=2.0)
    assert not res_2x_out.has_horizontal_snap

    # 2. At 50% zoom (zoom=0.5), 8 screen px corresponds to 16 scene px
    # Offset of 14 scene px is within threshold (14 * 0.5 = 7 screen px <= 8)
    m_half = QRectF(186.0, 300, 50, 50)
    res_half = snap_engine.snap_move(m_half, [target], zoom_factor=0.5)
    assert res_half.has_horizontal_snap
    assert res_half.delta_x == 14.0
    assert res_half.snapped_x == 200.0


# ============================================================================
# 6. Resize Snapping
# ============================================================================

def test_resize_snapping_handles(snap_engine: SmartAlignmentEngine):
    """Test snapping of edges and corners across resize handles."""
    target = QRectF(300, 300, 100, 100)

    # Handle 3 (Right edge): Start at [100, 100, 100, 100], right is 200.
    # Drag right to 297 (close to target left 300)
    start_rect = QRectF(100, 100, 100, 100)
    prop_r = QRectF(100, 100, 197, 100)  # proposed right is 297
    snapped_r, res_r = snap_engine.snap_resize(3, start_rect, prop_r, [target], zoom_factor=1.0)
    assert snapped_r.right() == 300.0
    assert snapped_r.left() == 100.0  # left corner fixed!
    assert len(res_r.guides) > 0

    # Handle 5 (Bottom edge): Drag bottom to 296 (close to target top 300)
    prop_b = QRectF(100, 100, 100, 196)  # proposed bottom is 296
    snapped_b, res_b = snap_engine.snap_resize(5, start_rect, prop_b, [target], zoom_factor=1.0)
    assert snapped_b.bottom() == 300.0
    assert snapped_b.top() == 100.0  # top edge fixed!
    assert len(res_b.guides) > 0

    # Handle 0 (Top-Left corner): Drag left to 298, top to 298
    start_corner = QRectF(350, 350, 100, 100)
    prop_tl = QRectF(298, 298, 152, 152)
    snapped_tl, res_tl = snap_engine.snap_resize(0, start_corner, prop_tl, [target], zoom_factor=1.0)
    assert snapped_tl.left() == 300.0
    assert snapped_tl.top() == 300.0
    assert snapped_tl.right() == 450.0  # Bottom-Right fixed!
    assert snapped_tl.bottom() == 450.0

    # Minimum size enforcement
    prop_tiny = QRectF(100, 100, 5, 5)
    snapped_tiny, _ = snap_engine.snap_resize(4, start_rect, prop_tiny, [target], zoom_factor=1.0)
    assert snapped_tiny.width() >= 5.0


# ============================================================================
# 7. Smart Spacing and Equal Distribution
# ============================================================================

def test_smart_spacing_detection(snap_engine: SmartAlignmentEngine):
    """Test Figma-style equal horizontal and vertical gap detection."""
    # 1. Horizontal: Target A [0, 60] (w=60), Target B [90, 150] (w=60, gap=30)
    t_a = QRectF(0, 100, 60, 50)
    t_b = QRectF(90, 100, 60, 50)
    # Moving C placed adjacent to B at x=176 (desired: 150 + 30 = 180 -> delta +4)
    m_c = QRectF(176, 100, 60, 50)
    res_h = snap_engine.snap_move(m_c, [t_a, t_b], zoom_factor=1.0)
    assert res_h.delta_x == 4.0
    assert res_h.snapped_x == 180.0
    assert len(res_h.spacing_badges) == 2
    assert "30 px" in res_h.spacing_badges[0].badge_text

    # 2. Horizontal: Moving between Target A [0, 50] and Target B [150, 200]
    # Total space between = 100 px. Moving element width = 40 px. Equal gap = (100 - 40) / 2 = 30 px.
    # Desired left: 50 + 30 = 80 px. Currently at x=83.
    t_left = QRectF(0, 100, 50, 50)
    t_right = QRectF(150, 100, 50, 50)
    m_mid = QRectF(83, 100, 40, 50)
    res_mid = snap_engine.snap_move(m_mid, [t_left, t_right], zoom_factor=1.0)
    assert res_mid.delta_x == -3.0
    assert res_mid.snapped_x == 80.0
    assert len(res_mid.spacing_badges) == 2

    # 3. Vertical: Target A [0, 50] (h=50), Target B [80, 130] (h=50, gap=30)
    # Moving below B at y=156 (desired: 130 + 30 = 160 -> delta +4)
    t_v1 = QRectF(100, 0, 50, 50)
    t_v2 = QRectF(100, 80, 50, 50)
    m_v3 = QRectF(100, 156, 50, 50)
    res_v = snap_engine.snap_move(m_v3, [t_v1, t_v2], zoom_factor=1.0)
    assert res_v.delta_y == 4.0
    assert res_v.snapped_y == 160.0
    assert len(res_v.spacing_badges) == 2


# ============================================================================
# 8. Multi-Selection and Target Filtering
# ============================================================================

def test_multi_selection_movement(canvas_scene: CanvasScene):
    """Test multi-selection moving as a single bounding unit."""
    el1 = CanvasElement(name="Elem 1", x=100, y=100, width=50, height=50)
    el2 = CanvasElement(name="Elem 2", x=200, y=100, width=50, height=50)
    target_el = CanvasElement(name="Target", x=500, y=100, width=50, height=50)

    it1 = canvas_scene.add_element(el1, push_undo=False)
    it2 = canvas_scene.add_element(el2, push_undo=False)
    it_target = canvas_scene.add_element(target_el, push_undo=False)

    canvas_scene.clearSelection()
    it1.setSelected(True)
    it2.setSelected(True)

    # Starting positions
    canvas_scene._mouse_press_positions = {it1: QPointF(100, 100), it2: QPointF(200, 100)}

    # Group bounding box is [100, 100, 150, 50], right edge is 250.
    # Relative offset between it1 and it2 is 100 px.
    # Suppose mouse moves by dx=247 (group right becomes 497, near target left 500)
    proposed_group = QRectF(347, 100, 150, 50)
    targets = canvas_scene.get_reference_targets(exclude_items={it1, it2})
    snap_res = canvas_scene.smart_alignment_engine.snap_move(proposed_group, targets)

    assert snap_res.delta_x == 3.0
    assert snap_res.snapped_x + 150 == 500.0


def test_target_filtering_hidden_and_locked(canvas_scene: CanvasScene):
    """Test that hidden elements are ignored and locked elements act as references without moving."""
    el_locked = CanvasElement(name="Locked Reference", x=300, y=100, width=50, height=50, locked=True)
    el_hidden = CanvasElement(name="Hidden Item", x=700, y=100, width=50, height=50, visible=False)
    el_active = CanvasElement(name="Active Mover", x=100, y=100, width=50, height=50)

    it_locked = canvas_scene.add_element(el_locked, push_undo=False)
    it_hidden = canvas_scene.add_element(el_hidden, push_undo=False)
    it_active = canvas_scene.add_element(el_active, push_undo=False)

    targets = canvas_scene.get_reference_targets(exclude_items={it_active})
    target_xs = [t.x() for t in targets]

    # Locked element (x=300) MUST be in reference targets
    assert 300.0 in target_xs
    # Hidden element (x=700) MUST NOT be in reference targets
    assert 700.0 not in target_xs


# ============================================================================
# 9. Disabling and Bypassing Snapping
# ============================================================================

def test_disabling_and_bypassing(snap_engine: SmartAlignmentEngine):
    """Test disabling snapping and holding Alt to bypass."""
    target = QRectF(200, 200, 100, 100)
    moving = QRectF(203, 300, 50, 50)

    # 1. Alt bypass held -> no delta, no guides
    res_bypass = snap_engine.snap_move(moving, [target], bypass_snap=True)
    assert res_bypass.delta_x == 0.0
    assert res_bypass.snapped_x == 203.0
    assert len(res_bypass.guides) == 0

    # 2. Object snapping disabled in settings -> no delta
    snap_engine.settings.object_snapping_enabled = False
    res_nosnap = snap_engine.snap_move(moving, [target], bypass_snap=False)
    assert res_nosnap.delta_x == 0.0
    assert res_nosnap.snapped_x == 203.0

    # 3. Smart guides disabled -> no guides
    snap_engine.settings.smart_guides_enabled = False
    res_noguides = snap_engine.snap_move(moving, [target], bypass_snap=False)
    assert len(res_noguides.guides) == 0


# ============================================================================
# 10. Guide Rendering
# ============================================================================

def test_guide_renderer_drawing():
    """Verify GuideRenderer executes cleanly on QPainter without errors."""
    img = QImage(400, 400, QImage.Format_ARGB32)
    img.fill(Qt.transparent)

    painter = QPainter(img)
    guides = [
        GuideLine(p1=QPointF(100, 0), p2=QPointF(100, 300), guide_type=GuideType.ALIGN_LEFT),
        GuideLine(p1=QPointF(0, 150), p2=QPointF(300, 150), guide_type=GuideType.CANVAS_CENTER_Y, is_center=True),
    ]
    badges = [
        SpacingBadge(
            axis="x",
            distance=24.0,
            p1=QPointF(50, 100),
            p2=QPointF(74, 100),
            marker_lines=[(QPointF(50, 95), QPointF(50, 105)), (QPointF(74, 95), QPointF(74, 105))],
            badge_text="24 px",
        )
    ]
    GuideRenderer.render(painter, guides, badges, zoom_factor=1.0)
    painter.end()

    # Image should not be completely empty
    pixel_bytes = img.bits().tobytes()
    assert any(b != 0 for b in pixel_bytes[:2000])


# ============================================================================
# 11. Undo / Redo Integration
# ============================================================================

def test_undo_redo_with_snapping(canvas_scene: CanvasScene):
    """Verify that moving an element with smart snapping works with undo and redo history."""
    el = CanvasElement(name="Text Item", x=100.0, y=100.0, width=50.0, height=50.0)
    item = canvas_scene.add_element(el, push_undo=False)

    old_p = QPointF(100.0, 100.0)
    snapped_p = QPointF(200.0, 100.0)

    from id_card_generator.editor.undo_manager import MoveElementCommand
    item.setPos(snapped_p)
    item.update_model_position()
    canvas_scene.undo_stack.push(MoveElementCommand(item, old_p, snapped_p))

    assert item.pos().x() == 200.0

    # Undo
    canvas_scene.undo()
    assert item.pos().x() == 100.0

    # Redo
    canvas_scene.redo()
    assert item.pos().x() == 200.0


# ============================================================================
# 12. Interactive Canvas Drag and Keyboard Nudge
# ============================================================================

def test_interactive_canvas_drag_snapping(canvas_scene: CanvasScene):
    """Test interactive mouse dragging with smart snapping and temporary guide rendering."""
    target_el = CanvasElement(name="Target", x=200.0, y=200.0, width=100.0, height=100.0)
    drag_el = CanvasElement(name="DragItem", x=50.0, y=200.0, width=50.0, height=50.0)

    target_item = canvas_scene.add_element(target_el, push_undo=False)
    drag_item = canvas_scene.add_element(drag_el, push_undo=False)

    canvas_scene.clearSelection()
    drag_item.setSelected(True)

    # 1. Simulate mouse press at item center
    canvas_scene._mouse_press_positions = {drag_item: QPointF(50.0, 200.0)}

    # 2. Simulate drag close to target left edge (move dx=147 to x=197 -> target left is 200, within 8px)
    event_disp = QPointF(147.0, 0.0)
    proposed_rect = QRectF(50.0 + 147.0, 200.0, 50.0, 50.0)
    targets = canvas_scene.get_reference_targets(exclude_items={drag_item})
    snap_res = canvas_scene.smart_alignment_engine.snap_move(proposed_rect, targets)

    # Snaps right to 200
    assert snap_res.has_horizontal_snap
    assert snap_res.snapped_x == 200.0
    assert snap_res.delta_x == 3.0
    assert len(snap_res.guides) > 0

    # Apply to item
    drag_item.setPos(snap_res.snapped_x, 200.0)
    drag_item.update_model_position()
    canvas_scene.set_active_guides(snap_res.guides, snap_res.spacing_badges)

    assert len(canvas_scene._active_guides) > 0
    assert drag_item.pos().x() == 200.0
    assert drag_item.element.x == 200.0

    # 3. Simulate mouse release: guides must be cleared
    canvas_scene.clear_guides()
    assert len(canvas_scene._active_guides) == 0


def test_interactive_keyboard_nudge_snapping(canvas_scene: CanvasScene):
    """Test that keyboard arrow nudge moves freely 1px at a time and flashes guides on alignment."""
    target_el = CanvasElement(name="Target", x=200.0, y=200.0, width=100.0, height=100.0)
    mover_el = CanvasElement(name="Mover", x=201.0, y=300.0, width=50.0, height=50.0)

    canvas_scene.add_element(target_el, push_undo=False)
    mover_item = canvas_scene.add_element(mover_el, push_undo=False)

    canvas_scene.clearSelection()
    mover_item.setSelected(True)

    from PySide6.QtGui import QKeyEvent

    # 1. Mover at 201.0. Press Left (1px) -> lands exactly on 200.0 (aligned with Target left)
    key_left = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Left, Qt.NoModifier)
    canvas_scene.keyPressEvent(key_left)
    assert mover_item.pos().x() == 200.0
    assert mover_item.element.x == 200.0
    # Smart guide is triggered because it's aligned!
    assert len(canvas_scene._active_guides) > 0

    # 2. Press Left again (1px) -> MUST move to 199.0 and NOT be trapped by snapping back to 200.0!
    canvas_scene.keyPressEvent(key_left)
    assert mover_item.pos().x() == 199.0
    assert mover_item.element.x == 199.0
    # Guides cleared because it moved past alignment
    assert len(canvas_scene._active_guides) == 0

    # 3. Press Right (1px) -> moves back to 200.0
    key_right = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Right, Qt.NoModifier)
    canvas_scene.keyPressEvent(key_right)
    assert mover_item.pos().x() == 200.0
    assert mover_item.element.x == 200.0
    assert len(canvas_scene._active_guides) > 0

    # 4. Press Right again (1px) -> MUST move to 201.0 freely
    canvas_scene.keyPressEvent(key_right)
    assert mover_item.pos().x() == 201.0
    assert mover_item.element.x == 201.0
    assert len(canvas_scene._active_guides) == 0


def test_keyboard_nudge_steps_and_undo(canvas_scene: CanvasScene):
    """Test 1px normal nudge, 10px Shift nudge, and undo/redo."""
    from PySide6.QtGui import QKeyEvent

    el = CanvasElement(name="Item", x=50.0, y=50.0, width=30.0, height=30.0)
    item = canvas_scene.add_element(el, push_undo=False)
    canvas_scene.clearSelection()
    item.setSelected(True)

    # 1px nudge Right
    ev_right = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Right, Qt.NoModifier)
    canvas_scene.keyPressEvent(ev_right)
    assert item.pos().x() == 51.0
    assert item.element.x == 51.0

    # 10px Shift nudge Down
    ev_down_shift = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Down, Qt.ShiftModifier)
    canvas_scene.keyPressEvent(ev_down_shift)
    assert item.pos().y() == 60.0
    assert item.element.y == 60.0

    # Undo 10px down
    canvas_scene.undo()
    assert item.pos().y() == 50.0
    assert item.element.y == 50.0

    # Undo 1px right
    canvas_scene.undo()
    assert item.pos().x() == 50.0
    assert item.element.x == 50.0

    # Redo 1px right
    canvas_scene.redo()
    assert item.pos().x() == 51.0
    assert item.element.x == 51.0


def test_keyboard_nudge_alt_bypass(canvas_scene: CanvasScene):
    """Test that Alt modifier completely bypasses snapping during keyboard nudge."""
    from PySide6.QtGui import QKeyEvent

    target_el = CanvasElement(name="Target", x=200.0, y=200.0, width=100.0, height=100.0)
    mover_el = CanvasElement(name="Mover", x=207.0, y=300.0, width=50.0, height=50.0)

    canvas_scene.add_element(target_el, push_undo=False)
    mover_item = canvas_scene.add_element(mover_el, push_undo=False)

    canvas_scene.clearSelection()
    mover_item.setSelected(True)

    # Alt+Shift+Left: would snap to 200 without Alt, but with Alt it moves exactly 10px to 197.0
    ev = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Left, Qt.AltModifier | Qt.ShiftModifier)
    canvas_scene.keyPressEvent(ev)

    assert mover_item.pos().x() == 197.0
    assert mover_item.element.x == 197.0
    assert len(canvas_scene._active_guides) == 0


def test_keyboard_nudge_multi_selection(canvas_scene: CanvasScene):
    """Test that multiple selected elements move together and undo in a single step."""
    from PySide6.QtGui import QKeyEvent

    el1 = CanvasElement(name="El1", x=100.0, y=100.0, width=50.0, height=50.0)
    el2 = CanvasElement(name="El2", x=300.0, y=200.0, width=60.0, height=40.0)

    item1 = canvas_scene.add_element(el1, push_undo=False)
    item2 = canvas_scene.add_element(el2, push_undo=False)

    canvas_scene.clearSelection()
    item1.setSelected(True)
    item2.setSelected(True)
    assert len(canvas_scene.selectedItems()) == 2

    # Nudge Right with Shift (10px) + Alt (bypass snap)
    ev = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Right, Qt.ShiftModifier | Qt.AltModifier)
    canvas_scene.keyPressEvent(ev)

    assert item1.pos().x() == 110.0
    assert item1.element.x == 110.0
    assert item2.pos().x() == 310.0
    assert item2.element.x == 310.0

    # Single undo step restores both items
    canvas_scene.undo()
    assert item1.pos().x() == 100.0
    assert item1.element.x == 100.0
    assert item2.pos().x() == 300.0
    assert item2.element.x == 300.0


# ============================================================================
# 13. Large Document Performance
# ============================================================================

def test_performance_many_elements(snap_engine: SmartAlignmentEngine):
    """Verify that snap calculation remains extremely fast (< 5ms) with hundreds of elements."""
    targets = []
    for i in range(250):
        targets.append(QRectF((i % 15) * 60, (i // 15) * 40, 45, 30))

    moving = QRectF(123.0, 123.0, 45.0, 30.0)

    start = time.perf_counter()
    res = snap_engine.snap_move(moving, targets, canvas_rect=QRectF(0, 0, 1200, 800), zoom_factor=1.0)
    elapsed = time.perf_counter() - start

    assert res is not None
    # Must compute within 15 milliseconds even with 250 elements
    assert elapsed < 0.015


# ============================================================================
# 14. Boundary Distance Measurement on Smart Guides
# ============================================================================

def test_boundary_distance_between_two_objects_horizontal():
    """Verify smart guide lines display boundary gap distance in mm between two horizontal objects."""
    settings = SnapSettings(smart_guides_enabled=True, snap_to_canvas_enabled=False, unit="mm", dpi=300)
    engine = SmartAlignmentEngine(settings)

    # Target A [x: 50..150, y: 100..150] (w=100, h=50)
    # Moving B [x: 250..350, y: 102..152] (w=100, h=50) -> snaps top to 100 (delta_y = -2)
    t_a = QRectF(50, 100, 100, 50)
    m_b = QRectF(250, 102, 100, 50)

    res = engine.snap_move(m_b, [t_a], zoom_factor=1.0)
    assert res.has_vertical_snap
    assert res.delta_y == -2.0
    assert len(res.guides) > 0

    # Top alignment guide should have a label in the middle of the gap (at x=200, y=100)
    top_guides = [g for g in res.guides if g.guide_type == GuideType.ALIGN_TOP]
    assert len(top_guides) > 0
    g = top_guides[0]
    assert len(g.labels) == 1
    lbl = g.labels[0]
    # Gap is 100px. At 300 DPI, 100 / 300 * 25.4 = 8.466 mm -> 8.5 mm
    assert lbl.text == "8.5 mm"
    assert lbl.pos.x() == 200.0  # Midpoint of 150 and 250
    assert lbl.pos.y() == 100.0


def test_boundary_distance_between_two_objects_vertical():
    """Verify smart guide lines display boundary gap distance in cm between two vertically stacked objects."""
    settings = SnapSettings(smart_guides_enabled=True, snap_to_canvas_enabled=False, unit="cm", dpi=300)
    engine = SmartAlignmentEngine(settings)

    # Target A [x: 100..200, y: 50..110] (bottom=110)
    # Moving B [x: 103..203, y: 250..310] (top=250) -> snaps left to 100 (delta_x = -3)
    t_a = QRectF(100, 50, 100, 60)
    m_b = QRectF(103, 250, 100, 60)

    res = engine.snap_move(m_b, [t_a], zoom_factor=1.0)
    assert res.has_horizontal_snap
    assert res.delta_x == -3.0

    left_guides = [g for g in res.guides if g.guide_type == GuideType.ALIGN_LEFT]
    assert len(left_guides) > 0
    g = left_guides[0]
    assert len(g.labels) == 1
    lbl = g.labels[0]
    # Gap is 140px. At 300 DPI, 140 / 300 * 2.54 = 1.185 cm -> 1.2 cm
    assert lbl.text == "1.2 cm"
    assert lbl.pos.x() == 100.0
    assert lbl.pos.y() == 180.0  # Midpoint of 110 and 250


def test_boundary_distance_canvas_unit_formatting():
    """Verify format_distance formats accurately for mm, cm, inch, and px."""
    # 300 DPI
    assert format_distance(118.11, "mm", 300) == "10 mm"
    assert format_distance(125.0, "mm", 300) == "10.6 mm"
    assert format_distance(118.11, "cm", 300) == "1 cm"
    assert format_distance(150.0, "inch", 300) == "0.5 in"
    assert format_distance(50.0, "px", 300) == "50 px"


def test_boundary_distance_with_canvas_edge():
    """Verify distance between canvas boundaries and object boundaries on smart guides."""
    settings = SnapSettings(smart_guides_enabled=True, snap_to_canvas_enabled=True, unit="mm", dpi=300)
    engine = SmartAlignmentEngine(settings)

    canvas = QRectF(0, 0, 1000, 600)
    # Moving element center y snapped to canvas center (y=300)
    m = QRectF(200, 278, 200, 40)
    res = engine.snap_move(m, [], canvas_rect=canvas, zoom_factor=1.0)
    assert res.has_vertical_snap
    center_guides = [g for g in res.guides if g.guide_type == GuideType.CANVAS_CENTER_Y]
    assert len(center_guides) > 0
    g = center_guides[0]
    # Should have labels for distance to left canvas edge and right canvas edge
    assert len(g.labels) == 2
    # Left: 200px / 300 * 25.4 = 16.9 mm at x=100
    assert g.labels[0].text == "16.9 mm"
    assert g.labels[0].pos.x() == 100.0
    # Right: (1000 - 400) = 600px / 300 * 25.4 = 50.8 mm at x=700
    assert g.labels[1].text == "50.8 mm"
    assert g.labels[1].pos.x() == 700.0


def test_guide_renderer_renders_distance_labels(qtbot):
    """Verify GuideRenderer renders guide lines and distance badges without errors."""
    img = QImage(600, 400, QImage.Format_ARGB32)
    img.fill(Qt.white)
    painter = QPainter(img)

    g = GuideLine(
        p1=QPointF(50, 100),
        p2=QPointF(400, 100),
        guide_type=GuideType.ALIGN_TOP,
        labels=[GuideLabel(pos=QPointF(200, 100), text="12.5 mm", distance_px=147.6)],
    )

    badge = SpacingBadge(
        axis="x",
        distance=60.0,
        p1=QPointF(50, 200),
        p2=QPointF(110, 200),
        badge_text="5.1 mm",
    )

    GuideRenderer.render(painter, [g], [badge], zoom_factor=1.0)
    painter.end()
    # Image must have been painted on
    assert not img.isNull()

