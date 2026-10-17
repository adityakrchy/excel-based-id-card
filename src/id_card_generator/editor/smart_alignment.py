"""Photoshop/Figma-Style Smart Alignment, Snapping, and Spacing Engine.

Provides dynamic smart guides, magnetic object snapping, equal distribution/spacing
detection, and temporary overlay rendering for canvas editing.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen


class GuideType(Enum):
    """Classification of smart alignment guides."""
    ALIGN_LEFT = "align_left"
    ALIGN_RIGHT = "align_right"
    ALIGN_TOP = "align_top"
    ALIGN_BOTTOM = "align_bottom"
    ALIGN_CENTER_X = "align_center_x"
    ALIGN_CENTER_Y = "align_center_y"
    CANVAS_EDGE_X = "canvas_edge_x"
    CANVAS_EDGE_Y = "canvas_edge_y"
    CANVAS_CENTER_X = "canvas_center_x"
    CANVAS_CENTER_Y = "canvas_center_y"
    GRID_X = "grid_x"
    GRID_Y = "grid_y"
    SPACING_X = "spacing_x"
    SPACING_Y = "spacing_y"


def format_distance(dist_px: float, unit: str = "px", dpi: int = 300) -> str:
    """Format pixel distance into canvas unit (mm, cm, inch, or px)."""
    u = (unit or "px").lower().strip()
    dpi = max(1, dpi or 300)
    inches = dist_px / dpi

    if u in ("mm", "millimeter", "millimeters"):
        val = inches * 25.4
        unit_str = "mm"
    elif u in ("cm", "centimeter", "centimeters"):
        val = inches * 2.54
        unit_str = "cm"
    elif u in ("in", "inch", "inches"):
        val = inches
        unit_str = "in"
    elif u in ("pt", "point", "points"):
        val = inches * 72.0
        unit_str = "pt"
    else:  # px
        val = dist_px
        unit_str = "px"

    if unit_str == "px":
        return f"{int(round(val))} px"
    elif abs(val - round(val)) < 0.04:
        return f"{int(round(val))} {unit_str}"
    else:
        return f"{val:.1f} {unit_str}"


@dataclass
class SnapSettings:
    """Configuration options for smart alignment and magnetic snapping."""
    smart_guides_enabled: bool = True
    object_snapping_enabled: bool = True
    smart_spacing_enabled: bool = True
    snap_to_canvas_enabled: bool = True
    snap_to_grid_enabled: bool = False
    grid_size: float = 10.0
    # Screen-space snapping threshold in logical screen pixels (visual sensitivity)
    snap_threshold_screen: float = 8.0
    guide_color: str = "#FF2D9A"  # Photoshop / Figma Smart Guide Magenta
    unit: str = "px"
    dpi: int = 300

    def get_scene_threshold(self, zoom_factor: float = 1.0) -> float:
        """Convert screen-space threshold into scene coordinates based on viewport zoom."""
        zf = max(0.05, zoom_factor)
        return self.snap_threshold_screen / zf


@dataclass
class GuideLabel:
    """Represents a dimension distance badge rendered along a smart guide line."""
    pos: QPointF
    text: str
    distance_px: float = 0.0


@dataclass
class GuideLine:
    """Represents a temporary visual alignment guide line."""
    p1: QPointF
    p2: QPointF
    guide_type: GuideType
    color: str = "#FF2D9A"
    is_center: bool = False
    labels: List[GuideLabel] = field(default_factory=list)
    distance_text: Optional[str] = None
    distance_pos: Optional[QPointF] = None


@dataclass
class SpacingBadge:
    """Represents an equal-spacing indicator badge with dimension line and text."""
    axis: str  # 'x' or 'y'
    distance: float
    p1: QPointF  # Start of gap line
    p2: QPointF  # End of gap line
    marker_lines: List[Tuple[QPointF, QPointF]] = field(default_factory=list)
    badge_text: str = ""


@dataclass
class SnapResult:
    """Outcome of snapping calculations for an element or selection."""
    snapped_x: Optional[float] = None
    snapped_y: Optional[float] = None
    delta_x: float = 0.0
    delta_y: float = 0.0
    guides: List[GuideLine] = field(default_factory=list)
    spacing_badges: List[SpacingBadge] = field(default_factory=list)
    has_horizontal_snap: bool = False
    has_vertical_snap: bool = False


class SmartSpacingEngine:
    """Detects equal spacing and distribution relationships between neighboring elements."""

    @staticmethod
    def detect_horizontal_spacing(
        moving_rect: QRectF,
        targets: List[QRectF],
        threshold: float,
        unit: str = "px",
        dpi: int = 300,
    ) -> Optional[Tuple[float, List[SpacingBadge], List[GuideLine]]]:
        """Detect if moving_rect can snap to equal horizontal spacing between/adjacent to targets.
        
        Returns:
            Tuple of (delta_x, spacing_badges, guide_lines) or None if no equal spacing candidate.
        """
        if len(targets) < 1:
            return None

        # Filter targets that share horizontal band (vertical overlap within reasonable window)
        m_top = moving_rect.top()
        m_bottom = moving_rect.bottom()
        m_h = moving_rect.height()

        band_targets = []
        for t in targets:
            # Check vertical overlap or near-alignment
            overlap = min(m_bottom, t.bottom()) - max(m_top, t.top())
            if overlap >= -max(30.0, m_h * 0.5):
                band_targets.append(t)

        if not band_targets:
            return None

        candidates: List[Tuple[float, float, List[SpacingBadge]]] = []

        # Sort targets from left to right
        sorted_targets = sorted(band_targets, key=lambda r: r.left())

        # 1. Check between pairs of targets: moving element placed between target A and target B
        for i in range(len(sorted_targets) - 1):
            t_a = sorted_targets[i]
            t_b = sorted_targets[i + 1]
            if t_a.right() >= t_b.left():
                continue
            total_gap = t_b.left() - t_a.right()
            if total_gap > moving_rect.width():
                equal_gap = (total_gap - moving_rect.width()) / 2.0
                if equal_gap >= 2.0:
                    desired_x = t_a.right() + equal_gap
                    delta = desired_x - moving_rect.left()
                    if abs(delta) <= threshold:
                        # Construct badges
                        y_mid = (max(t_a.top(), moving_rect.top()) + min(t_a.bottom(), moving_rect.bottom())) / 2.0
                        badges = SmartSpacingEngine._create_h_spacing_badges(
                            [
                                (t_a.right(), desired_x, y_mid, equal_gap),
                                (desired_x + moving_rect.width(), t_b.left(), y_mid, equal_gap),
                            ],
                            unit=unit,
                            dpi=dpi,
                        )
                        candidates.append((abs(delta), delta, badges))

        # 2. Check adjacent to a pair of targets:
        # Target A, Target B, Moving M  OR  Moving M, Target A, Target B
        for i in range(len(sorted_targets) - 1):
            t_a = sorted_targets[i]
            t_b = sorted_targets[i + 1]
            if t_a.right() >= t_b.left():
                continue
            gap_ab = t_b.left() - t_a.right()
            if gap_ab < 2.0:
                continue

            # Case: M placed to the right of B (A -> B -> M)
            desired_x_right = t_b.right() + gap_ab
            delta_right = desired_x_right - moving_rect.left()
            if abs(delta_right) <= threshold:
                y_ab = (max(t_a.top(), t_b.top()) + min(t_a.bottom(), t_b.bottom())) / 2.0
                y_bm = (max(t_b.top(), moving_rect.top()) + min(t_b.bottom(), moving_rect.bottom())) / 2.0
                badges = SmartSpacingEngine._create_h_spacing_badges(
                    [
                        (t_a.right(), t_b.left(), y_ab, gap_ab),
                        (t_b.right(), desired_x_right, y_bm, gap_ab),
                    ],
                    unit=unit,
                    dpi=dpi,
                )
                candidates.append((abs(delta_right), delta_right, badges))

            # Case: M placed to the left of A (M -> A -> B)
            desired_x_left = t_a.left() - gap_ab - moving_rect.width()
            delta_left = desired_x_left - moving_rect.left()
            if abs(delta_left) <= threshold:
                y_ab = (max(t_a.top(), t_b.top()) + min(t_a.bottom(), t_b.bottom())) / 2.0
                y_ma = (max(moving_rect.top(), t_a.top()) + min(moving_rect.bottom(), t_a.bottom())) / 2.0
                badges = SmartSpacingEngine._create_h_spacing_badges(
                    [
                        (desired_x_left + moving_rect.width(), t_a.left(), y_ma, gap_ab),
                        (t_a.right(), t_b.left(), y_ab, gap_ab),
                    ],
                    unit=unit,
                    dpi=dpi,
                )
                candidates.append((abs(delta_left), delta_left, badges))

        if not candidates:
            return None

        # Pick candidate with smallest delta error
        candidates.sort(key=lambda c: c[0])
        best_abs, best_delta, badges = candidates[0]
        return best_delta, badges, []

    @staticmethod
    def detect_vertical_spacing(
        moving_rect: QRectF,
        targets: List[QRectF],
        threshold: float,
        unit: str = "px",
        dpi: int = 300,
    ) -> Optional[Tuple[float, List[SpacingBadge], List[GuideLine]]]:
        """Detect if moving_rect can snap to equal vertical spacing between/adjacent to targets."""
        if len(targets) < 1:
            return None

        m_left = moving_rect.left()
        m_right = moving_rect.right()
        m_w = moving_rect.width()

        band_targets = []
        for t in targets:
            overlap = min(m_right, t.right()) - max(m_left, t.left())
            if overlap >= -max(30.0, m_w * 0.5):
                band_targets.append(t)

        if not band_targets:
            return None

        candidates: List[Tuple[float, float, List[SpacingBadge]]] = []
        sorted_targets = sorted(band_targets, key=lambda r: r.top())

        # 1. Between pairs
        for i in range(len(sorted_targets) - 1):
            t_a = sorted_targets[i]
            t_b = sorted_targets[i + 1]
            if t_a.bottom() >= t_b.top():
                continue
            total_gap = t_b.top() - t_a.bottom()
            if total_gap > moving_rect.height():
                equal_gap = (total_gap - moving_rect.height()) / 2.0
                if equal_gap >= 2.0:
                    desired_y = t_a.bottom() + equal_gap
                    delta = desired_y - moving_rect.top()
                    if abs(delta) <= threshold:
                        x_mid = (max(t_a.left(), moving_rect.left()) + min(t_a.right(), moving_rect.right())) / 2.0
                        badges = SmartSpacingEngine._create_v_spacing_badges(
                            [
                                (t_a.bottom(), desired_y, x_mid, equal_gap),
                                (desired_y + moving_rect.height(), t_b.top(), x_mid, equal_gap),
                            ],
                            unit=unit,
                            dpi=dpi,
                        )
                        candidates.append((abs(delta), delta, badges))

        # 2. Adjacent pairs (A -> B -> M  or  M -> A -> B)
        for i in range(len(sorted_targets) - 1):
            t_a = sorted_targets[i]
            t_b = sorted_targets[i + 1]
            if t_a.bottom() >= t_b.top():
                continue
            gap_ab = t_b.top() - t_a.bottom()
            if gap_ab < 2.0:
                continue

            # M placed below B (A -> B -> M)
            desired_y_bottom = t_b.bottom() + gap_ab
            delta_bottom = desired_y_bottom - moving_rect.top()
            if abs(delta_bottom) <= threshold:
                x_ab = (max(t_a.left(), t_b.left()) + min(t_a.right(), t_b.right())) / 2.0
                x_bm = (max(t_b.left(), moving_rect.left()) + min(t_b.right(), moving_rect.right())) / 2.0
                badges = SmartSpacingEngine._create_v_spacing_badges(
                    [
                        (t_a.bottom(), t_b.top(), x_ab, gap_ab),
                        (t_b.bottom(), desired_y_bottom, x_bm, gap_ab),
                    ],
                    unit=unit,
                    dpi=dpi,
                )
                candidates.append((abs(delta_bottom), delta_bottom, badges))

            # M placed above A (M -> A -> B)
            desired_y_top = t_a.top() - gap_ab - moving_rect.height()
            delta_top = desired_y_top - moving_rect.top()
            if abs(delta_top) <= threshold:
                x_ab = (max(t_a.left(), t_b.left()) + min(t_a.right(), t_b.right())) / 2.0
                x_ma = (max(moving_rect.left(), t_a.left()) + min(moving_rect.right(), t_a.right())) / 2.0
                badges = SmartSpacingEngine._create_v_spacing_badges(
                    [
                        (desired_y_top + moving_rect.height(), t_a.top(), x_ma, gap_ab),
                        (t_a.bottom(), t_b.top(), x_ab, gap_ab),
                    ],
                    unit=unit,
                    dpi=dpi,
                )
                candidates.append((abs(delta_top), delta_top, badges))

        if not candidates:
            return None

        candidates.sort(key=lambda c: c[0])
        best_abs, best_delta, badges = candidates[0]
        return best_delta, badges, []

    @staticmethod
    def _create_h_spacing_badges(
        spans: List[Tuple[float, float, float, float]], unit: str = "px", dpi: int = 300
    ) -> List[SpacingBadge]:
        badges = []
        for x_start, x_end, y, dist in spans:
            x1 = min(x_start, x_end)
            x2 = max(x_start, x_end)
            tick1 = (QPointF(x1, y - 5), QPointF(x1, y + 5))
            tick2 = (QPointF(x2, y - 5), QPointF(x2, y + 5))
            text = format_distance(dist, unit, dpi)
            badges.append(
                SpacingBadge(
                    axis="x",
                    distance=dist,
                    p1=QPointF(x1, y),
                    p2=QPointF(x2, y),
                    marker_lines=[tick1, tick2],
                    badge_text=text,
                )
            )
        return badges

    @staticmethod
    def _create_v_spacing_badges(
        spans: List[Tuple[float, float, float, float]], unit: str = "px", dpi: int = 300
    ) -> List[SpacingBadge]:
        badges = []
        for y_start, y_end, x, dist in spans:
            y1 = min(y_start, y_end)
            y2 = max(y_start, y_end)
            tick1 = (QPointF(x - 5, y1), QPointF(x + 5, y1))
            tick2 = (QPointF(x - 5, y2), QPointF(x + 5, y2))
            text = format_distance(dist, unit, dpi)
            badges.append(
                SpacingBadge(
                    axis="y",
                    distance=dist,
                    p1=QPointF(x, y1),
                    p2=QPointF(x, y2),
                    marker_lines=[tick1, tick2],
                    badge_text=text,
                )
            )
        return badges


class SmartAlignmentEngine:
    """Core calculation engine for edge, center, canvas, and distribution snapping."""

    def __init__(self, settings: Optional[SnapSettings] = None):
        self.settings = settings or SnapSettings()

    def snap_move(
        self,
        moving_rect: QRectF,
        targets: List[QRectF],
        canvas_rect: Optional[QRectF] = None,
        zoom_factor: float = 1.0,
        bypass_snap: bool = False,
    ) -> SnapResult:
        """Calculate magnetic snap correction and temporary guides for moving rect.
        
        Args:
            moving_rect: Bounding box of moving element or multi-selection in scene coordinates.
            targets: Reference bounding boxes of unselected visible elements.
            canvas_rect: Canvas boundary (0, 0, width, height), if enabled.
            zoom_factor: Current canvas viewport zoom level.
            bypass_snap: True if modifier (e.g. Alt) is held to disable snapping.
        """
        if bypass_snap or not (self.settings.object_snapping_enabled or self.settings.smart_guides_enabled):
            return SnapResult(
                snapped_x=moving_rect.left(),
                snapped_y=moving_rect.top(),
                delta_x=0.0,
                delta_y=0.0,
            )

        threshold = self.settings.get_scene_threshold(zoom_factor)

        # 1. Horizontal Snapping (X-axis)
        delta_x, guides_x, badges_x = self._calculate_axis_snap(
            axis="x",
            moving_rect=moving_rect,
            targets=targets,
            canvas_rect=canvas_rect,
            threshold=threshold,
        )

        # 2. Vertical Snapping (Y-axis)
        delta_y, guides_y, badges_y = self._calculate_axis_snap(
            axis="y",
            moving_rect=moving_rect,
            targets=targets,
            canvas_rect=canvas_rect,
            threshold=threshold,
        )

        # If object snapping is disabled but smart guides is enabled, guides are computed but delta is 0
        if not self.settings.object_snapping_enabled:
            delta_x = 0.0
            delta_y = 0.0

        all_guides = []
        all_badges = []
        if self.settings.smart_guides_enabled:
            all_guides = guides_x + guides_y
            all_badges = badges_x + badges_y

        return SnapResult(
            snapped_x=moving_rect.left() + delta_x,
            snapped_y=moving_rect.top() + delta_y,
            delta_x=delta_x,
            delta_y=delta_y,
            guides=all_guides,
            spacing_badges=all_badges,
            has_horizontal_snap=abs(delta_x) > 1e-6,
            has_vertical_snap=abs(delta_y) > 1e-6,
        )

    def snap_resize(
        self,
        handle: int,
        start_rect_scene: QRectF,
        proposed_rect_scene: QRectF,
        targets: List[QRectF],
        canvas_rect: Optional[QRectF] = None,
        zoom_factor: float = 1.0,
        keep_aspect: bool = False,
        bypass_snap: bool = False,
    ) -> Tuple[QRectF, SnapResult]:
        """Snap element edges and corners during interactive resize.
        
        Handles:
            0: TL, 1: T, 2: TR, 3: R, 4: BR, 5: B, 6: BL, 7: L
        """
        if bypass_snap or not (self.settings.object_snapping_enabled or self.settings.smart_guides_enabled):
            return proposed_rect_scene, SnapResult(delta_x=0.0, delta_y=0.0)

        threshold = self.settings.get_scene_threshold(zoom_factor)
        snapped_rect = QRectF(proposed_rect_scene)
        guides: List[GuideLine] = []

        # Determine which edges are active
        modifies_left = handle in (0, 6, 7)
        modifies_right = handle in (2, 3, 4)
        modifies_top = handle in (0, 1, 2)
        modifies_bottom = handle in (4, 5, 6)

        # 1. Snap X edge if applicable
        if modifies_left:
            delta_x, g_list = self._find_single_edge_snap(
                snapped_rect.left(),
                "left",
                snapped_rect,
                targets,
                canvas_rect,
                threshold,
                is_x=True,
            )
            if delta_x != 0.0 and self.settings.object_snapping_enabled:
                new_left = snapped_rect.left() + delta_x
                if start_rect_scene.right() - new_left >= 10.0:
                    snapped_rect.setLeft(new_left)
                    guides.extend(g_list)
            elif g_list:
                guides.extend(g_list)

        elif modifies_right:
            delta_x, g_list = self._find_single_edge_snap(
                snapped_rect.right(),
                "right",
                snapped_rect,
                targets,
                canvas_rect,
                threshold,
                is_x=True,
            )
            if delta_x != 0.0 and self.settings.object_snapping_enabled:
                new_right = snapped_rect.right() + delta_x
                if new_right - start_rect_scene.left() >= 10.0:
                    snapped_rect.setRight(new_right)
                    guides.extend(g_list)
            elif g_list:
                guides.extend(g_list)

        # 2. Snap Y edge if applicable
        if modifies_top:
            delta_y, g_list = self._find_single_edge_snap(
                snapped_rect.top(),
                "top",
                snapped_rect,
                targets,
                canvas_rect,
                threshold,
                is_x=False,
            )
            if delta_y != 0.0 and self.settings.object_snapping_enabled:
                new_top = snapped_rect.top() + delta_y
                if start_rect_scene.bottom() - new_top >= 10.0:
                    snapped_rect.setTop(new_top)
                    guides.extend(g_list)
            elif g_list:
                guides.extend(g_list)

        elif modifies_bottom:
            delta_y, g_list = self._find_single_edge_snap(
                snapped_rect.bottom(),
                "bottom",
                snapped_rect,
                targets,
                canvas_rect,
                threshold,
                is_x=False,
            )
            if delta_y != 0.0 and self.settings.object_snapping_enabled:
                new_bottom = snapped_rect.bottom() + delta_y
                if new_bottom - start_rect_scene.top() >= 10.0:
                    snapped_rect.setBottom(new_bottom)
                    guides.extend(g_list)
            elif g_list:
                guides.extend(g_list)

        # Aspect ratio preservation
        if keep_aspect and start_rect_scene.width() > 0 and start_rect_scene.height() > 0:
            aspect = start_rect_scene.width() / start_rect_scene.height()
            if handle in (0, 2, 4, 6):  # Corner handles
                new_w = snapped_rect.width()
                new_h = new_w / aspect
                if modifies_top:
                    snapped_rect.setTop(snapped_rect.bottom() - new_h)
                else:
                    snapped_rect.setBottom(snapped_rect.top() + new_h)

        # Filter guides if disabled
        active_guides = guides if self.settings.smart_guides_enabled else []

        snap_res = SnapResult(
            guides=active_guides,
            has_horizontal_snap=snapped_rect.left() != proposed_rect_scene.left() or snapped_rect.right() != proposed_rect_scene.right(),
            has_vertical_snap=snapped_rect.top() != proposed_rect_scene.top() or snapped_rect.bottom() != proposed_rect_scene.bottom(),
        )
        return snapped_rect, snap_res

    def _calculate_axis_snap(
        self,
        axis: str,
        moving_rect: QRectF,
        targets: List[QRectF],
        canvas_rect: Optional[QRectF],
        threshold: float,
    ) -> Tuple[float, List[GuideLine], List[SpacingBadge]]:
        """Calculate best snap delta and guides along a single axis ('x' or 'y')."""
        is_x = axis == "x"

        # Moving coordinates
        if is_x:
            m_coords = [
                (moving_rect.left(), "left"),
                (moving_rect.center().x(), "center"),
                (moving_rect.right(), "right"),
            ]
        else:
            m_coords = [
                (moving_rect.top(), "top"),
                (moving_rect.center().y(), "center"),
                (moving_rect.bottom(), "bottom"),
            ]

        # Candidate alignment pairs: (abs_delta, delta, target_val, target_type, target_rect_or_none)
        candidates: List[Tuple[float, float, float, str, Optional[QRectF]]] = []

        # Target elements
        for t in targets:
            if is_x:
                t_lines = [(t.left(), "left"), (t.center().x(), "center"), (t.right(), "right")]
            else:
                t_lines = [(t.top(), "top"), (t.center().y(), "center"), (t.bottom(), "bottom")]

            for m_val, m_type in m_coords:
                for t_val, t_type in t_lines:
                    if m_type == "center" and t_type != "center":
                        continue
                    diff = t_val - m_val
                    if abs(diff) <= threshold:
                        candidates.append((abs(diff), diff, t_val, f"{m_type}_{t_type}", t))

        # Canvas bounds & center
        if self.settings.snap_to_canvas_enabled and canvas_rect is not None:
            if is_x:
                c_lines = [
                    (canvas_rect.left(), "canvas_left"),
                    (canvas_rect.center().x(), "canvas_center"),
                    (canvas_rect.right(), "canvas_right"),
                ]
            else:
                c_lines = [
                    (canvas_rect.top(), "canvas_top"),
                    (canvas_rect.center().y(), "canvas_center"),
                    (canvas_rect.bottom(), "canvas_bottom"),
                ]

            for m_val, m_type in m_coords:
                for c_val, c_type in c_lines:
                    if m_type == "center" and "center" not in c_type:
                        continue
                    diff = c_val - m_val
                    if abs(diff) <= threshold:
                        candidates.append((abs(diff), diff, c_val, c_type, None))

        # Grid lines
        if self.settings.snap_to_grid_enabled and self.settings.grid_size > 0:
            gs = self.settings.grid_size
            for m_val, m_type in m_coords:
                nearest_grid = round(m_val / gs) * gs
                diff = nearest_grid - m_val
                if abs(diff) <= threshold:
                    candidates.append((abs(diff), diff, nearest_grid, "grid", None))

        # Check Equal Spacing candidates
        spacing_delta = None
        spacing_badges = []
        if self.settings.smart_spacing_enabled:
            if is_x:
                res = SmartSpacingEngine.detect_horizontal_spacing(
                    moving_rect, targets, threshold, unit=self.settings.unit, dpi=self.settings.dpi
                )
            else:
                res = SmartSpacingEngine.detect_vertical_spacing(
                    moving_rect, targets, threshold, unit=self.settings.unit, dpi=self.settings.dpi
                )
            if res is not None:
                spacing_delta, spacing_badges, _ = res

        # Compare Spacing vs Edge Alignment
        best_delta = 0.0
        best_abs = float("inf")
        winning_candidates = []

        if candidates:
            candidates.sort(key=lambda c: c[0])
            best_abs = candidates[0][0]
            best_delta = candidates[0][1]

        # If spacing is closer or edge candidates are empty
        if spacing_delta is not None and (not candidates or abs(spacing_delta) < best_abs):
            best_delta = spacing_delta
            return best_delta, [], spacing_badges

        # Otherwise edge candidates win
        if not candidates:
            return 0.0, [], []

        # Find all candidates matching best_delta within small tolerance to create complete guide lines
        winning_candidates = [c for c in candidates if abs(c[1] - best_delta) < 1e-4]

        # Generate guide lines for winning alignments
        guides = self._create_guide_lines(
            is_x=is_x,
            best_delta=best_delta,
            moving_rect=moving_rect,
            winning_candidates=winning_candidates,
            canvas_rect=canvas_rect,
        )

        return best_delta, guides, []

    def _find_single_edge_snap(
        self,
        edge_val: float,
        edge_name: str,
        current_rect: QRectF,
        targets: List[QRectF],
        canvas_rect: Optional[QRectF],
        threshold: float,
        is_x: bool,
    ) -> Tuple[float, List[GuideLine]]:
        """Snap a specific moving edge during resize."""
        candidates = []

        # Target elements
        for t in targets:
            if is_x:
                t_lines = [(t.left(), "left"), (t.center().x(), "center"), (t.right(), "right")]
            else:
                t_lines = [(t.top(), "top"), (t.center().y(), "center"), (t.bottom(), "bottom")]

            for t_val, t_type in t_lines:
                diff = t_val - edge_val
                if abs(diff) <= threshold:
                    candidates.append((abs(diff), diff, t_val, t))

        # Canvas bounds & center
        if self.settings.snap_to_canvas_enabled and canvas_rect is not None:
            if is_x:
                c_lines = [
                    (canvas_rect.left(), "canvas_left"),
                    (canvas_rect.center().x(), "canvas_center"),
                    (canvas_rect.right(), "canvas_right"),
                ]
            else:
                c_lines = [
                    (canvas_rect.top(), "canvas_top"),
                    (canvas_rect.center().y(), "canvas_center"),
                    (canvas_rect.bottom(), "canvas_bottom"),
                ]

            for c_val, c_type in c_lines:
                diff = c_val - edge_val
                if abs(diff) <= threshold:
                    candidates.append((abs(diff), diff, c_val, None))

        if not candidates:
            return 0.0, []

        candidates.sort(key=lambda c: c[0])
        best_abs, best_delta, target_val, target_rect = candidates[0]

        # Create guide line
        guides = []
        if is_x:
            snapped_x = edge_val + best_delta
            labels: List[GuideLabel] = []
            if target_rect is not None:
                y1 = min(current_rect.top(), target_rect.top()) - 10.0
                y2 = max(current_rect.bottom(), target_rect.bottom()) + 10.0
                sorted_r = sorted([current_rect, target_rect], key=lambda r: r.top())
                gap = sorted_r[1].top() - sorted_r[0].bottom()
                if gap >= 2.0:
                    y_mid = (sorted_r[0].bottom() + sorted_r[1].top()) / 2.0
                    txt = format_distance(gap, self.settings.unit, self.settings.dpi)
                    labels.append(GuideLabel(pos=QPointF(snapped_x, y_mid), text=txt, distance_px=gap))
            elif canvas_rect is not None:
                y1 = canvas_rect.top()
                y2 = canvas_rect.bottom()
                gap_top = current_rect.top() - canvas_rect.top()
                if gap_top >= 2.0:
                    y_mid = (canvas_rect.top() + current_rect.top()) / 2.0
                    txt = format_distance(gap_top, self.settings.unit, self.settings.dpi)
                    labels.append(GuideLabel(pos=QPointF(snapped_x, y_mid), text=txt, distance_px=gap_top))
                gap_bottom = canvas_rect.bottom() - current_rect.bottom()
                if gap_bottom >= 2.0:
                    y_mid = (current_rect.bottom() + canvas_rect.bottom()) / 2.0
                    txt = format_distance(gap_bottom, self.settings.unit, self.settings.dpi)
                    labels.append(GuideLabel(pos=QPointF(snapped_x, y_mid), text=txt, distance_px=gap_bottom))
            else:
                y1 = current_rect.top() - 50.0
                y2 = current_rect.bottom() + 50.0

            dist_text = labels[0].text if labels else None
            dist_pos = labels[0].pos if labels else None

            guides.append(
                GuideLine(
                    p1=QPointF(snapped_x, y1),
                    p2=QPointF(snapped_x, y2),
                    guide_type=GuideType.ALIGN_LEFT if edge_name == "left" else GuideType.ALIGN_RIGHT,
                    color=self.settings.guide_color,
                    labels=labels,
                    distance_text=dist_text,
                    distance_pos=dist_pos,
                )
            )
        else:
            snapped_y = edge_val + best_delta
            labels: List[GuideLabel] = []
            if target_rect is not None:
                x1 = min(current_rect.left(), target_rect.left()) - 10.0
                x2 = max(current_rect.right(), target_rect.right()) + 10.0
                sorted_r = sorted([current_rect, target_rect], key=lambda r: r.left())
                gap = sorted_r[1].left() - sorted_r[0].right()
                if gap >= 2.0:
                    x_mid = (sorted_r[0].right() + sorted_r[1].left()) / 2.0
                    txt = format_distance(gap, self.settings.unit, self.settings.dpi)
                    labels.append(GuideLabel(pos=QPointF(x_mid, snapped_y), text=txt, distance_px=gap))
            elif canvas_rect is not None:
                x1 = canvas_rect.left()
                x2 = canvas_rect.right()
                gap_left = current_rect.left() - canvas_rect.left()
                if gap_left >= 2.0:
                    x_mid = (canvas_rect.left() + current_rect.left()) / 2.0
                    txt = format_distance(gap_left, self.settings.unit, self.settings.dpi)
                    labels.append(GuideLabel(pos=QPointF(x_mid, snapped_y), text=txt, distance_px=gap_left))
                gap_right = canvas_rect.right() - current_rect.right()
                if gap_right >= 2.0:
                    x_mid = (current_rect.right() + canvas_rect.right()) / 2.0
                    txt = format_distance(gap_right, self.settings.unit, self.settings.dpi)
                    labels.append(GuideLabel(pos=QPointF(x_mid, snapped_y), text=txt, distance_px=gap_right))
            else:
                x1 = current_rect.left() - 50.0
                x2 = current_rect.right() + 50.0

            dist_text = labels[0].text if labels else None
            dist_pos = labels[0].pos if labels else None

            guides.append(
                GuideLine(
                    p1=QPointF(x1, snapped_y),
                    p2=QPointF(x2, snapped_y),
                    guide_type=GuideType.ALIGN_TOP if edge_name == "top" else GuideType.ALIGN_BOTTOM,
                    color=self.settings.guide_color,
                    labels=labels,
                    distance_text=dist_text,
                    distance_pos=dist_pos,
                )
            )

        return best_delta, guides

    def _create_guide_lines(
        self,
        is_x: bool,
        best_delta: float,
        moving_rect: QRectF,
        winning_candidates: List[Tuple[float, float, float, str, Optional[QRectF]]],
        canvas_rect: Optional[QRectF],
    ) -> List[GuideLine]:
        """Construct crisp guide lines spanning all aligned elements with boundary distance badges."""
        guides: List[GuideLine] = []
        # Group candidates by alignment line coordinate
        grouped_by_coord: Dict[float, List[Tuple[str, Optional[QRectF]]]] = {}
        for _, _, coord, c_type, t_rect in winning_candidates:
            grouped_by_coord.setdefault(coord, []).append((c_type, t_rect))

        m_snapped = moving_rect.translated(best_delta, 0) if is_x else moving_rect.translated(0, best_delta)

        for coord, items in grouped_by_coord.items():
            is_canvas = any("canvas" in it[0] for it in items)
            is_center = any("center" in it[0] for it in items)
            participating_rects = [m_snapped] + [r for _, r in items if r is not None]

            # De-duplicate participating rects
            unique_rects: List[QRectF] = []
            for r in participating_rects:
                if not any(
                    abs(r.left() - u.left()) < 1e-3
                    and abs(r.top() - u.top()) < 1e-3
                    and abs(r.width() - u.width()) < 1e-3
                    and abs(r.height() - u.height()) < 1e-3
                    for u in unique_rects
                ):
                    unique_rects.append(r)

            labels: List[GuideLabel] = []

            if is_x:
                if is_canvas and canvas_rect is not None:
                    y1 = canvas_rect.top()
                    y2 = canvas_rect.bottom()
                    g_type = GuideType.CANVAS_CENTER_X if is_center else GuideType.CANVAS_EDGE_X
                else:
                    y1 = min(r.top() for r in unique_rects) - 8.0
                    y2 = max(r.bottom() for r in unique_rects) + 8.0
                    g_type = GuideType.ALIGN_CENTER_X if is_center else GuideType.ALIGN_LEFT

                sorted_rects = sorted(unique_rects, key=lambda r: r.top())

                for i in range(len(sorted_rects) - 1):
                    r_a = sorted_rects[i]
                    r_b = sorted_rects[i + 1]
                    gap = r_b.top() - r_a.bottom()
                    if gap >= 2.0:
                        y_mid = (r_a.bottom() + r_b.top()) / 2.0
                        txt = format_distance(gap, self.settings.unit, self.settings.dpi)
                        labels.append(GuideLabel(pos=QPointF(coord, y_mid), text=txt, distance_px=gap))

                if is_canvas and canvas_rect is not None and sorted_rects:
                    gap_top = sorted_rects[0].top() - canvas_rect.top()
                    if gap_top >= 2.0:
                        y_mid = (canvas_rect.top() + sorted_rects[0].top()) / 2.0
                        txt = format_distance(gap_top, self.settings.unit, self.settings.dpi)
                        labels.append(GuideLabel(pos=QPointF(coord, y_mid), text=txt, distance_px=gap_top))

                    gap_bottom = canvas_rect.bottom() - sorted_rects[-1].bottom()
                    if gap_bottom >= 2.0:
                        y_mid = (sorted_rects[-1].bottom() + canvas_rect.bottom()) / 2.0
                        txt = format_distance(gap_bottom, self.settings.unit, self.settings.dpi)
                        labels.append(GuideLabel(pos=QPointF(coord, y_mid), text=txt, distance_px=gap_bottom))

                dist_text = labels[0].text if labels else None
                dist_pos = labels[0].pos if labels else None

                guides.append(
                    GuideLine(
                        p1=QPointF(coord, y1),
                        p2=QPointF(coord, y2),
                        guide_type=g_type,
                        color=self.settings.guide_color,
                        is_center=is_center,
                        labels=labels,
                        distance_text=dist_text,
                        distance_pos=dist_pos,
                    )
                )
            else:
                if is_canvas and canvas_rect is not None:
                    x1 = canvas_rect.left()
                    x2 = canvas_rect.right()
                    g_type = GuideType.CANVAS_CENTER_Y if is_center else GuideType.CANVAS_EDGE_Y
                else:
                    x1 = min(r.left() for r in unique_rects) - 8.0
                    x2 = max(r.right() for r in unique_rects) + 8.0
                    g_type = GuideType.ALIGN_CENTER_Y if is_center else GuideType.ALIGN_TOP

                sorted_rects = sorted(unique_rects, key=lambda r: r.left())

                for i in range(len(sorted_rects) - 1):
                    r_a = sorted_rects[i]
                    r_b = sorted_rects[i + 1]
                    gap = r_b.left() - r_a.right()
                    if gap >= 2.0:
                        x_mid = (r_a.right() + r_b.left()) / 2.0
                        txt = format_distance(gap, self.settings.unit, self.settings.dpi)
                        labels.append(GuideLabel(pos=QPointF(x_mid, coord), text=txt, distance_px=gap))

                if is_canvas and canvas_rect is not None and sorted_rects:
                    gap_left = sorted_rects[0].left() - canvas_rect.left()
                    if gap_left >= 2.0:
                        x_mid = (canvas_rect.left() + sorted_rects[0].left()) / 2.0
                        txt = format_distance(gap_left, self.settings.unit, self.settings.dpi)
                        labels.append(GuideLabel(pos=QPointF(x_mid, coord), text=txt, distance_px=gap_left))

                    gap_right = canvas_rect.right() - sorted_rects[-1].right()
                    if gap_right >= 2.0:
                        x_mid = (sorted_rects[-1].right() + canvas_rect.right()) / 2.0
                        txt = format_distance(gap_right, self.settings.unit, self.settings.dpi)
                        labels.append(GuideLabel(pos=QPointF(x_mid, coord), text=txt, distance_px=gap_right))

                dist_text = labels[0].text if labels else None
                dist_pos = labels[0].pos if labels else None

                guides.append(
                    GuideLine(
                        p1=QPointF(x1, coord),
                        p2=QPointF(x2, coord),
                        guide_type=g_type,
                        color=self.settings.guide_color,
                        is_center=is_center,
                        labels=labels,
                        distance_text=dist_text,
                        distance_pos=dist_pos,
                    )
                )

        return guides


class GuideRenderer:
    """Renders temporary Photoshop/Figma-style magenta guides and spacing badges."""

    @staticmethod
    def render(
        painter: QPainter,
        guides: List[GuideLine],
        spacing_badges: List[SpacingBadge],
        zoom_factor: float = 1.0,
    ) -> None:
        """Render alignment lines and equal-spacing indicators using high-contrast crisp cosmetics."""
        if not guides and not spacing_badges:
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        zf = max(0.05, zoom_factor)

        # 1. Render smart guide lines
        for g in guides:
            pen = QPen(QColor(g.color), 1.2)
            pen.setCosmetic(True)  # Crisp 1.2px on all zoom levels
            if g.is_center:
                # Subtle dashed line for center axis guides
                pen.setStyle(Qt.CustomDashLine)
                pen.setDashPattern([5, 3])
            else:
                pen.setStyle(Qt.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawLine(g.p1, g.p2)

        # 2. Render guide line distance badges in the middle of guide lines between boundaries
        for g in guides:
            labels_to_draw = list(getattr(g, "labels", []))
            if not labels_to_draw and getattr(g, "distance_text", None) and getattr(g, "distance_pos", None):
                labels_to_draw.append(GuideLabel(pos=g.distance_pos, text=g.distance_text))

            for lbl in labels_to_draw:
                mid_x = lbl.pos.x()
                mid_y = lbl.pos.y()

                font = QFont("Segoe UI", max(7, int(9 / zf)))
                font.setBold(True)
                painter.setFont(font)
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(lbl.text) + (8.0 / zf)
                th = fm.height() + (4.0 / zf)

                badge_rect = QRectF(mid_x - tw / 2.0, mid_y - th / 2.0, tw, th)

                # Pill background
                painter.setPen(QPen(QColor(255, 255, 255, 220), 0.75 / zf))
                painter.setBrush(QBrush(QColor(g.color or "#FF2D9A")))
                radius = 3.0 / zf
                painter.drawRoundedRect(badge_rect, radius, radius)

                # Text
                painter.setPen(QColor("#FFFFFF"))
                painter.drawText(badge_rect, Qt.AlignCenter, lbl.text)

        # 2. Render spacing dimension lines & badges
        for badge in spacing_badges:
            # Dimension gap line
            pen = QPen(QColor("#FF2D9A"), 1.2)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawLine(badge.p1, badge.p2)

            # End tick marks
            for tp1, tp2 in badge.marker_lines:
                painter.drawLine(tp1, tp2)

            # Pill Badge
            mid_x = (badge.p1.x() + badge.p2.x()) / 2.0
            mid_y = (badge.p1.y() + badge.p2.y()) / 2.0

            font = QFont("Segoe UI", max(7, int(9 / zf)))
            font.setBold(True)
            painter.setFont(font)
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(badge.badge_text) + (10.0 / zf)
            th = fm.height() + (4.0 / zf)

            badge_rect = QRectF(mid_x - tw / 2.0, mid_y - th / 2.0, tw, th)

            # Pill background
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor("#FF2D9A")))
            radius = 3.0 / zf
            painter.drawRoundedRect(badge_rect, radius, radius)

            # Text
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(badge_rect, Qt.AlignCenter, badge.badge_text)

        painter.restore()
