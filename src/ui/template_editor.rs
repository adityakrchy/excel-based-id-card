//! Photoshop-inspired template editor widget with vertical toolbox, interactive rulers,
//! contextual top options bar, Photoshop dual color swatches, TBox transform box with 8 bidirectional
//! resize handles, custom designed tool cursors (magnifier, shapes, brush ring, paint bucket, eraser),
//! live shape preview, and docking panels (Properties, Layers, Swatches, History, Align).

use eframe::egui::{
    self, Align2, Color32, CursorIcon, FontId, Id, PointerButton, Pos2, Rect, Response, Sense,
    Stroke, Ui, Vec2,
};
use uuid::Uuid;

use crate::data::models::{CanvasElement, CanvasElementStyle, TemplateDefinition};
use crate::ui::new_canvas_dialog::CanvasUnit;

const MIN_ZOOM: f32 = 0.1;
const MAX_ZOOM: f32 = 4.0;
const RULER_THICKNESS: f32 = 22.0;
const HANDLE_SIZE: f32 = 8.0;

/// Curated 24-color ID badge palette inspired by professional badge design systems.
pub const SWATCHES: &[(&str, &str)] = &[
    ("#0F172A", "Deep Midnight"),
    ("#1E293B", "Slate 800"),
    ("#1E3A8A", "Navy Blue"),
    ("#1D4ED8", "Royal Blue"),
    ("#2563EB", "Corporate Blue"),
    ("#0284C7", "Sky Blue"),
    ("#06B6D4", "Cyan Accent"),
    ("#0D9488", "Teal"),
    ("#064E3B", "Dark Emerald"),
    ("#059669", "Emerald Green"),
    ("#10B981", "Bright Green"),
    ("#84CC16", "Lime"),
    ("#78350F", "Bronze"),
    ("#B45309", "Dark Amber"),
    ("#D97706", "Amber Gold"),
    ("#F59E0B", "Warning Yellow"),
    ("#DC2626", "Crimson Red"),
    ("#BE123C", "Ruby Accent"),
    ("#E11D48", "Rose"),
    ("#7C3AED", "Purple"),
    ("#000000", "Pitch Black"),
    ("#475569", "Slate Gray"),
    ("#94A3B8", "Silver"),
    ("#FFFFFF", "Pure White"),
];

/// Major Photoshop-style editing tools.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum EditorTool {
    #[default]
    Move, // V: Move & Transform (TBox)
    Marquee,      // M: Rectangular marquee selection
    ObjectSelect, // W: Quick object selection
    Crop,         // C: Canvas crop tool
    Eyedropper,   // I: Color picker / sampler
    Brush,        // B: Brush tool
    Eraser,       // E: Eraser tool
    Gradient,     // G: Gradient fill tool
    PaintBucket,  // K: Paint bucket fill tool
    Text,         // T: Text tool
    Shape,        // U: Shape tool (Rectangle, Circle, Line)
    Hand,         // H: Hand / pan tool
    Zoom,         // Z: Zoom tool
}

impl EditorTool {
    pub fn name(self) -> &'static str {
        match self {
            Self::Move => "Move Tool (V)",
            Self::Marquee => "Marquee Tool (M)",
            Self::ObjectSelect => "Object Selection Tool (W)",
            Self::Crop => "Crop Tool (C)",
            Self::Eyedropper => "Eyedropper Tool (I)",
            Self::Brush => "Brush Tool (B)",
            Self::Eraser => "Eraser Tool (E)",
            Self::Gradient => "Gradient Tool (G)",
            Self::PaintBucket => "Paint Bucket Tool (K)",
            Self::Text => "Horizontal Type Tool (T)",
            Self::Shape => "Shape Tool (U)",
            Self::Hand => "Hand Tool (H)",
            Self::Zoom => "Zoom Tool (Z)",
        }
    }

    pub fn icon(self) -> &'static str {
        match self {
            Self::Move => "✥",
            Self::Marquee => "⬚",
            Self::ObjectSelect => "⛶",
            Self::Crop => "⯐",
            Self::Eyedropper => "💉",
            Self::Brush => "🖌",
            Self::Eraser => "⌫",
            Self::Gradient => "▨",
            Self::PaintBucket => "🪣",
            Self::Text => "T",
            Self::Shape => "▭",
            Self::Hand => "✋",
            Self::Zoom => "🔍",
        }
    }

    pub fn short_label(self) -> &'static str {
        match self {
            Self::Move => "Move",
            Self::Marquee => "Marq",
            Self::ObjectSelect => "Select",
            Self::Crop => "Crop",
            Self::Eyedropper => "Drop",
            Self::Brush => "Brush",
            Self::Eraser => "Erase",
            Self::Gradient => "Grad",
            Self::PaintBucket => "Bucket",
            Self::Text => "Text",
            Self::Shape => "Shape",
            Self::Hand => "Hand",
            Self::Zoom => "Zoom",
        }
    }

    pub fn shortcut(self) -> &'static str {
        match self {
            Self::Move => "V",
            Self::Marquee => "M",
            Self::ObjectSelect => "W",
            Self::Crop => "C",
            Self::Eyedropper => "I",
            Self::Brush => "B",
            Self::Eraser => "E",
            Self::Gradient => "G",
            Self::PaintBucket => "K",
            Self::Text => "T",
            Self::Shape => "U",
            Self::Hand => "H",
            Self::Zoom => "Z",
        }
    }
}

/// Shape types supported by the Shape Tool (U).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ShapeKind {
    #[default]
    Rectangle,
    RoundedRectangle,
    Ellipse,
    Line,
}

impl ShapeKind {
    pub fn label(self) -> &'static str {
        match self {
            Self::Rectangle => "Rectangle (▭)",
            Self::RoundedRectangle => "Rounded Rect (▢)",
            Self::Ellipse => "Ellipse / Circle (◯)",
            Self::Line => "Line (─)",
        }
    }

    pub fn icon(self) -> &'static str {
        match self {
            Self::Rectangle => "▭",
            Self::RoundedRectangle => "▢",
            Self::Ellipse => "◯",
            Self::Line => "─",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ToolVectorIcon {
    Move,
    Marquee,
    ObjectSelect,
    Crop,
    Eyedropper,
    Brush,
    Eraser,
    Gradient,
    PaintBucket,
    Text,
    Shape(ShapeKind),
    Hand,
    Zoom,
    Fit,
    ActualPixels,
    More,
    DefaultColors,
    SwapColors,
    QuickMask,
    ScreenMode,
}

impl EditorTool {
    pub fn vector_icon(self, active_shape: ShapeKind) -> ToolVectorIcon {
        match self {
            Self::Move => ToolVectorIcon::Move,
            Self::Marquee => ToolVectorIcon::Marquee,
            Self::ObjectSelect => ToolVectorIcon::ObjectSelect,
            Self::Crop => ToolVectorIcon::Crop,
            Self::Eyedropper => ToolVectorIcon::Eyedropper,
            Self::Brush => ToolVectorIcon::Brush,
            Self::Eraser => ToolVectorIcon::Eraser,
            Self::Gradient => ToolVectorIcon::Gradient,
            Self::PaintBucket => ToolVectorIcon::PaintBucket,
            Self::Text => ToolVectorIcon::Text,
            Self::Shape => ToolVectorIcon::Shape(active_shape),
            Self::Hand => ToolVectorIcon::Hand,
            Self::Zoom => ToolVectorIcon::Zoom,
        }
    }
}

/// Draws pixel-perfect procedural vector icons matching Adobe Photoshop.
/// This completely avoids missing OS/font unicode glyphs and renders identically on all platforms.
fn draw_tool_vector_icon(
    painter: &egui::Painter,
    icon: ToolVectorIcon,
    center: Pos2,
    color: Color32,
) {
    let stroke = Stroke::new(1.3_f32, color);

    match icon {
        ToolVectorIcon::Move => {
            // 4-way arrow cross
            let span = 6.0;
            painter.line_segment(
                [center - Vec2::new(span, 0.0), center + Vec2::new(span, 0.0)],
                stroke,
            );
            painter.line_segment(
                [center - Vec2::new(0.0, span), center + Vec2::new(0.0, span)],
                stroke,
            );
            // Left arrowhead
            painter.line_segment(
                [
                    center - Vec2::new(span, 0.0),
                    center - Vec2::new(span - 2.5, 2.5),
                ],
                stroke,
            );
            painter.line_segment(
                [
                    center - Vec2::new(span, 0.0),
                    center - Vec2::new(span - 2.5, -2.5),
                ],
                stroke,
            );
            // Right arrowhead
            painter.line_segment(
                [
                    center + Vec2::new(span, 0.0),
                    center + Vec2::new(span - 2.5, 2.5),
                ],
                stroke,
            );
            painter.line_segment(
                [
                    center + Vec2::new(span, 0.0),
                    center + Vec2::new(span - 2.5, -2.5),
                ],
                stroke,
            );
            // Top arrowhead
            painter.line_segment(
                [
                    center - Vec2::new(0.0, span),
                    center - Vec2::new(2.5, span - 2.5),
                ],
                stroke,
            );
            painter.line_segment(
                [
                    center - Vec2::new(0.0, span),
                    center - Vec2::new(-2.5, span - 2.5),
                ],
                stroke,
            );
            // Bottom arrowhead
            painter.line_segment(
                [
                    center + Vec2::new(0.0, span),
                    center + Vec2::new(2.5, span - 2.5),
                ],
                stroke,
            );
            painter.line_segment(
                [
                    center + Vec2::new(0.0, span),
                    center + Vec2::new(-2.5, span - 2.5),
                ],
                stroke,
            );
        }
        ToolVectorIcon::Marquee => {
            // Dashed selection rectangle
            let half = 5.5;
            let d_len = 3.0;
            let tl = center - Vec2::splat(half);
            let tr = center + Vec2::new(half, -half);
            let bl = center + Vec2::new(-half, half);
            let br = center + Vec2::splat(half);

            painter.line_segment([tl, tl + Vec2::new(d_len, 0.0)], stroke);
            painter.line_segment([tr - Vec2::new(d_len, 0.0), tr], stroke);
            painter.line_segment([bl, bl + Vec2::new(d_len, 0.0)], stroke);
            painter.line_segment([br - Vec2::new(d_len, 0.0), br], stroke);
            painter.line_segment([tl, tl + Vec2::new(0.0, d_len)], stroke);
            painter.line_segment([bl - Vec2::new(0.0, d_len), bl], stroke);
            painter.line_segment([tr, tr + Vec2::new(0.0, d_len)], stroke);
            painter.line_segment([br - Vec2::new(0.0, d_len), br], stroke);
        }
        ToolVectorIcon::ObjectSelect => {
            // Corner brackets with arrow pointer
            let half = 6.0;
            let c_len = 2.5;
            let tl = center - Vec2::splat(half);
            let tr = center + Vec2::new(half, -half);
            let bl = center + Vec2::new(-half, half);
            let br = center + Vec2::splat(half);

            painter.line_segment([tl, tl + Vec2::new(c_len, 0.0)], stroke);
            painter.line_segment([tl, tl + Vec2::new(0.0, c_len)], stroke);

            painter.line_segment([tr, tr - Vec2::new(c_len, 0.0)], stroke);
            painter.line_segment([tr, tr + Vec2::new(0.0, c_len)], stroke);

            painter.line_segment([bl, bl + Vec2::new(c_len, 0.0)], stroke);
            painter.line_segment([bl, bl - Vec2::new(0.0, c_len)], stroke);

            painter.line_segment([br, br - Vec2::new(c_len, 0.0)], stroke);
            painter.line_segment([br, br - Vec2::new(0.0, c_len)], stroke);

            let p_tip = center + Vec2::new(1.0, 1.0);
            let p_top = center + Vec2::new(-2.5, -3.5);
            let p_bot = center + Vec2::new(-3.5, -0.5);
            painter.add(egui::Shape::convex_polygon(
                vec![p_top, p_tip, p_bot],
                color,
                Stroke::NONE,
            ));
        }
        ToolVectorIcon::Crop => {
            // Photoshop crop blades
            let arm = 5.0;
            let ext = 2.5;
            let tl = center - Vec2::splat(arm);
            let br = center + Vec2::splat(arm);
            let c_stroke = Stroke::new(1.4_f32, color);

            painter.line_segment(
                [tl - Vec2::new(ext, 0.0), center + Vec2::new(arm, -arm)],
                c_stroke,
            );
            painter.line_segment(
                [tl - Vec2::new(0.0, ext), center + Vec2::new(-arm, arm)],
                c_stroke,
            );
            painter.line_segment(
                [br + Vec2::new(ext, 0.0), center + Vec2::new(-arm, arm)],
                c_stroke,
            );
            painter.line_segment(
                [br + Vec2::new(0.0, ext), center + Vec2::new(arm, -arm)],
                c_stroke,
            );
        }
        ToolVectorIcon::Eyedropper => {
            // Angled pipette
            let tip = center + Vec2::new(-5.0, 5.0);
            let neck = center + Vec2::new(-3.0, 3.0);
            let barrel_top = center + Vec2::new(2.0, -2.0);
            let bulb = center + Vec2::new(4.5, -4.5);

            painter.line_segment([tip, neck], Stroke::new(1.2_f32, color));

            let normal = Vec2::new(1.8, 1.8);
            let p1 = neck - normal;
            let p2 = barrel_top - normal;
            let p3 = barrel_top + normal;
            let p4 = neck + normal;
            painter.add(egui::Shape::closed_line(
                vec![p1, p2, p3, p4],
                Stroke::new(1.2_f32, color),
            ));

            painter.circle_filled(bulb, 2.2, color);
        }
        ToolVectorIcon::Brush => {
            // Angled paintbrush
            let tip = center + Vec2::new(-5.0, 5.0);
            let ferrule_c = center + Vec2::new(-1.0, 1.0);
            let handle_top = center + Vec2::new(5.0, -5.0);

            painter.line_segment([ferrule_c, handle_top], Stroke::new(2.4_f32, color));

            let perp = Vec2::new(2.2, 2.2);
            painter.line_segment(
                [ferrule_c - perp, ferrule_c + perp],
                Stroke::new(1.5_f32, color),
            );

            painter.add(egui::Shape::convex_polygon(
                vec![ferrule_c - perp * 0.8, tip, ferrule_c + perp * 0.8],
                color,
                Stroke::NONE,
            ));
        }
        ToolVectorIcon::Eraser => {
            // Angled eraser block
            let p1 = center + Vec2::new(-5.0, 1.0);
            let p2 = center + Vec2::new(-1.0, -4.5);
            let p3 = center + Vec2::new(5.0, 0.5);
            let p4 = center + Vec2::new(1.0, 6.0);

            painter.add(egui::Shape::closed_line(
                vec![p1, p2, p3, p4],
                Stroke::new(1.3_f32, color),
            ));

            let m1 = p1 + (p2 - p1) * 0.45;
            let m2 = p4 + (p3 - p4) * 0.45;
            painter.line_segment([m1, m2], Stroke::new(1.1_f32, color));

            painter.add(egui::Shape::convex_polygon(
                vec![p1, m1, m2, p4],
                Color32::from_rgba_unmultiplied(color.r(), color.g(), color.b(), 70),
                Stroke::NONE,
            ));
        }
        ToolVectorIcon::Gradient => {
            // Gradient fill box
            let half = 5.5;
            let rect = Rect::from_center_size(center, Vec2::splat(half * 2.0));
            painter.rect_stroke(rect, 1.0, stroke);

            let w = (rect.width() - 2.0) / 4.0;
            for i in 0..4 {
                let x = rect.left() + 1.0 + i as f32 * w;
                let band = Rect::from_min_size(
                    Pos2::new(x, rect.top() + 1.0),
                    Vec2::new(w, rect.height() - 2.0),
                );
                let alpha = match i {
                    0 => 220,
                    1 => 140,
                    2 => 70,
                    _ => 0,
                };
                if alpha > 0 {
                    painter.rect_filled(
                        band,
                        0.0,
                        Color32::from_rgba_unmultiplied(color.r(), color.g(), color.b(), alpha),
                    );
                }
            }
        }
        ToolVectorIcon::PaintBucket => {
            // Tilted bucket with pouring paint
            let p1 = center + Vec2::new(-4.0, -1.0);
            let p2 = center + Vec2::new(-1.0, -5.0);
            let p3 = center + Vec2::new(3.5, -1.0);
            let p4 = center + Vec2::new(0.0, 3.5);

            painter.add(egui::Shape::closed_line(
                vec![p1, p2, p3, p4],
                Stroke::new(1.3_f32, color),
            ));

            painter.line_segment(
                [center + Vec2::new(0.0, 3.5), center + Vec2::new(2.5, 4.5)],
                Stroke::new(1.3_f32, color),
            );

            painter.circle_filled(center + Vec2::new(4.0, 5.0), 1.4, color);
        }
        ToolVectorIcon::Text => {
            painter.text(
                center,
                Align2::CENTER_CENTER,
                "T",
                FontId::proportional(15.0),
                color,
            );
        }
        ToolVectorIcon::Shape(kind) => match kind {
            ShapeKind::Rectangle => {
                painter.rect_stroke(
                    Rect::from_center_size(center, Vec2::new(13.0, 9.0)),
                    0.0,
                    stroke,
                );
            }
            ShapeKind::RoundedRectangle => {
                painter.rect_stroke(
                    Rect::from_center_size(center, Vec2::new(13.0, 9.0)),
                    2.5,
                    stroke,
                );
            }
            ShapeKind::Ellipse => {
                painter.circle_stroke(center, 5.5, stroke);
            }
            ShapeKind::Line => {
                painter.line_segment(
                    [center - Vec2::new(6.0, 4.0), center + Vec2::new(6.0, 4.0)],
                    stroke,
                );
            }
        },
        ToolVectorIcon::Hand => {
            let palm = Rect::from_center_size(center + Vec2::new(0.0, 2.0), Vec2::new(8.0, 7.0));
            painter.rect_stroke(palm, 2.0, stroke);

            let f_stroke = Stroke::new(1.3_f32, color);
            painter.line_segment(
                [
                    center + Vec2::new(-3.0, -1.0),
                    center + Vec2::new(-3.0, -5.0),
                ],
                f_stroke,
            );
            painter.line_segment(
                [
                    center + Vec2::new(-1.0, -1.0),
                    center + Vec2::new(-1.0, -6.5),
                ],
                f_stroke,
            );
            painter.line_segment(
                [center + Vec2::new(1.0, -1.0), center + Vec2::new(1.0, -6.0)],
                f_stroke,
            );
            painter.line_segment(
                [center + Vec2::new(3.0, -1.0), center + Vec2::new(3.0, -4.5)],
                f_stroke,
            );
            painter.line_segment(
                [center + Vec2::new(-4.0, 1.5), center + Vec2::new(-6.0, 0.0)],
                f_stroke,
            );
        }
        ToolVectorIcon::Zoom => {
            let lens_center = center + Vec2::new(-2.0, -2.0);
            painter.circle_stroke(lens_center, 4.5, Stroke::new(1.4_f32, color));
            painter.line_segment(
                [
                    lens_center + Vec2::new(3.2, 3.2),
                    center + Vec2::new(5.8, 5.8),
                ],
                Stroke::new(2.2_f32, color),
            );
        }
        ToolVectorIcon::Fit => {
            let outer = Rect::from_center_size(center, Vec2::splat(12.0));
            painter.rect_stroke(outer, 1.0, stroke);
            let inner = Rect::from_center_size(center, Vec2::new(7.0, 5.0));
            painter.rect_filled(inner, 0.5, color);
        }
        ToolVectorIcon::ActualPixels => {
            painter.text(
                center,
                Align2::CENTER_CENTER,
                "1:1",
                FontId::proportional(11.0),
                color,
            );
        }
        ToolVectorIcon::More => {
            painter.circle_filled(center + Vec2::new(-4.0, 0.0), 1.2, color);
            painter.circle_filled(center, 1.2, color);
            painter.circle_filled(center + Vec2::new(4.0, 0.0), 1.2, color);
        }
        ToolVectorIcon::DefaultColors => {
            let size = Vec2::splat(6.5);
            let bg = Rect::from_min_size(center + Vec2::new(-1.0, -1.0), size);
            painter.rect_filled(bg, 0.0, Color32::WHITE);
            painter.rect_stroke(bg, 0.0, Stroke::new(1.0_f32, Color32::from_gray(50)));

            let fg = Rect::from_min_size(center + Vec2::new(-5.5, -5.5), size);
            painter.rect_filled(fg, 0.0, Color32::BLACK);
            painter.rect_stroke(fg, 0.0, Stroke::new(1.0_f32, Color32::WHITE));
        }
        ToolVectorIcon::SwapColors => {
            let a_stroke = Stroke::new(1.2_f32, color);
            painter.line_segment(
                [
                    center + Vec2::new(-4.0, -2.5),
                    center + Vec2::new(1.5, -2.5),
                ],
                a_stroke,
            );
            painter.line_segment(
                [center + Vec2::new(1.5, -2.5), center + Vec2::new(4.0, 0.0)],
                a_stroke,
            );
            painter.line_segment(
                [center + Vec2::new(4.0, 0.0), center + Vec2::new(1.5, -0.5)],
                a_stroke,
            );
            painter.line_segment(
                [center + Vec2::new(4.0, 0.0), center + Vec2::new(4.0, -2.5)],
                a_stroke,
            );

            painter.line_segment(
                [center + Vec2::new(4.0, 2.5), center + Vec2::new(-1.5, 2.5)],
                a_stroke,
            );
            painter.line_segment(
                [center + Vec2::new(-1.5, 2.5), center + Vec2::new(-4.0, 0.0)],
                a_stroke,
            );
            painter.line_segment(
                [center + Vec2::new(-4.0, 0.0), center + Vec2::new(-1.5, 0.5)],
                a_stroke,
            );
            painter.line_segment(
                [center + Vec2::new(-4.0, 0.0), center + Vec2::new(-4.0, 2.5)],
                a_stroke,
            );
        }
        ToolVectorIcon::QuickMask => {
            let rect = Rect::from_center_size(center, Vec2::splat(12.0));
            painter.rect_stroke(rect, 1.0, stroke);
            painter.circle_stroke(center, 3.2, stroke);
        }
        ToolVectorIcon::ScreenMode => {
            let rect = Rect::from_center_size(center, Vec2::new(13.0, 10.0));
            painter.rect_stroke(rect, 1.0, stroke);
            painter.line_segment(
                [
                    Pos2::new(rect.left(), rect.top() + 3.0),
                    Pos2::new(rect.right(), rect.top() + 3.0),
                ],
                Stroke::new(1.0_f32, color),
            );
        }
    }
}

/// Transform handle positions for the TBox bounding box.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TransformHandle {
    TopLeft,
    TopCenter,
    TopRight,
    MiddleLeft,
    MiddleRight,
    BottomLeft,
    BottomCenter,
    BottomRight,
    Rotate,
    Body,
}

impl TransformHandle {
    /// Return the corresponding bidirectional movement cursor icon.
    pub fn cursor_icon(self) -> CursorIcon {
        match self {
            Self::TopLeft | Self::BottomRight => CursorIcon::ResizeNwSe,
            Self::TopRight | Self::BottomLeft => CursorIcon::ResizeNeSw,
            Self::TopCenter | Self::BottomCenter => CursorIcon::ResizeVertical,
            Self::MiddleLeft | Self::MiddleRight => CursorIcon::ResizeHorizontal,
            Self::Rotate => CursorIcon::Crosshair,
            Self::Body => CursorIcon::Move,
        }
    }
}

/// A scene-to-screen transform for the template canvas.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CanvasTransform {
    pub origin: Pos2,
    pub scale: f32,
}

impl CanvasTransform {
    /// Fit the whole template into `view`, preserving its aspect ratio.
    pub fn fit(view: Rect, template: &TemplateDefinition, zoom: f32, pan: Vec2) -> Self {
        let width = template.width_px.max(1) as f32;
        let height = template.height_px.max(1) as f32;
        let scale =
            (view.width() / width).min(view.height() / height) * zoom.clamp(MIN_ZOOM, MAX_ZOOM);
        let size = Vec2::new(width * scale, height * scale);
        Self {
            origin: view.center() - size / 2.0 + pan,
            scale,
        }
    }

    pub fn scene_to_screen(self, point: Pos2) -> Pos2 {
        self.origin + point.to_vec2() * self.scale
    }

    pub fn screen_to_scene(self, point: Pos2) -> Pos2 {
        let value = (point - self.origin) / self.scale.max(f32::EPSILON);
        Pos2::new(value.x, value.y)
    }

    pub fn scene_rect(self, template: &TemplateDefinition) -> Rect {
        Rect::from_min_size(
            self.origin,
            Vec2::new(
                template.width_px as f32 * self.scale,
                template.height_px as f32 * self.scale,
            ),
        )
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AlignmentType {
    Left,
    CenterHorizontal,
    Right,
    Top,
    CenterVertical,
    Bottom,
    CenterOnCard,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SwatchTarget {
    Fill,
    Font,
    Border,
    Background,
}

/// Commands independent of egui for undo/redo and scriptability.
#[derive(Debug, Clone, PartialEq)]
#[allow(clippy::large_enum_variant)]
pub enum EditorCommand {
    Add(CanvasElement),
    Delete {
        id: String,
    },
    Duplicate {
        id: String,
    },
    Move {
        id: String,
        delta: Vec2,
    },
    Resize {
        id: String,
        new_x: f64,
        new_y: f64,
        new_width: f64,
        new_height: f64,
    },
    SetVisibility {
        id: String,
        visible: bool,
    },
    SetLocked {
        id: String,
        locked: bool,
    },
    Raise {
        id: String,
    },
    Lower {
        id: String,
    },
    BringToFront {
        id: String,
    },
    SendToBack {
        id: String,
    },
    Align {
        id: String,
        alignment: AlignmentType,
    },
    UpdateColor {
        id: String,
        target: SwatchTarget,
        color: String,
    },
    CropCanvas {
        new_width: u32,
        new_height: u32,
        offset_x: f64,
        offset_y: f64,
    },
    SetBackgroundColor {
        color: String,
    },
    SetBackgroundGradient {
        from_color: String,
        to_color: String,
        angle: f32,
    },
    BatchDelete {
        ids: Vec<String>,
    },
    UpdateText {
        id: String,
        text: String,
    },
}

impl EditorCommand {
    pub fn description(&self) -> String {
        match self {
            Self::Add(elem) => format!("Add {}", elem.name),
            Self::Delete { .. } => "Delete element".into(),
            Self::Duplicate { .. } => "Duplicate element".into(),
            Self::Move { .. } => "Move element".into(),
            Self::Resize { .. } => "Transform element".into(),
            Self::SetVisibility { visible, .. } => if *visible {
                "Show element"
            } else {
                "Hide element"
            }
            .into(),
            Self::SetLocked { locked, .. } => if *locked {
                "Lock element"
            } else {
                "Unlock element"
            }
            .into(),
            Self::Raise { .. } => "Bring forward".into(),
            Self::Lower { .. } => "Send backward".into(),
            Self::BringToFront { .. } => "Bring to front".into(),
            Self::SendToBack { .. } => "Send to back".into(),
            Self::Align { alignment, .. } => format!("Align {:?}", alignment),
            Self::UpdateColor { target, .. } => format!("Set {:?} color", target),
            Self::CropCanvas { .. } => "Crop canvas".into(),
            Self::SetBackgroundColor { .. } => "Set background color".into(),
            Self::SetBackgroundGradient { .. } => "Set background gradient".into(),
            Self::BatchDelete { ids } => format!("Delete {} elements", ids.len()),
            Self::UpdateText { .. } => "Edit text".into(),
        }
    }
}

/// Snapshot history for template edits.
#[derive(Debug, Clone, Default)]
pub struct EditorHistory {
    pub undo: Vec<TemplateDefinition>,
    pub redo: Vec<TemplateDefinition>,
    pub action_names: Vec<String>,
}

impl EditorHistory {
    pub fn execute(&mut self, template: &mut TemplateDefinition, command: EditorCommand) -> bool {
        let before = template.clone();
        let desc = command.description();
        if !apply_command(template, command) || *template == before {
            return false;
        }
        self.undo.push(before);
        self.action_names.push(desc);
        self.redo.clear();
        true
    }

    pub fn record_action(
        &mut self,
        before: TemplateDefinition,
        after: &TemplateDefinition,
        action: String,
    ) {
        if before != *after {
            self.undo.push(before);
            self.action_names.push(action);
            self.redo.clear();
        }
    }

    pub fn record_change(&mut self, before: TemplateDefinition, after: &TemplateDefinition) {
        self.record_action(before, after, "Edit properties".into());
    }

    pub fn undo(&mut self, template: &mut TemplateDefinition) -> bool {
        let Some(snapshot) = self.undo.pop() else {
            return false;
        };
        self.redo.push(template.clone());
        *template = snapshot;
        true
    }

    pub fn redo(&mut self, template: &mut TemplateDefinition) -> bool {
        let Some(snapshot) = self.redo.pop() else {
            return false;
        };
        self.undo.push(template.clone());
        *template = snapshot;
        true
    }

    pub fn can_undo(&self) -> bool {
        !self.undo.is_empty()
    }

    pub fn can_redo(&self) -> bool {
        !self.redo.is_empty()
    }
}

fn apply_command(template: &mut TemplateDefinition, command: EditorCommand) -> bool {
    match command {
        EditorCommand::Add(mut element) => {
            if template.get_element_by_id(&element.id).is_some() {
                element.id = Uuid::new_v4().to_string();
            }
            template.elements.push(element);
            true
        }
        EditorCommand::Delete { id } => remove_element(template, &id),
        EditorCommand::Duplicate { id } => {
            let Some(mut copy) = template.get_element_by_id(&id).cloned() else {
                return false;
            };
            copy.id = Uuid::new_v4().to_string();
            copy.name = format!("{} Copy", copy.name);
            copy.x += 15.0;
            copy.y += 15.0;
            copy.z_index += 1;
            template.elements.push(copy);
            true
        }
        EditorCommand::Move { id, delta } => {
            let Some(element) = template.elements.iter_mut().find(|elem| elem.id == id) else {
                return false;
            };
            element.x += f64::from(delta.x);
            element.y += f64::from(delta.y);
            true
        }
        EditorCommand::Resize {
            id,
            new_x,
            new_y,
            new_width,
            new_height,
        } => {
            let Some(element) = template.elements.iter_mut().find(|elem| elem.id == id) else {
                return false;
            };
            let is_text = element.r#type == "text" || element.r#type == "dynamic_text";
            let (min_w, min_h) = if is_text {
                (40.0, 20.0)
            } else if element.r#type == "line" {
                (10.0, 2.0)
            } else {
                (24.0, 24.0)
            };
            element.x = new_x;
            element.y = new_y;
            element.width = new_width.max(min_w);
            element.height = new_height.max(min_h);
            true
        }
        EditorCommand::SetVisibility { id, visible } => {
            let Some(element) = template.elements.iter_mut().find(|elem| elem.id == id) else {
                return false;
            };
            element.visible = visible;
            true
        }
        EditorCommand::SetLocked { id, locked } => {
            let Some(element) = template.elements.iter_mut().find(|elem| elem.id == id) else {
                return false;
            };
            element.locked = locked;
            true
        }
        EditorCommand::Raise { id } => step_z_index(template, &id, 1),
        EditorCommand::Lower { id } => step_z_index(template, &id, -1),
        EditorCommand::BringToFront { id } => set_extreme_z_index(template, &id, true),
        EditorCommand::SendToBack { id } => set_extreme_z_index(template, &id, false),
        EditorCommand::Align { id, alignment } => align_element(template, &id, alignment),
        EditorCommand::UpdateColor { id, target, color } => {
            let Some(element) = template.elements.iter_mut().find(|elem| elem.id == id) else {
                return false;
            };
            match target {
                SwatchTarget::Fill => element.style.background_color = color,
                SwatchTarget::Font => element.style.font_color = color,
                SwatchTarget::Border => element.style.border_color = color,
                SwatchTarget::Background => {}
            }
            true
        }
        EditorCommand::CropCanvas {
            new_width,
            new_height,
            offset_x,
            offset_y,
        } => {
            template.width_px = new_width.max(10);
            template.height_px = new_height.max(10);
            for elem in &mut template.elements {
                elem.x -= offset_x;
                elem.y -= offset_y;
            }
            true
        }
        EditorCommand::SetBackgroundColor { color } => {
            template.background_color = color;
            true
        }
        EditorCommand::SetBackgroundGradient {
            from_color,
            to_color,
            angle,
        } => {
            template.background_color = from_color.clone();
            template.metadata.insert(
                "background_gradient".into(),
                serde_json::json!({
                    "from": from_color,
                    "to": to_color,
                    "angle": angle,
                }),
            );
            true
        }
        EditorCommand::BatchDelete { ids } => {
            let before = template.elements.len();
            template
                .elements
                .retain(|element| !ids.contains(&element.id));
            template.elements.len() != before
        }
        EditorCommand::UpdateText { id, text } => {
            let Some(element) = template.elements.iter_mut().find(|elem| elem.id == id) else {
                return false;
            };
            element.static_content = Some(text);
            true
        }
    }
}

fn remove_element(template: &mut TemplateDefinition, id: &str) -> bool {
    let before = template.elements.len();
    template.elements.retain(|element| element.id != id);
    template.elements.len() != before
}

fn step_z_index(template: &mut TemplateDefinition, id: &str, delta: i32) -> bool {
    let Some(element) = template.elements.iter_mut().find(|elem| elem.id == id) else {
        return false;
    };
    element.z_index += delta;
    true
}

fn set_extreme_z_index(template: &mut TemplateDefinition, id: &str, front: bool) -> bool {
    let current_extremum = if front {
        template
            .elements
            .iter()
            .map(|element| element.z_index)
            .max()
            .unwrap_or(0)
    } else {
        template
            .elements
            .iter()
            .map(|element| element.z_index)
            .min()
            .unwrap_or(0)
    };
    let target = if front {
        current_extremum + 1
    } else {
        current_extremum - 1
    };
    let Some(element) = template.elements.iter_mut().find(|elem| elem.id == id) else {
        return false;
    };
    if element.z_index == target {
        return false;
    }
    element.z_index = target;
    true
}

fn align_element(template: &mut TemplateDefinition, id: &str, alignment: AlignmentType) -> bool {
    let width = template.width_px as f64;
    let height = template.height_px as f64;
    let Some(element) = template.elements.iter_mut().find(|elem| elem.id == id) else {
        return false;
    };
    match alignment {
        AlignmentType::Left => element.x = 0.0,
        AlignmentType::CenterHorizontal => element.x = ((width - element.width) / 2.0).max(0.0),
        AlignmentType::Right => element.x = (width - element.width).max(0.0),
        AlignmentType::Top => element.y = 0.0,
        AlignmentType::CenterVertical => element.y = ((height - element.height) / 2.0).max(0.0),
        AlignmentType::Bottom => element.y = (height - element.height).max(0.0),
        AlignmentType::CenterOnCard => {
            element.x = ((width - element.width) / 2.0).max(0.0);
            element.y = ((height - element.height) / 2.0).max(0.0);
        }
    }
    true
}

#[derive(Debug, Clone)]
struct DragState {
    id: String,
    handle: TransformHandle,
    start_element_rect: Rect,
    start_pointer_scene: Pos2,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CropHandle {
    TopLeft,
    TopCenter,
    TopRight,
    MiddleLeft,
    MiddleRight,
    BottomLeft,
    BottomCenter,
    BottomRight,
    Inside,
}

impl CropHandle {
    pub fn cursor_icon(self) -> CursorIcon {
        match self {
            Self::TopLeft | Self::BottomRight => CursorIcon::ResizeNwSe,
            Self::TopRight | Self::BottomLeft => CursorIcon::ResizeNeSw,
            Self::TopCenter | Self::BottomCenter => CursorIcon::ResizeVertical,
            Self::MiddleLeft | Self::MiddleRight => CursorIcon::ResizeHorizontal,
            Self::Inside => CursorIcon::Move,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum CropAspectPreset {
    #[default]
    Free,
    Custom,
    Original,
    Square,
    Cr80,
    Ratio4_3,
    Ratio16_9,
}

impl CropAspectPreset {
    pub fn label(self) -> &'static str {
        match self {
            Self::Free => "Free Unconstrained",
            Self::Custom => "Custom Size (W × H)",
            Self::Original => "Original Ratio",
            Self::Square => "1:1 Square",
            Self::Cr80 => "CR80 (85.6 × 54 mm)",
            Self::Ratio4_3 => "4:3 Standard",
            Self::Ratio16_9 => "16:9 Widescreen",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EditorTab {
    Properties,
    Layers,
    Swatches,
    History,
    Align,
}

/// Transient state for [`TemplateEditor`].
#[derive(Debug, Clone)]
pub struct TemplateEditorState {
    pub zoom: f32,
    pub pan: Vec2,
    pub selected_id: Option<String>,
    pub active_tool: EditorTool,
    pub active_shape: ShapeKind,
    pub show_grid: bool,
    pub show_safe_area: bool,
    pub show_rulers: bool,
    pub ruler_unit: String,
    pub show_crosshairs: bool,
    pub show_transform_controls: bool,
    pub snap_to_grid: bool,
    pub active_tab: EditorTab,
    pub swatch_target: SwatchTarget,
    pub custom_hex_color: String,
    pub foreground_color: Color32,
    pub background_color: Color32,

    // Tool specific options
    pub font_family: String,
    pub font_size: u32,
    pub font_bold: bool,
    pub font_italic: bool,
    pub text_align: String,
    pub brush_size: f32,
    pub brush_opacity: f32,
    pub brush_hardness: f32,
    pub crop_width: f64,
    pub crop_height: f64,
    pub crop_unit: CanvasUnit,
    pub crop_ratio: &'static str,
    pub crop_aspect_preset: CropAspectPreset,
    pub crop_rect: Option<Rect>,
    pub crop_drag_handle: Option<CropHandle>,
    pub crop_drag_start_pointer: Option<Pos2>,
    pub crop_drag_start_rect: Option<Rect>,

    pub gradient_start: Option<Pos2>,
    pub gradient_end: Option<Pos2>,
    pub gradient_style: String,

    pub shape_corner_radius: u32,
    pub shape_border_width: u32,
    pub shape_fill_color: Color32,
    pub shape_border_color: Color32,

    pub sampled_color: Option<Color32>,
    pub sampled_hex: String,
    pub hovered_object_id: Option<String>,

    pub cursor_scene_pos: Option<Pos2>,
    pub history: EditorHistory,
    drag: Option<DragState>,
    tool_drag_start: Option<Pos2>,
    live_shape_rect: Option<Rect>,
    live_marquee_rect: Option<Rect>,
    live_brush_stroke: Vec<Pos2>,
    pub editing_text_id: Option<String>,
    pub editing_text_buffer: String,
    pub scrollbar_dragging_h: bool,
    pub scrollbar_dragging_v: bool,
    pub eraser_drag_snapshot: Option<TemplateDefinition>,
    pub last_eraser_pos: Option<Pos2>,
    pub eraser_modified: bool,
}

impl Default for TemplateEditorState {
    fn default() -> Self {
        Self {
            zoom: 1.0,
            pan: Vec2::ZERO,
            selected_id: None,
            active_tool: EditorTool::Move,
            active_shape: ShapeKind::Rectangle,
            show_grid: true,
            show_safe_area: true,
            show_rulers: true,
            ruler_unit: "px".into(),
            show_crosshairs: true,
            show_transform_controls: true,
            snap_to_grid: true,
            active_tab: EditorTab::Properties,
            swatch_target: SwatchTarget::Fill,
            custom_hex_color: "#2563EB".into(),
            foreground_color: Color32::from_rgb(15, 23, 42), // Deep slate black
            background_color: Color32::WHITE,

            font_family: "Inter, sans-serif".into(),
            font_size: 16,
            font_bold: false,
            font_italic: false,
            text_align: "left".into(),
            brush_size: 14.0,
            brush_opacity: 1.0,
            brush_hardness: 0.8,
            crop_width: 1011.0,
            crop_height: 638.0,
            crop_unit: CanvasUnit::Pixels,
            crop_ratio: "Original",
            crop_aspect_preset: CropAspectPreset::Free,
            crop_rect: None,
            crop_drag_handle: None,
            crop_drag_start_pointer: None,
            crop_drag_start_rect: None,

            gradient_start: None,
            gradient_end: None,
            gradient_style: "linear".into(),

            shape_corner_radius: 12,
            shape_border_width: 2,
            shape_fill_color: Color32::from_rgb(37, 99, 235),
            shape_border_color: Color32::from_rgb(15, 23, 42),

            sampled_color: None,
            sampled_hex: "#000000".into(),
            hovered_object_id: None,

            cursor_scene_pos: None,
            history: EditorHistory::default(),
            drag: None,
            tool_drag_start: None,
            live_shape_rect: None,
            live_marquee_rect: None,
            live_brush_stroke: Vec::new(),
            editing_text_id: None,
            editing_text_buffer: String::new(),
            scrollbar_dragging_h: false,
            scrollbar_dragging_v: false,
            eraser_drag_snapshot: None,
            last_eraser_pos: None,
            eraser_modified: false,
        }
    }
}

impl TemplateEditorState {
    pub fn execute(&mut self, template: &mut TemplateDefinition, command: EditorCommand) -> bool {
        self.history.execute(template, command)
    }

    pub fn undo(&mut self, template: &mut TemplateDefinition) -> bool {
        let changed = self.history.undo(template);
        if changed
            && self
                .selected_id
                .as_ref()
                .is_some_and(|id| template.get_element_by_id(id).is_none())
        {
            self.selected_id = None;
        }
        changed
    }

    pub fn redo(&mut self, template: &mut TemplateDefinition) -> bool {
        self.history.redo(template)
    }

    pub fn fit_canvas(&mut self) {
        self.zoom = 1.0;
        self.pan = Vec2::ZERO;
    }

    pub fn swap_colors(&mut self) {
        std::mem::swap(&mut self.foreground_color, &mut self.background_color);
    }

    pub fn reset_default_colors(&mut self) {
        self.foreground_color = Color32::BLACK;
        self.background_color = Color32::WHITE;
    }
}

/// Native template editor with Photoshop vertical toolbox, contextual top options bar,
/// TBox transform box with 8 handles, and Photoshop docking panels.
pub struct TemplateEditor<'a> {
    pub template: &'a mut TemplateDefinition,
    pub state: &'a mut TemplateEditorState,
    pub available_columns: &'a [String],
    pub photo_key_column: Option<&'a mut Option<String>>,
    pub sample_photo_match: Option<&'a crate::data::models::PhotoMatchResult>,
}

impl<'a> TemplateEditor<'a> {
    pub fn new(template: &'a mut TemplateDefinition, state: &'a mut TemplateEditorState) -> Self {
        Self {
            template,
            state,
            available_columns: &[],
            photo_key_column: None,
            sample_photo_match: None,
        }
    }

    pub fn with_context(
        template: &'a mut TemplateDefinition,
        state: &'a mut TemplateEditorState,
        available_columns: &'a [String],
        photo_key_column: Option<&'a mut Option<String>>,
        sample_photo_match: Option<&'a crate::data::models::PhotoMatchResult>,
    ) -> Self {
        Self {
            template,
            state,
            available_columns,
            photo_key_column,
            sample_photo_match,
        }
    }

    pub fn start_editing_text(&mut self, id: String) {
        if let Some(elem) = self.template.get_element_by_id(&id) {
            self.state.editing_text_buffer = elem
                .static_content
                .clone()
                .unwrap_or_else(|| elem.name.clone());
            self.state.editing_text_id = Some(id.clone());
            self.state.selected_id = Some(id);
        }
    }

    pub fn commit_editing_text(&mut self) {
        if let Some(id) = self.state.editing_text_id.take() {
            let buffer = std::mem::take(&mut self.state.editing_text_buffer);
            self.state.execute(
                self.template,
                EditorCommand::UpdateText { id, text: buffer },
            );
            if self.state.active_tool == EditorTool::Text {
                self.state.active_tool = EditorTool::Move;
            }
        }
    }

    pub fn cancel_editing_text(&mut self) {
        self.state.editing_text_id = None;
        self.state.editing_text_buffer.clear();
        if self.state.active_tool == EditorTool::Text {
            self.state.active_tool = EditorTool::Move;
        }
    }

    pub fn show(&mut self, ui: &mut Ui) -> bool {
        let before = self.template.clone();

        // 1. Contextual Top Options Bar
        self.top_options_bar(ui);
        ui.separator();

        // 2. Vertical Photoshop Toolbox on Left
        egui::SidePanel::left(Id::new("photoshop_vertical_toolbox"))
            .resizable(false)
            .exact_width(62.0)
            .frame(
                egui::Frame::none()
                    .fill(Color32::from_rgb(40, 40, 44))
                    .stroke(Stroke::new(1.0_f32, Color32::from_rgb(28, 28, 30)))
                    .inner_margin(3.0_f32),
            )
            .show_inside(ui, |ui| self.vertical_toolbox(ui));

        // 3. Photoshop Dock Panel on Right (Properties, Layers, Swatches, History, Align)
        egui::SidePanel::right(Id::new("photoshop_right_dock_panel"))
            .resizable(true)
            .default_width(300.0)
            .min_width(260.0)
            .show_inside(ui, |ui| self.right_dock_panel(ui));

        // 4. Central Canvas Viewport with Rulers, TBox, and HUD
        egui::CentralPanel::default().show_inside(ui, |ui| self.canvas_viewport(ui));

        *self.template != before
    }

    /// Vertical Photoshop-style toolbox on the far left with a 2-column icon-only layout.
    fn vertical_toolbox(&mut self, ui: &mut Ui) {
        ui.vertical_centered(|ui| {
            // Photoshop collapse header icon
            ui.add_space(3.0);
            ui.label(
                egui::RichText::new("«")
                    .size(11.0)
                    .color(Color32::from_gray(140)),
            )
            .on_hover_text("Photoshop Tools Panel");
            ui.add_space(4.0);

            let tool_rows: &[[EditorTool; 2]] = &[
                [EditorTool::Move, EditorTool::Marquee],
                [EditorTool::ObjectSelect, EditorTool::Crop],
                [EditorTool::Eyedropper, EditorTool::Brush],
                [EditorTool::Eraser, EditorTool::Gradient],
                [EditorTool::PaintBucket, EditorTool::Text],
                [EditorTool::Shape, EditorTool::Hand],
            ];

            let button_size = Vec2::splat(26.0);
            let spacing = Vec2::new(3.0, 3.0);

            for pair in tool_rows {
                ui.horizontal(|ui| {
                    ui.spacing_mut().item_spacing = spacing;
                    for &tool in pair {
                        self.render_tool_button(ui, tool, button_size);
                    }
                });
                ui.add_space(1.0);
            }

            // Zoom and Fit row
            ui.horizontal(|ui| {
                ui.spacing_mut().item_spacing = spacing;
                self.render_tool_button(ui, EditorTool::Zoom, button_size);

                // Fit to Screen button
                let (rect, resp) = ui.allocate_exact_size(button_size, Sense::click());
                let painter = ui.painter_at(rect);
                let bg_col = if resp.hovered() {
                    Color32::from_rgb(52, 52, 56)
                } else {
                    Color32::from_rgb(36, 36, 38)
                };
                painter.rect_filled(rect, 2.5_f32, bg_col);
                draw_tool_vector_icon(
                    &painter,
                    ToolVectorIcon::Fit,
                    rect.center(),
                    if resp.hovered() {
                        Color32::WHITE
                    } else {
                        Color32::from_gray(200)
                    },
                );
                if resp.clicked() {
                    self.state.zoom = 1.0;
                    self.state.pan = Vec2::ZERO;
                }
                resp.on_hover_text("Fit on Screen (Ctrl+0)");
            });
            ui.add_space(1.0);

            // 100% Zoom and More Tools row
            ui.horizontal(|ui| {
                ui.spacing_mut().item_spacing = spacing;

                // 100% actual pixels
                let (rect1, resp1) = ui.allocate_exact_size(button_size, Sense::click());
                let painter1 = ui.painter_at(rect1);
                let bg1 = if resp1.hovered() {
                    Color32::from_rgb(52, 52, 56)
                } else {
                    Color32::from_rgb(36, 36, 38)
                };
                painter1.rect_filled(rect1, 2.5_f32, bg1);
                draw_tool_vector_icon(
                    &painter1,
                    ToolVectorIcon::ActualPixels,
                    rect1.center(),
                    if resp1.hovered() {
                        Color32::WHITE
                    } else {
                        Color32::from_gray(200)
                    },
                );
                if resp1.clicked() {
                    self.state.zoom = 1.0;
                }
                resp1.on_hover_text("Actual Pixels 100% (Ctrl+1)");

                // More tools (...)
                let (rect2, resp2) = ui.allocate_exact_size(button_size, Sense::click());
                let painter2 = ui.painter_at(rect2);
                let bg2 = if resp2.hovered() {
                    Color32::from_rgb(52, 52, 56)
                } else {
                    Color32::from_rgb(36, 36, 38)
                };
                painter2.rect_filled(rect2, 2.5_f32, bg2);
                draw_tool_vector_icon(
                    &painter2,
                    ToolVectorIcon::More,
                    rect2.center(),
                    if resp2.hovered() {
                        Color32::WHITE
                    } else {
                        Color32::from_gray(200)
                    },
                );
                resp2.on_hover_text("Edit Toolbar & Tools");
            });

            ui.add_space(6.0);
            ui.separator();
            ui.add_space(4.0);

            // Photoshop Dual Color Swatches
            self.photoshop_color_swatches(ui);
        });
    }

    /// Renders a single square tool button with Photoshop active highlight, vector icon, and complete name on hover.
    fn render_tool_button(&mut self, ui: &mut Ui, tool: EditorTool, size: Vec2) {
        let is_active = self.state.active_tool == tool;
        let (rect, resp) = ui.allocate_exact_size(size, Sense::click());

        if resp.clicked() {
            self.state.active_tool = tool;
            if tool == EditorTool::Crop {
                self.init_crop_if_needed();
            }
        }

        let painter = ui.painter_at(rect);
        let rounding = 2.5_f32;

        if is_active {
            // Photoshop active tool highlight: vivid sky-blue outline with dark slate fill
            painter.rect_filled(rect, rounding, Color32::from_rgb(38, 48, 64));
            painter.rect_stroke(
                rect,
                rounding,
                Stroke::new(1.5_f32, Color32::from_rgb(56, 189, 248)),
            );
        } else if resp.hovered() {
            painter.rect_filled(rect, rounding, Color32::from_rgb(52, 52, 56));
            painter.rect_stroke(rect, rounding, Stroke::new(1.0_f32, Color32::from_gray(80)));
        } else {
            painter.rect_filled(rect, rounding, Color32::from_rgb(36, 36, 38));
        }

        let icon_color = if is_active {
            Color32::WHITE
        } else if resp.hovered() {
            Color32::from_gray(245)
        } else {
            Color32::from_gray(210)
        };

        // Draw pixel-perfect procedural vector icon (never tofu □)
        let vector_icon = tool.vector_icon(self.state.active_shape);
        draw_tool_vector_icon(&painter, vector_icon, rect.center(), icon_color);

        // Subtle bottom-right corner triangle indicator like Photoshop
        let tri = [
            rect.right_bottom() + Vec2::new(-1.0, -4.5),
            rect.right_bottom() + Vec2::new(-1.0, -1.0),
            rect.right_bottom() + Vec2::new(-4.5, -1.0),
        ];
        let tri_color = if is_active {
            Color32::from_rgb(56, 189, 248)
        } else {
            Color32::from_gray(100)
        };
        painter.add(egui::Shape::convex_polygon(
            tri.to_vec(),
            tri_color,
            Stroke::NONE,
        ));

        // Hover displays full tool name and shortcut
        resp.on_hover_text(tool.name());
    }

    /// Overlapping Foreground / Background color swatches like Photoshop with vector icons.
    fn photoshop_color_swatches(&mut self, ui: &mut Ui) {
        // Top miniature row: Default B&W (D) and Swap (X)
        ui.horizontal(|ui| {
            ui.spacing_mut().item_spacing = Vec2::new(16.0, 0.0);

            // Default B&W button (vector icon)
            let (d_rect, d_resp) = ui.allocate_exact_size(Vec2::splat(15.0), Sense::click());
            let d_painter = ui.painter_at(d_rect);
            draw_tool_vector_icon(
                &d_painter,
                ToolVectorIcon::DefaultColors,
                d_rect.center(),
                Color32::WHITE,
            );
            if d_resp.clicked() {
                self.state.reset_default_colors();
            }
            d_resp.on_hover_text("Default Foreground and Background Colors (D)");

            // Swap colors button (vector icon)
            let (x_rect, x_resp) = ui.allocate_exact_size(Vec2::splat(15.0), Sense::click());
            let x_painter = ui.painter_at(x_rect);
            draw_tool_vector_icon(
                &x_painter,
                ToolVectorIcon::SwapColors,
                x_rect.center(),
                if x_resp.hovered() {
                    Color32::WHITE
                } else {
                    Color32::from_gray(200)
                },
            );
            if x_resp.clicked() {
                self.state.swap_colors();
            }
            x_resp.on_hover_text("Switch Foreground and Background Colors (X)");
        });

        ui.add_space(2.0);

        // Overlapping dual color chips
        let box_size = Vec2::splat(22.0);
        let (rect, _response) = ui.allocate_exact_size(Vec2::new(42.0, 38.0), Sense::hover());
        let painter = ui.painter_at(rect);

        // Background color box (lower right)
        let bg_rect = Rect::from_min_size(rect.min + Vec2::new(15.0, 12.0), box_size);
        painter.rect_filled(bg_rect, 1.0_f32, self.state.background_color);
        painter.rect_stroke(
            bg_rect,
            1.0_f32,
            Stroke::new(1.0_f32, Color32::from_gray(40)),
        );
        painter.rect_stroke(
            bg_rect.shrink(1.0),
            0.0_f32,
            Stroke::new(1.0_f32, Color32::from_gray(180)),
        );

        // Foreground color box (upper left)
        let fg_rect = Rect::from_min_size(rect.min + Vec2::new(2.0, 2.0), box_size);
        painter.rect_filled(fg_rect, 1.0_f32, self.state.foreground_color);
        painter.rect_stroke(
            fg_rect,
            1.0_f32,
            Stroke::new(1.0_f32, Color32::from_gray(40)),
        );
        painter.rect_stroke(
            fg_rect.shrink(1.0),
            0.0_f32,
            Stroke::new(1.0_f32, Color32::WHITE),
        );

        ui.add_space(4.0);

        // Quick edit buttons
        ui.horizontal(|ui| {
            ui.spacing_mut().item_spacing = Vec2::new(4.0, 0.0);
            ui.color_edit_button_srgba(&mut self.state.foreground_color)
                .on_hover_text("Click to edit Foreground Color");
            ui.color_edit_button_srgba(&mut self.state.background_color)
                .on_hover_text("Click to edit Background Color");
        });

        ui.add_space(4.0);

        // Bottom row: Standard Screen Mode and Quick Mask Mode (matching Photoshop reference)
        ui.horizontal(|ui| {
            ui.spacing_mut().item_spacing = Vec2::new(3.0, 0.0);

            // Quick Mask Mode (vector icon)
            let (q_rect, q_resp) = ui.allocate_exact_size(Vec2::splat(25.0), Sense::click());
            let q_painter = ui.painter_at(q_rect);
            let q_bg = if q_resp.hovered() {
                Color32::from_rgb(52, 52, 56)
            } else {
                Color32::from_rgb(36, 36, 38)
            };
            q_painter.rect_filled(q_rect, 2.0_f32, q_bg);
            draw_tool_vector_icon(
                &q_painter,
                ToolVectorIcon::QuickMask,
                q_rect.center(),
                if q_resp.hovered() {
                    Color32::WHITE
                } else {
                    Color32::from_gray(200)
                },
            );
            q_resp.on_hover_text("Edit in Standard Mode (Q)");

            // Screen Mode (vector icon)
            let (s_rect, s_resp) = ui.allocate_exact_size(Vec2::splat(25.0), Sense::click());
            let s_painter = ui.painter_at(s_rect);
            let s_bg = if s_resp.hovered() {
                Color32::from_rgb(52, 52, 56)
            } else {
                Color32::from_rgb(36, 36, 38)
            };
            s_painter.rect_filled(s_rect, 2.0_f32, s_bg);
            draw_tool_vector_icon(
                &s_painter,
                ToolVectorIcon::ScreenMode,
                s_rect.center(),
                if s_resp.hovered() {
                    Color32::WHITE
                } else {
                    Color32::from_gray(200)
                },
            );
            if s_resp.clicked() {
                self.state.zoom = 1.0;
                self.state.pan = Vec2::ZERO;
            }
            s_resp.on_hover_text("Change Screen Mode (F)");
        });
    }

    /// Contextual top options bar adapting dynamically to the active tool.
    fn top_options_bar(&mut self, ui: &mut Ui) {
        ui.horizontal(|ui| {
            // Undo / Redo controls
            if ui
                .add_enabled(self.state.history.can_undo(), egui::Button::new("↶ Undo"))
                .clicked()
            {
                self.state.undo(self.template);
            }
            if ui
                .add_enabled(self.state.history.can_redo(), egui::Button::new("↷ Redo"))
                .clicked()
            {
                self.state.redo(self.template);
            }

            ui.separator();

            // Active Tool Indicator
            ui.colored_label(
                Color32::from_rgb(56, 189, 248),
                self.state.active_tool.name(),
            );

            ui.separator();

            // Dynamic Context Options
            match self.state.active_tool {
                EditorTool::Move | EditorTool::ObjectSelect => {
                    ui.checkbox(
                        &mut self.state.show_transform_controls,
                        "Show Transform (TBox)",
                    );
                    ui.checkbox(&mut self.state.snap_to_grid, "Snap to Grid");
                    ui.separator();
                    ui.label("Align:");
                    for (label, align) in [
                        ("⇤ Left", AlignmentType::Left),
                        ("⇥ Right", AlignmentType::Right),
                        ("⇋ Center H", AlignmentType::CenterHorizontal),
                        ("⤒ Top", AlignmentType::Top),
                        ("⤓ Bottom", AlignmentType::Bottom),
                        ("↕ Center V", AlignmentType::CenterVertical),
                        ("⊡ Card", AlignmentType::CenterOnCard),
                    ] {
                        if ui.small_button(label).clicked() {
                            if let Some(id) = &self.state.selected_id.clone() {
                                self.state.execute(
                                    self.template,
                                    EditorCommand::Align {
                                        id: id.clone(),
                                        alignment: align,
                                    },
                                );
                            }
                        }
                    }
                }
                EditorTool::Text => {
                    ui.label("Font:");
                    egui::ComboBox::from_id_salt("top_font_family")
                        .selected_text(&self.state.font_family)
                        .show_ui(ui, |ui| {
                            for f in [
                                "Inter, sans-serif",
                                "Roboto, sans-serif",
                                "Arial, Helvetica, sans-serif",
                                "Times New Roman, serif",
                                "Courier New, monospace",
                                "Georgia, serif",
                            ] {
                                ui.selectable_value(&mut self.state.font_family, f.into(), f);
                            }
                        });

                    ui.label("Size:");
                    ui.add(egui::DragValue::new(&mut self.state.font_size).range(6..=200));
                    ui.small("px");

                    ui.toggle_value(&mut self.state.font_bold, egui::RichText::new("B").strong());
                    ui.toggle_value(
                        &mut self.state.font_italic,
                        egui::RichText::new("I").italics(),
                    );

                    ui.label("Align:");
                    for (icon, val) in [("⫷", "left"), ("≡", "center"), ("⫸", "right")] {
                        if ui
                            .selectable_label(self.state.text_align == val, icon)
                            .clicked()
                        {
                            self.state.text_align = val.into();
                        }
                    }

                    if ui.small_button("+ Add Text to Canvas").clicked() {
                        self.add_element("text");
                    }
                }
                EditorTool::Shape => {
                    ui.label("Active Shape:");
                    egui::ComboBox::from_id_salt("top_shape_select")
                        .selected_text(self.state.active_shape.label())
                        .show_ui(ui, |ui| {
                            ui.selectable_value(
                                &mut self.state.active_shape,
                                ShapeKind::Rectangle,
                                ShapeKind::Rectangle.label(),
                            );
                            ui.selectable_value(
                                &mut self.state.active_shape,
                                ShapeKind::RoundedRectangle,
                                ShapeKind::RoundedRectangle.label(),
                            );
                            ui.selectable_value(
                                &mut self.state.active_shape,
                                ShapeKind::Ellipse,
                                ShapeKind::Ellipse.label(),
                            );
                            ui.selectable_value(
                                &mut self.state.active_shape,
                                ShapeKind::Line,
                                ShapeKind::Line.label(),
                            );
                        });

                    ui.label("Fill:");
                    ui.color_edit_button_srgba(&mut self.state.foreground_color);

                    ui.label("Stroke:");
                    ui.color_edit_button_srgba(&mut self.state.background_color);

                    ui.label("Width:");
                    ui.add(egui::DragValue::new(&mut self.state.shape_border_width).range(0..=30));

                    if self.state.active_shape == ShapeKind::RoundedRectangle {
                        ui.label("Radius:");
                        ui.add(
                            egui::DragValue::new(&mut self.state.shape_corner_radius).range(0..=80),
                        );
                    }

                    if ui.small_button("+ Add to Center").clicked() {
                        match self.state.active_shape {
                            ShapeKind::Rectangle => self.add_element("rect"),
                            ShapeKind::RoundedRectangle => self.add_element("round_rect"),
                            ShapeKind::Ellipse => self.add_element("ellipse"),
                            ShapeKind::Line => self.add_element("line"),
                        }
                    }
                }
                EditorTool::Crop => {
                    ui.label("Preset:");
                    egui::ComboBox::from_id_salt("top_crop_preset")
                        .selected_text(self.state.crop_aspect_preset.label())
                        .show_ui(ui, |ui| {
                            for preset in [
                                CropAspectPreset::Free,
                                CropAspectPreset::Custom,
                                CropAspectPreset::Original,
                                CropAspectPreset::Square,
                                CropAspectPreset::Cr80,
                                CropAspectPreset::Ratio4_3,
                                CropAspectPreset::Ratio16_9,
                            ] {
                                if ui
                                    .selectable_value(
                                        &mut self.state.crop_aspect_preset,
                                        preset,
                                        preset.label(),
                                    )
                                    .clicked()
                                {
                                    match preset {
                                        CropAspectPreset::Free | CropAspectPreset::Custom => {}
                                        CropAspectPreset::Original => {
                                            let w = self.template.width_px as f32;
                                            let h = self.template.height_px as f32;
                                            self.apply_crop_dimensions(w, h);
                                        }
                                        CropAspectPreset::Square => {
                                            let s = self
                                                .state
                                                .crop_width
                                                .min(self.state.crop_height)
                                                .max(50.0)
                                                as f32;
                                            self.apply_crop_dimensions(s, s);
                                        }
                                        CropAspectPreset::Cr80 => {
                                            let dpi = self.template.dpi.max(72) as f64;
                                            let w = (85.60 / 25.4 * dpi).round() as f32;
                                            let h = (53.98 / 25.4 * dpi).round() as f32;
                                            self.apply_crop_dimensions(w, h);
                                        }
                                        CropAspectPreset::Ratio4_3 => {
                                            let w = self.state.crop_width as f32;
                                            let h = (w * (3.0 / 4.0)).round();
                                            self.apply_crop_dimensions(w, h);
                                        }
                                        CropAspectPreset::Ratio16_9 => {
                                            let w = self.state.crop_width as f32;
                                            let h = (w * (9.0 / 16.0)).round();
                                            self.apply_crop_dimensions(w, h);
                                        }
                                    }
                                }
                            }
                        });

                    ui.separator();

                    let dpi = self.template.dpi.max(72) as f64;
                    let unit = self.state.crop_unit;

                    let px_to_unit = |px: f64| -> f64 {
                        match unit {
                            CanvasUnit::Pixels => px,
                            CanvasUnit::Inches => px / dpi,
                            CanvasUnit::Millimeters => (px / dpi) * 25.4,
                            CanvasUnit::Centimeters => (px / dpi) * 2.54,
                        }
                    };

                    let unit_to_px = |val: f64| -> f64 {
                        match unit {
                            CanvasUnit::Pixels => val,
                            CanvasUnit::Inches => val * dpi,
                            CanvasUnit::Millimeters => (val / 25.4) * dpi,
                            CanvasUnit::Centimeters => (val / 2.54) * dpi,
                        }
                    };

                    let (speed, range, suffix) = match unit {
                        CanvasUnit::Pixels => (1.0, 10.0..=20000.0, " px"),
                        CanvasUnit::Millimeters => (0.5, 1.0..=2000.0, " mm"),
                        CanvasUnit::Centimeters => (0.1, 0.1..=200.0, " cm"),
                        CanvasUnit::Inches => (0.05, 0.1..=100.0, " in"),
                    };

                    ui.label(egui::RichText::new("W:").strong());
                    let mut w_display = px_to_unit(self.state.crop_width);
                    let w_resp = ui.add(
                        egui::DragValue::new(&mut w_display)
                            .speed(speed)
                            .range(range.clone())
                            .suffix(suffix),
                    );

                    ui.label(egui::RichText::new("H:").strong());
                    let mut h_display = px_to_unit(self.state.crop_height);
                    let h_resp = ui.add(
                        egui::DragValue::new(&mut h_display)
                            .speed(speed)
                            .range(range)
                            .suffix(suffix),
                    );

                    // Measurement unit selector (mm, cm, in, px)
                    egui::ComboBox::from_id_salt("top_crop_unit")
                        .selected_text(self.state.crop_unit.short_code())
                        .width(55.0)
                        .show_ui(ui, |ui| {
                            for u in [
                                CanvasUnit::Millimeters,
                                CanvasUnit::Centimeters,
                                CanvasUnit::Inches,
                                CanvasUnit::Pixels,
                            ] {
                                ui.selectable_value(&mut self.state.crop_unit, u, u.label());
                            }
                        });

                    if ui
                        .small_button("⇄")
                        .on_hover_text("Swap Width and Height (Toggle Orientation)")
                        .clicked()
                    {
                        let mut w = self.state.crop_width;
                        let mut h = self.state.crop_height;
                        std::mem::swap(&mut w, &mut h);
                        self.state.crop_aspect_preset = CropAspectPreset::Custom;
                        self.apply_crop_dimensions(w as f32, h as f32);
                    }

                    if w_resp.changed() || h_resp.changed() {
                        let new_px_w = unit_to_px(w_display).max(10.0);
                        let new_px_h = unit_to_px(h_display).max(10.0);
                        self.state.crop_aspect_preset = CropAspectPreset::Custom;
                        self.apply_crop_dimensions(new_px_w as f32, new_px_h as f32);
                    }

                    ui.separator();
                    ui.label(egui::RichText::new("DPI:").strong());
                    let mut dpi_val = self.template.dpi;
                    let dpi_resp = ui.add(
                        egui::DragValue::new(&mut dpi_val)
                            .speed(1.0)
                            .range(72..=2400)
                            .suffix(" DPI"),
                    );
                    if dpi_resp.changed() {
                        self.template.dpi = dpi_val.max(72);
                        if self.state.crop_unit != CanvasUnit::Pixels {
                            let new_px_w = unit_to_px(w_display).max(10.0);
                            let new_px_h = unit_to_px(h_display).max(10.0);
                            self.apply_crop_dimensions(new_px_w as f32, new_px_h as f32);
                        }
                    }

                    let alt_text = if self.state.crop_unit == CanvasUnit::Pixels {
                        let mm_w = (self.state.crop_width / dpi) * 25.4;
                        let mm_h = (self.state.crop_height / dpi) * 25.4;
                        format!("({:.1} × {:.1} mm)", mm_w, mm_h)
                    } else {
                        format!(
                            "({:.0} × {:.0} px)",
                            self.state.crop_width, self.state.crop_height
                        )
                    };
                    ui.label(
                        egui::RichText::new(alt_text)
                            .size(11.0)
                            .color(Color32::from_gray(160)),
                    );

                    ui.separator();

                    if ui
                        .small_button("⯐ Drag-Select Area")
                        .on_hover_text(
                            "Clear current crop box and drag on canvas to select a new portion",
                        )
                        .clicked()
                    {
                        self.state.crop_rect = None;
                    }

                    if ui
                        .small_button("Full Canvas")
                        .on_hover_text("Reset crop boundary to entire canvas")
                        .clicked()
                    {
                        self.apply_crop_dimensions(
                            self.template.width_px as f32,
                            self.template.height_px as f32,
                        );
                    }

                    if ui
                        .add(
                            egui::Button::new(egui::RichText::new("✓ Commit (↵)").strong())
                                .fill(Color32::from_rgb(22, 101, 52)),
                        )
                        .clicked()
                    {
                        self.commit_crop();
                    }
                    if ui.small_button("✕ Cancel (Esc)").clicked() {
                        self.cancel_crop();
                    }
                }
                EditorTool::Brush | EditorTool::Eraser => {
                    ui.label("Size:");
                    ui.add(egui::Slider::new(&mut self.state.brush_size, 1.0..=120.0).text("px"));
                    ui.label("Opacity:");
                    ui.add(egui::Slider::new(&mut self.state.brush_opacity, 0.05..=1.0).text(""));
                    if self.state.active_tool == EditorTool::Brush {
                        ui.label("Color:");
                        ui.color_edit_button_srgba(&mut self.state.foreground_color);
                        if ui.small_button("Clear Strokes").clicked() {
                            let stroke_ids: Vec<String> = self
                                .template
                                .elements
                                .iter()
                                .filter(|el| el.r#type == "brush")
                                .map(|el| el.id.clone())
                                .collect();
                            if !stroke_ids.is_empty() {
                                self.state.execute(
                                    self.template,
                                    EditorCommand::BatchDelete { ids: stroke_ids },
                                );
                            }
                        }
                    }
                }
                EditorTool::Zoom => {
                    ui.strong("Left Click: Zoom In  |  Right Click / Alt+Click: Zoom Out");
                    if ui.small_button("100% Actual").clicked() {
                        self.state.zoom = 1.0;
                    }
                    if ui.small_button("Fit Screen").clicked() {
                        self.state.fit_canvas();
                    }
                }
                EditorTool::Gradient => {
                    ui.label("From:");
                    ui.color_edit_button_srgba(&mut self.state.foreground_color);
                    ui.label("To:");
                    ui.color_edit_button_srgba(&mut self.state.background_color);
                    if ui.small_button("⇄ Swap").clicked() {
                        self.state.swap_colors();
                    }
                    if ui.small_button("Apply to Background").clicked() {
                        let fg_hex = format!(
                            "#{:02X}{:02X}{:02X}",
                            self.state.foreground_color.r(),
                            self.state.foreground_color.g(),
                            self.state.foreground_color.b()
                        );
                        let bg_hex = format!(
                            "#{:02X}{:02X}{:02X}",
                            self.state.background_color.r(),
                            self.state.background_color.g(),
                            self.state.background_color.b()
                        );
                        self.state.execute(
                            self.template,
                            EditorCommand::SetBackgroundGradient {
                                from_color: fg_hex,
                                to_color: bg_hex,
                                angle: 90.0,
                            },
                        );
                    }
                    if let Some(id) = &self.state.selected_id.clone() {
                        if ui.small_button("Apply to Element").clicked() {
                            let fg_hex = format!(
                                "#{:02X}{:02X}{:02X}",
                                self.state.foreground_color.r(),
                                self.state.foreground_color.g(),
                                self.state.foreground_color.b()
                            );
                            let bg_hex = format!(
                                "#{:02X}{:02X}{:02X}",
                                self.state.background_color.r(),
                                self.state.background_color.g(),
                                self.state.background_color.b()
                            );
                            self.state.execute(
                                self.template,
                                EditorCommand::UpdateColor {
                                    id: id.clone(),
                                    target: SwatchTarget::Fill,
                                    color: fg_hex,
                                },
                            );
                            self.state.execute(
                                self.template,
                                EditorCommand::UpdateColor {
                                    id: id.clone(),
                                    target: SwatchTarget::Border,
                                    color: bg_hex,
                                },
                            );
                        }
                    }
                }
                EditorTool::Eyedropper => {
                    ui.label("Sampled Color:");
                    if let Some(c) = self.state.sampled_color {
                        let mut swatch = c;
                        ui.color_edit_button_srgba(&mut swatch);
                        ui.label(format!("HEX: {}", self.state.sampled_hex));
                    } else {
                        ui.label("Click or hover over canvas to sample color");
                    }
                }
                EditorTool::PaintBucket => {
                    ui.label("Click element to fill, or click canvas background to set color:");
                    ui.color_edit_button_srgba(&mut self.state.foreground_color);
                }
                _ => {
                    ui.label(format!("Active: {}", self.state.active_tool.name()));
                }
            }

            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                ui.label(format!(
                    "Canvas: {} × {} px @ {} DPI",
                    self.template.width_px, self.template.height_px, self.template.dpi
                ));
            });
        });
    }

    /// Right dock panel: Properties, Layers, Swatches, History, Align.
    fn right_dock_panel(&mut self, ui: &mut Ui) {
        ui.horizontal(|ui| {
            for (tab, label) in [
                (EditorTab::Properties, "Properties"),
                (EditorTab::Layers, "Layers"),
                (EditorTab::Swatches, "Swatches"),
                (EditorTab::History, "History"),
                (EditorTab::Align, "Align"),
            ] {
                if ui
                    .selectable_label(self.state.active_tab == tab, label)
                    .clicked()
                {
                    self.state.active_tab = tab;
                }
            }
        });
        ui.separator();

        match self.state.active_tab {
            EditorTab::Properties => self.properties_tab(ui),
            EditorTab::Layers => self.layers_tab(ui),
            EditorTab::Swatches => self.swatches_tab(ui),
            EditorTab::History => self.history_tab(ui),
            EditorTab::Align => self.align_tab(ui),
        }
    }

    /// Properties Tab (context-aware for selected element or active tool/canvas).
    fn properties_tab(&mut self, ui: &mut Ui) {
        let scroll_height = (ui.available_height() - 20.0).max(350.0);
        egui::ScrollArea::vertical()
            .max_height(scroll_height)
            .show(ui, |ui| {
                if let Some(id) = self.state.selected_id.clone() {
                    self.element_properties_tab(ui, &id);
                } else {
                    self.document_properties_tab(ui);
                }
            });
    }

    /// When an element is selected, show its full attribute panel.
    fn element_properties_tab(&mut self, ui: &mut Ui, id: &str) {
        let before = self.template.clone();

        if let Some(element) = self
            .template
            .elements
            .iter_mut()
            .find(|element| element.id == id)
        {
            ui.horizontal(|ui| {
                ui.heading(&element.name);
                ui.small(format!("[{}]", element.r#type));
            });

            ui.separator();

            // Transform section (TBox coordinates)
            ui.strong("📐 Transform");
            ui.horizontal(|ui| {
                ui.label("Name");
                ui.text_edit_singleline(&mut element.name);
            });
            ui.horizontal(|ui| {
                ui.label("X");
                ui.add(egui::DragValue::new(&mut element.x).speed(1.0));
                ui.label("Y");
                ui.add(egui::DragValue::new(&mut element.y).speed(1.0));
            });
            ui.horizontal(|ui| {
                ui.label("W");
                ui.add(
                    egui::DragValue::new(&mut element.width)
                        .speed(1.0)
                        .range(1.0..=10000.0),
                );
                ui.label("H");
                ui.add(
                    egui::DragValue::new(&mut element.height)
                        .speed(1.0)
                        .range(1.0..=10000.0),
                );
            });
            ui.horizontal(|ui| {
                ui.checkbox(&mut element.visible, "Visible");
                ui.checkbox(&mut element.locked, "Locked");
            });

            ui.separator();

            // Appearance: Fill & Border
            ui.strong("🎨 Appearance & Fill");
            ui.horizontal(|ui| {
                ui.label("Fill Color");
                let mut fill = parse_color(&element.style.background_color, Color32::TRANSPARENT);
                if ui.color_edit_button_srgba(&mut fill).changed() {
                    element.style.background_color =
                        format!("#{:02X}{:02X}{:02X}", fill.r(), fill.g(), fill.b());
                }
                ui.text_edit_singleline(&mut element.style.background_color);
            });

            ui.horizontal(|ui| {
                ui.label("Border Color");
                let mut stroke = parse_color(&element.style.border_color, Color32::DARK_GRAY);
                if ui.color_edit_button_srgba(&mut stroke).changed() {
                    element.style.border_color =
                        format!("#{:02X}{:02X}{:02X}", stroke.r(), stroke.g(), stroke.b());
                }
                ui.text_edit_singleline(&mut element.style.border_color);
            });

            ui.horizontal(|ui| {
                ui.label("Border Width");
                ui.add(egui::DragValue::new(&mut element.style.border_width).range(0..=50));
                ui.label("Corner Radius");
                ui.add(egui::DragValue::new(&mut element.style.border_radius).range(0..=100));
            });

            ui.horizontal(|ui| {
                ui.label("Opacity");
                ui.add(egui::Slider::new(&mut element.style.opacity, 0.0..=1.0));
            });

            // Typography section (for text and dynamic_text)
            if element.r#type == "text" || element.r#type == "dynamic_text" {
                ui.separator();
                ui.strong("🔤 Typography & Data Binding");

                ui.horizontal(|ui| {
                    ui.label("Font Family");
                    ui.text_edit_singleline(&mut element.style.font_family);
                });

                ui.horizontal(|ui| {
                    ui.label("Font Size");
                    ui.add(egui::DragValue::new(&mut element.style.font_size).range(6..=200));
                    ui.checkbox(&mut element.style.font_bold, "Bold");
                    ui.checkbox(&mut element.style.font_italic, "Italic");
                });

                ui.horizontal(|ui| {
                    ui.label("Text Color");
                    let mut font_col = parse_color(&element.style.font_color, Color32::BLACK);
                    if ui.color_edit_button_srgba(&mut font_col).changed() {
                        element.style.font_color = format!(
                            "#{:02X}{:02X}{:02X}",
                            font_col.r(),
                            font_col.g(),
                            font_col.b()
                        );
                    }
                    ui.text_edit_singleline(&mut element.style.font_color);
                });

                ui.horizontal(|ui| {
                    ui.label("Static Text");
                    let mut content = element.static_content.clone().unwrap_or_default();
                    if ui.text_edit_singleline(&mut content).changed() {
                        element.static_content = (!content.trim().is_empty()).then_some(content);
                    }
                });

                // Excel data column binding
                ui.horizontal(|ui| {
                    ui.label("Data Binding");
                    let mut selected = element.binding.clone().unwrap_or_else(|| "None".into());
                    egui::ComboBox::from_id_salt(format!("binding_{}", element.id))
                        .selected_text(&selected)
                        .show_ui(ui, |ui| {
                            if ui
                                .selectable_value(&mut selected, "None".into(), "None")
                                .clicked()
                            {
                                element.binding = None;
                            }
                            for col in self.available_columns {
                                if ui
                                    .selectable_value(&mut selected, col.clone(), col)
                                    .clicked()
                                {
                                    element.binding = Some(col.clone());
                                }
                            }
                        });
                });
            }

            // Photo section
            if element.r#type == "photo" {
                ui.separator();
                ui.strong("🖼 Photo Binding & Framing");

                ui.horizontal(|ui| {
                    ui.label("Photo Key Column");
                    let mut selected = element
                        .binding
                        .clone()
                        .unwrap_or_else(|| "PIN / Fallback".into());
                    egui::ComboBox::from_id_salt(format!("photo_binding_{}", element.id))
                        .selected_text(&selected)
                        .show_ui(ui, |ui| {
                            if ui
                                .selectable_value(
                                    &mut selected,
                                    "PIN / Fallback".into(),
                                    "PIN / Fallback",
                                )
                                .clicked()
                            {
                                element.binding = None;
                            }
                            for col in self.available_columns {
                                if ui
                                    .selectable_value(&mut selected, col.clone(), col)
                                    .clicked()
                                {
                                    element.binding = Some(col.clone());
                                }
                            }
                        });
                });

                ui.horizontal(|ui| {
                    ui.label("Mask Shape");
                    egui::ComboBox::from_id_salt(format!("mask_shape_{}", element.id))
                        .selected_text(&element.style.mask_shape)
                        .show_ui(ui, |ui| {
                            ui.selectable_value(
                                &mut element.style.mask_shape,
                                "rect".into(),
                                "Rectangle",
                            );
                            ui.selectable_value(
                                &mut element.style.mask_shape,
                                "rounded".into(),
                                "Rounded",
                            );
                            ui.selectable_value(
                                &mut element.style.mask_shape,
                                "oval".into(),
                                "Oval / Circle",
                            );
                        });
                });
            }

            // Layer arrangement buttons
            ui.separator();
            ui.strong("📑 Layer Management");
            ui.horizontal_wrapped(|ui| {
                if ui.button("⤒ Front").clicked() {
                    self.state.execute(
                        self.template,
                        EditorCommand::BringToFront { id: id.to_string() },
                    );
                }
                if ui.button("▲ Up").clicked() {
                    self.state
                        .execute(self.template, EditorCommand::Raise { id: id.to_string() });
                }
                if ui.button("▼ Down").clicked() {
                    self.state
                        .execute(self.template, EditorCommand::Lower { id: id.to_string() });
                }
                if ui.button("⤓ Back").clicked() {
                    self.state.execute(
                        self.template,
                        EditorCommand::SendToBack { id: id.to_string() },
                    );
                }
                if ui.button("⧉ Duplicate").clicked() {
                    self.state.execute(
                        self.template,
                        EditorCommand::Duplicate { id: id.to_string() },
                    );
                }
                if ui.button("🗑 Delete").clicked() {
                    self.state
                        .execute(self.template, EditorCommand::Delete { id: id.to_string() });
                }
            });
        }

        self.state.history.record_change(before, self.template);
    }

    /// When no element is selected, show canvas document properties and active tool parameters.
    fn document_properties_tab(&mut self, ui: &mut Ui) {
        ui.heading("Document Properties");
        ui.separator();

        ui.horizontal(|ui| {
            ui.label("Canvas Name");
            ui.text_edit_singleline(&mut self.template.name);
        });

        ui.horizontal(|ui| {
            ui.label("Dimensions:");
            ui.strong(format!(
                "{} × {} px",
                self.template.width_px, self.template.height_px
            ));
        });

        ui.horizontal(|ui| {
            ui.label("Resolution:");
            ui.strong(format!("{} DPI", self.template.dpi));
        });

        ui.horizontal(|ui| {
            ui.label("Background Color");
            let mut bg = parse_color(&self.template.background_color, Color32::WHITE);
            if ui.color_edit_button_srgba(&mut bg).changed() {
                self.template.background_color =
                    format!("#{:02X}{:02X}{:02X}", bg.r(), bg.g(), bg.b());
            }
            ui.text_edit_singleline(&mut self.template.background_color);
        });

        ui.horizontal(|ui| {
            ui.label("Safe Area Margin (mm)");
            ui.add(egui::DragValue::new(&mut self.template.safe_area_margin_mm).range(0.0..=50.0));
        });

        ui.separator();
        ui.heading(format!("Active Tool: {}", self.state.active_tool.name()));
        ui.label("Select any element on canvas to inspect its TBox transform and edit properties.");
    }

    /// Layers panel: list layers with visibility, lock, reorder, delete.
    fn layers_tab(&mut self, ui: &mut Ui) {
        ui.horizontal(|ui| {
            ui.heading("Layers");
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if ui
                    .small_button("🗑")
                    .on_hover_text("Delete Selected Layer")
                    .clicked()
                {
                    if let Some(id) = self.state.selected_id.clone() {
                        self.state
                            .execute(self.template, EditorCommand::Delete { id });
                    }
                }
                if ui.small_button("+ Text").clicked() {
                    self.add_element("text");
                }
                if ui.small_button("+ Photo").clicked() {
                    self.add_element("photo");
                }
                if ui.small_button("+ Shape").clicked() {
                    self.add_element("rect");
                }
            });
        });
        ui.separator();

        let mut elements_rev: Vec<_> = self.template.elements.clone();
        elements_rev.sort_by_key(|element| -element.z_index);

        let scroll_height = (ui.available_height() - 60.0).max(350.0);
        egui::ScrollArea::vertical()
            .max_height(scroll_height)
            .show(ui, |ui| {
                for element in elements_rev {
                    let is_selected = self.state.selected_id.as_deref() == Some(&element.id);
                    ui.group(|ui| {
                        ui.horizontal(|ui| {
                            // Visibility toggle
                            let vis_icon = if element.visible { "👁" } else { "⊘" };
                            if ui.small_button(vis_icon).clicked() {
                                self.state.execute(
                                    self.template,
                                    EditorCommand::SetVisibility {
                                        id: element.id.clone(),
                                        visible: !element.visible,
                                    },
                                );
                            }

                            // Lock toggle
                            let lock_icon = if element.locked { "🔒" } else { "🔓" };
                            if ui.small_button(lock_icon).clicked() {
                                self.state.execute(
                                    self.template,
                                    EditorCommand::SetLocked {
                                        id: element.id.clone(),
                                        locked: !element.locked,
                                    },
                                );
                            }

                            // Type icon
                            let type_icon = match element.r#type.as_str() {
                                "photo" => "🖼",
                                "text" | "dynamic_text" => "T",
                                "round_rect" => "▢",
                                "ellipse" => "◯",
                                "line" => "─",
                                _ => "▭",
                            };
                            ui.small(type_icon);

                            let label = egui::RichText::new(&element.name);
                            let label = if is_selected {
                                label.strong().color(Color32::from_rgb(56, 189, 248))
                            } else {
                                label
                            };

                            if ui.selectable_label(is_selected, label).clicked() {
                                self.state.selected_id = Some(element.id.clone());
                            }

                            // Reordering
                            ui.with_layout(
                                egui::Layout::right_to_left(egui::Align::Center),
                                |ui| {
                                    if ui.small_button("▼").clicked() {
                                        self.state.execute(
                                            self.template,
                                            EditorCommand::Lower {
                                                id: element.id.clone(),
                                            },
                                        );
                                    }
                                    if ui.small_button("▲").clicked() {
                                        self.state.execute(
                                            self.template,
                                            EditorCommand::Raise {
                                                id: element.id.clone(),
                                            },
                                        );
                                    }
                                },
                            );
                        });
                    });
                }
            });
    }

    /// Swatches Tab.
    fn swatches_tab(&mut self, ui: &mut Ui) {
        ui.heading("Color Swatches");
        ui.horizontal(|ui| {
            ui.label("Target:");
            for (target, label) in [
                (SwatchTarget::Fill, "Fill"),
                (SwatchTarget::Border, "Border"),
                (SwatchTarget::Font, "Font"),
                (SwatchTarget::Background, "Background"),
            ] {
                if ui
                    .selectable_label(self.state.swatch_target == target, label)
                    .clicked()
                {
                    self.state.swatch_target = target;
                }
            }
        });
        ui.separator();

        egui::Grid::new("swatches_grid")
            .spacing([6.0, 6.0])
            .show(ui, |ui| {
                for (index, (hex, name)) in SWATCHES.iter().enumerate() {
                    let color = parse_color(hex, Color32::WHITE);
                    let (rect, resp) = ui.allocate_exact_size(Vec2::splat(24.0), Sense::click());
                    let painter = ui.painter_at(rect);
                    painter.rect_filled(rect, 3.0, color);
                    painter.rect_stroke(rect, 3.0, Stroke::new(1.0_f32, Color32::from_gray(80)));

                    if resp.on_hover_text(format!("{name} ({hex})")).clicked() {
                        self.apply_swatch_color(hex);
                    }

                    if (index + 1) % 6 == 0 {
                        ui.end_row();
                    }
                }
            });

        ui.separator();
        ui.horizontal(|ui| {
            ui.label("Custom Hex:");
            ui.text_edit_singleline(&mut self.state.custom_hex_color);
            if ui.button("Apply").clicked() {
                let hex = self.state.custom_hex_color.clone();
                self.apply_swatch_color(&hex);
            }
        });
    }

    fn apply_swatch_color(&mut self, hex: &str) {
        if self.state.swatch_target == SwatchTarget::Background {
            self.template.background_color = hex.to_string();
        } else if let Some(id) = self.state.selected_id.clone() {
            self.state.execute(
                self.template,
                EditorCommand::UpdateColor {
                    id,
                    target: self.state.swatch_target,
                    color: hex.to_string(),
                },
            );
        }
        self.state.foreground_color = parse_color(hex, Color32::BLACK);
    }

    /// History Tab: action stack.
    fn history_tab(&mut self, ui: &mut Ui) {
        ui.heading("Action History");
        ui.label(format!(
            "{} undo steps recorded",
            self.state.history.action_names.len()
        ));
        ui.separator();

        let scroll_height = (ui.available_height() - 60.0).max(350.0);
        egui::ScrollArea::vertical()
            .max_height(scroll_height)
            .show(ui, |ui| {
                for (index, name) in self.state.history.action_names.iter().enumerate() {
                    ui.label(format!("{}. {}", index + 1, name));
                }
            });
    }

    /// Align Tab: quick alignment and distribution operations.
    fn align_tab(&mut self, ui: &mut Ui) {
        ui.heading("Alignment & Distribution");
        ui.label("Align selected element relative to canvas boundary:");
        ui.separator();

        egui::Grid::new("align_grid")
            .spacing([8.0, 8.0])
            .show(ui, |ui| {
                for (label, align) in [
                    ("⇤ Align Left", AlignmentType::Left),
                    ("⇥ Align Right", AlignmentType::Right),
                    ("⇋ Center Horizontal", AlignmentType::CenterHorizontal),
                    ("⤒ Align Top", AlignmentType::Top),
                    ("⤓ Align Bottom", AlignmentType::Bottom),
                    ("↕ Center Vertical", AlignmentType::CenterVertical),
                    ("⊡ Center on Card", AlignmentType::CenterOnCard),
                ] {
                    if ui.button(label).clicked() {
                        if let Some(id) = self.state.selected_id.clone() {
                            self.state.execute(
                                self.template,
                                EditorCommand::Align {
                                    id,
                                    alignment: align,
                                },
                            );
                        }
                    }
                    ui.end_row();
                }
            });
    }

    /// Main canvas viewport with interactive rulers, TBox, and HUD.
    fn canvas_viewport(&mut self, ui: &mut Ui) {
        let full_size = ui.available_size();
        let (view_rect, response) = ui.allocate_exact_size(full_size, Sense::click_and_drag());
        let painter = ui.painter_at(view_rect);

        // Fill background
        painter.rect_filled(view_rect, 0.0, Color32::from_rgb(28, 28, 30));

        let ruler_offset = if self.state.show_rulers {
            RULER_THICKNESS
        } else {
            0.0
        };
        let canvas_area = Rect::from_min_max(
            view_rect.min + Vec2::new(ruler_offset, ruler_offset),
            view_rect.max - Vec2::new(0.0, 36.0), // Reserve bottom HUD
        );

        let transform = CanvasTransform::fit(
            canvas_area.shrink(16.0),
            self.template,
            self.state.zoom,
            self.state.pan,
        );
        let scene_rect = transform.scene_rect(self.template);

        // Draw card shadow and canvas background
        painter.rect_filled(
            scene_rect.translate(Vec2::new(3.0, 4.0)),
            2.0,
            Color32::from_black_alpha(100),
        );
        painter.rect_filled(
            scene_rect,
            2.0,
            parse_color(&self.template.background_color, Color32::WHITE),
        );

        // Draw guides & elements
        self.draw_guides(&painter, scene_rect, transform);

        let mut elements_sorted = self.template.elements.clone();
        elements_sorted.sort_by_key(|element| element.z_index);
        for element in &elements_sorted {
            if element.visible {
                self.draw_element(&painter, element, transform);
            }
        }

        // Draw live drawing / marquee / shape preview
        self.draw_live_overlays(&painter, transform);

        // Draw TBox for selected element
        if let Some(id) = self.state.selected_id.clone() {
            if let Some(selected_elem) = self.template.get_element_by_id(&id).cloned() {
                self.draw_tbox(&painter, &selected_elem, transform);
            }
        }

        // Draw interactive rulers
        let pointer_pos = response.hover_pos();
        if self.state.show_rulers {
            self.draw_rulers(&painter, view_rect, canvas_area, transform, pointer_pos);
        }

        // Draw and handle canvas scrollbars when canvas exceeds available space
        let canvas_w = self.template.width_px as f32 * transform.scale;
        let canvas_h = self.template.height_px as f32 * transform.scale;
        let exceeds_h = canvas_w > canvas_area.width()
            || scene_rect.min.x < canvas_area.min.x
            || scene_rect.max.x > canvas_area.max.x;
        let exceeds_v = canvas_h > canvas_area.height()
            || scene_rect.min.y < canvas_area.min.y
            || scene_rect.max.y > canvas_area.max.y;

        let over_scrollbar = self.draw_and_handle_scrollbars(
            &painter,
            &response,
            canvas_area,
            transform,
            exceeds_h,
            exceeds_v,
        );

        // Handle interactions & cursor icons
        self.handle_canvas_input(response, view_rect, canvas_area, transform, over_scrollbar);

        // Inline text editor overlay
        self.show_inline_text_editor(ui, transform);

        // Bottom HUD
        self.draw_hud(&painter, view_rect);

        // Draw custom designed floating tool cursor
        if let Some(pos) = pointer_pos {
            if canvas_area.contains(pos) && !over_scrollbar {
                self.draw_custom_cursor(&painter, pos, transform);
            }
        }
    }

    /// Draw and handle canvas scrollbars when canvas exceeds available space.
    fn draw_and_handle_scrollbars(
        &mut self,
        painter: &egui::Painter,
        response: &Response,
        canvas_area: Rect,
        transform: CanvasTransform,
        exceeds_h: bool,
        exceeds_v: bool,
    ) -> bool {
        if !exceeds_h && !exceeds_v {
            self.state.scrollbar_dragging_h = false;
            self.state.scrollbar_dragging_v = false;
            return false;
        }

        const THICKNESS: f32 = 10.0;
        const MARGIN: f32 = 3.0;
        let pointer = response
            .interact_pointer_pos()
            .or_else(|| response.hover_pos());

        let canvas_w = self.template.width_px as f32 * transform.scale;
        let canvas_h = self.template.height_px as f32 * transform.scale;

        let v_track = if exceeds_v {
            let bottom = if exceeds_h {
                canvas_area.max.y - THICKNESS - MARGIN * 2.0
            } else {
                canvas_area.max.y - MARGIN
            };
            Some(Rect::from_min_max(
                Pos2::new(
                    canvas_area.max.x - THICKNESS - MARGIN,
                    canvas_area.min.y + MARGIN,
                ),
                Pos2::new(canvas_area.max.x - MARGIN, bottom),
            ))
        } else {
            None
        };

        let h_track = if exceeds_h {
            let right = if exceeds_v {
                canvas_area.max.x - THICKNESS - MARGIN * 2.0
            } else {
                canvas_area.max.x - MARGIN
            };
            Some(Rect::from_min_max(
                Pos2::new(
                    canvas_area.min.x + MARGIN,
                    canvas_area.max.y - THICKNESS - MARGIN,
                ),
                Pos2::new(right, canvas_area.max.y - MARGIN),
            ))
        } else {
            None
        };

        let mut over_scrollbar = false;

        // --- Vertical Scrollbar ---
        if let Some(track) = v_track {
            let max_pan_y = ((canvas_h - canvas_area.height()) / 2.0).max(0.0) + 120.0;
            let thumb_h = (track.height() * (canvas_area.height() / (canvas_h + 240.0)))
                .clamp(28.0, track.height());
            let travel = (track.height() - thumb_h).max(1.0);
            let t_y = if max_pan_y > 0.0 {
                ((max_pan_y - self.state.pan.y) / (2.0 * max_pan_y)).clamp(0.0, 1.0)
            } else {
                0.5
            };
            let thumb_y = track.min.y + t_y * travel;
            let thumb = Rect::from_min_size(
                Pos2::new(track.min.x, thumb_y),
                Vec2::new(track.width(), thumb_h),
            );

            let is_hovered = pointer.is_some_and(|p| track.contains(p));
            if is_hovered || self.state.scrollbar_dragging_v {
                over_scrollbar = true;
            }

            if response.drag_started() && pointer.is_some_and(|p| track.contains(p)) {
                self.state.scrollbar_dragging_v = true;
            }

            if self.state.scrollbar_dragging_v {
                if response.dragged() {
                    let dy = response.drag_delta().y;
                    let dt = dy / travel;
                    self.state.pan.y =
                        (self.state.pan.y - dt * (2.0 * max_pan_y)).clamp(-max_pan_y, max_pan_y);
                }
            } else if response.clicked()
                && pointer.is_some_and(|p| track.contains(p) && !thumb.contains(p))
            {
                if let Some(pos) = pointer {
                    let click_t = ((pos.y - track.min.y - thumb_h / 2.0) / travel).clamp(0.0, 1.0);
                    self.state.pan.y = max_pan_y - click_t * (2.0 * max_pan_y);
                }
            }

            if response.drag_stopped() {
                self.state.scrollbar_dragging_v = false;
            }

            // Draw track
            painter.rect_filled(track, 5.0, Color32::from_rgba_unmultiplied(20, 20, 24, 180));
            // Draw thumb
            let thumb_fill = if self.state.scrollbar_dragging_v {
                Color32::from_rgba_unmultiplied(180, 180, 195, 230)
            } else if is_hovered {
                Color32::from_rgba_unmultiplied(140, 140, 155, 200)
            } else {
                Color32::from_rgba_unmultiplied(100, 100, 115, 140)
            };
            painter.rect_filled(thumb, 4.0, thumb_fill);
        }

        // --- Horizontal Scrollbar ---
        if let Some(track) = h_track {
            let max_pan_x = ((canvas_w - canvas_area.width()) / 2.0).max(0.0) + 120.0;
            let thumb_w = (track.width() * (canvas_area.width() / (canvas_w + 240.0)))
                .clamp(28.0, track.width());
            let travel = (track.width() - thumb_w).max(1.0);
            let t_x = if max_pan_x > 0.0 {
                ((max_pan_x - self.state.pan.x) / (2.0 * max_pan_x)).clamp(0.0, 1.0)
            } else {
                0.5
            };
            let thumb_x = track.min.x + t_x * travel;
            let thumb = Rect::from_min_size(
                Pos2::new(thumb_x, track.min.y),
                Vec2::new(thumb_w, track.height()),
            );

            let is_hovered = pointer.is_some_and(|p| track.contains(p));
            if is_hovered || self.state.scrollbar_dragging_h {
                over_scrollbar = true;
            }

            if response.drag_started() && pointer.is_some_and(|p| track.contains(p)) {
                self.state.scrollbar_dragging_h = true;
            }

            if self.state.scrollbar_dragging_h {
                if response.dragged() {
                    let dx = response.drag_delta().x;
                    let dt = dx / travel;
                    self.state.pan.x =
                        (self.state.pan.x - dt * (2.0 * max_pan_x)).clamp(-max_pan_x, max_pan_x);
                }
            } else if response.clicked()
                && pointer.is_some_and(|p| track.contains(p) && !thumb.contains(p))
            {
                if let Some(pos) = pointer {
                    let click_t = ((pos.x - track.min.x - thumb_w / 2.0) / travel).clamp(0.0, 1.0);
                    self.state.pan.x = max_pan_x - click_t * (2.0 * max_pan_x);
                }
            }

            if response.drag_stopped() {
                self.state.scrollbar_dragging_h = false;
            }

            // Draw track
            painter.rect_filled(track, 5.0, Color32::from_rgba_unmultiplied(20, 20, 24, 180));
            // Draw thumb
            let thumb_fill = if self.state.scrollbar_dragging_h {
                Color32::from_rgba_unmultiplied(180, 180, 195, 230)
            } else if is_hovered {
                Color32::from_rgba_unmultiplied(140, 140, 155, 200)
            } else {
                Color32::from_rgba_unmultiplied(100, 100, 115, 140)
            };
            painter.rect_filled(thumb, 4.0, thumb_fill);
        }

        over_scrollbar
    }

    /// Render floating inline text editor overlay when a text element is being edited.
    fn show_inline_text_editor(&mut self, ui: &mut Ui, transform: CanvasTransform) {
        let Some(edit_id) = self.state.editing_text_id.clone() else {
            return;
        };
        let Some(elem) = self.template.get_element_by_id(&edit_id).cloned() else {
            self.state.editing_text_id = None;
            return;
        };

        let elem_rect = Rect::from_min_size(
            transform.scene_to_screen(Pos2::new(elem.x as f32, elem.y as f32)),
            Vec2::new(
                elem.width as f32 * transform.scale,
                elem.height as f32 * transform.scale,
            ),
        );

        let mut should_commit = false;
        let mut should_cancel = false;

        egui::Area::new(egui::Id::new("canvas_inline_text_editor"))
            .fixed_pos(elem_rect.left_top() - Vec2::new(2.0, 2.0))
            .order(egui::Order::Foreground)
            .show(ui.ctx(), |ui| {
                egui::Frame::popup(ui.style())
                    .fill(Color32::from_rgb(24, 24, 28))
                    .stroke(Stroke::new(1.5_f32, Color32::from_rgb(59, 130, 246)))
                    .inner_margin(4.0)
                    .rounding(4.0)
                    .show(ui, |ui| {
                        ui.horizontal(|ui| {
                            let edit_w = (elem_rect.width() + 16.0).clamp(160.0, 480.0);
                            let font_sz =
                                (elem.style.font_size as f32 * transform.scale).clamp(12.0, 28.0);
                            let text_edit =
                                egui::TextEdit::singleline(&mut self.state.editing_text_buffer)
                                    .desired_width(edit_w)
                                    .font(FontId::proportional(font_sz))
                                    .text_color(Color32::WHITE);
                            let res = ui.add(text_edit);
                            res.request_focus();

                            if res.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter)) {
                                should_commit = true;
                            }

                            if ui
                                .small_button("✔")
                                .on_hover_text("Commit text (Enter)")
                                .clicked()
                            {
                                should_commit = true;
                            }
                            if ui.small_button("✖").on_hover_text("Cancel (Esc)").clicked() {
                                should_cancel = true;
                            }
                        });
                    });
            });

        if ui.input(|i| i.key_pressed(egui::Key::Enter)) {
            should_commit = true;
        } else if ui.input(|i| i.key_pressed(egui::Key::Escape)) {
            should_cancel = true;
        }

        if should_commit {
            self.commit_editing_text();
        } else if should_cancel {
            self.cancel_editing_text();
        }
    }

    /// Apply specified width and height to current crop rectangle, clamped to canvas bounds.
    pub fn apply_crop_dimensions(&mut self, w: f32, h: f32) {
        let w = w.max(10.0);
        let h = h.max(10.0);
        let canvas_w = self.template.width_px as f32;
        let canvas_h = self.template.height_px as f32;

        let center = if let Some(r) = self.state.crop_rect {
            r.center()
        } else {
            Pos2::new(canvas_w / 2.0, canvas_h / 2.0)
        };

        let min_x = (center.x - w / 2.0).clamp(0.0, (canvas_w - w).max(0.0));
        let min_y = (center.y - h / 2.0).clamp(0.0, (canvas_h - h).max(0.0));
        let new_rect = Rect::from_min_size(Pos2::new(min_x, min_y), Vec2::new(w, h));

        self.state.crop_rect = Some(new_rect);
        self.state.crop_width = w as f64;
        self.state.crop_height = h as f64;
    }

    /// Initialize the crop rectangle if currently uninitialized.
    pub fn init_crop_if_needed(&mut self) {
        if self.state.crop_rect.is_none() {
            let w = self.template.width_px as f32;
            let h = self.template.height_px as f32;
            self.state.crop_rect = Some(Rect::from_min_size(Pos2::ZERO, Vec2::new(w, h)));
            self.state.crop_width = w as f64;
            self.state.crop_height = h as f64;
        }
    }

    /// Commit the current crop rectangle, updating canvas size and element positions.
    pub fn commit_crop(&mut self) {
        let crop_rect = self.state.crop_rect.take().unwrap_or_else(|| {
            Rect::from_min_size(
                Pos2::ZERO,
                Vec2::new(
                    self.template.width_px as f32,
                    self.template.height_px as f32,
                ),
            )
        });
        let new_width = (crop_rect.width().round() as u32).max(10);
        let new_height = (crop_rect.height().round() as u32).max(10);
        let offset_x = f64::from(crop_rect.left().round());
        let offset_y = f64::from(crop_rect.top().round());

        self.state.execute(
            self.template,
            EditorCommand::CropCanvas {
                new_width,
                new_height,
                offset_x,
                offset_y,
            },
        );
        self.state.crop_drag_handle = None;
        self.state.crop_drag_start_pointer = None;
        self.state.crop_drag_start_rect = None;
        self.state.active_tool = EditorTool::Move;
    }

    /// Cancel the current crop action and restore the previous view state.
    pub fn cancel_crop(&mut self) {
        self.state.crop_rect = None;
        self.state.crop_drag_handle = None;
        self.state.crop_drag_start_pointer = None;
        self.state.crop_drag_start_rect = None;
        self.state.active_tool = EditorTool::Move;
    }

    fn hit_test_crop_handle(&self, screen_crop: Rect, pointer: Pos2) -> Option<CropHandle> {
        let handle_radius = 12.0_f32;
        let is_near = |p: Pos2| (p - pointer).length() <= handle_radius;

        // Corners first
        if is_near(screen_crop.left_top()) {
            return Some(CropHandle::TopLeft);
        }
        if is_near(screen_crop.right_top()) {
            return Some(CropHandle::TopRight);
        }
        if is_near(screen_crop.left_bottom()) {
            return Some(CropHandle::BottomLeft);
        }
        if is_near(screen_crop.right_bottom()) {
            return Some(CropHandle::BottomRight);
        }

        // Edge midpoints
        if is_near(Pos2::new(screen_crop.center().x, screen_crop.top())) {
            return Some(CropHandle::TopCenter);
        }
        if is_near(Pos2::new(screen_crop.center().x, screen_crop.bottom())) {
            return Some(CropHandle::BottomCenter);
        }
        if is_near(Pos2::new(screen_crop.left(), screen_crop.center().y)) {
            return Some(CropHandle::MiddleLeft);
        }
        if is_near(Pos2::new(screen_crop.right(), screen_crop.center().y)) {
            return Some(CropHandle::MiddleRight);
        }

        // Inside
        if screen_crop.contains(pointer) {
            return Some(CropHandle::Inside);
        }

        None
    }

    /// Draw live interactive preview overlays for Shape, Marquee, Brush, Crop, and Gradient.
    fn draw_live_overlays(&self, painter: &egui::Painter, transform: CanvasTransform) {
        let primary_cyan = Color32::from_rgb(56, 189, 248);

        // 1. Live Shape creation preview
        if let Some(rect) = self.state.live_shape_rect {
            let screen_min = transform.scene_to_screen(rect.min);
            let screen_max = transform.scene_to_screen(rect.max);
            let screen_rect = Rect::from_two_pos(screen_min, screen_max);

            let preview_fill = Color32::from_rgba_premultiplied(
                self.state.shape_fill_color.r(),
                self.state.shape_fill_color.g(),
                self.state.shape_fill_color.b(),
                80,
            );
            let preview_stroke = Stroke::new(
                (self.state.shape_border_width as f32 * transform.scale).max(1.5),
                self.state.shape_border_color,
            );

            match self.state.active_shape {
                ShapeKind::Rectangle => {
                    painter.rect_filled(screen_rect, 0.0, preview_fill);
                    painter.rect_stroke(screen_rect, 0.0, preview_stroke);
                }
                ShapeKind::RoundedRectangle => {
                    let r = self.state.shape_corner_radius as f32 * transform.scale;
                    painter.rect_filled(screen_rect, r, preview_fill);
                    painter.rect_stroke(screen_rect, r, preview_stroke);
                }
                ShapeKind::Ellipse => {
                    let rx = screen_rect.width() / 2.0;
                    let ry = screen_rect.height() / 2.0;
                    let center = screen_rect.center();
                    let pts: Vec<Pos2> = (0..32)
                        .map(|i| {
                            let a = i as f32 * std::f32::consts::TAU / 32.0;
                            Pos2::new(center.x + rx * a.cos(), center.y + ry * a.sin())
                        })
                        .collect();
                    painter.add(egui::Shape::convex_polygon(
                        pts,
                        preview_fill,
                        preview_stroke,
                    ));
                }
                ShapeKind::Line => {
                    painter.line_segment(
                        [screen_rect.left_top(), screen_rect.right_bottom()],
                        preview_stroke,
                    );
                }
            }

            // Dimension label
            let dim_text = format!("{:.0} × {:.0} px", rect.width().abs(), rect.height().abs());
            painter.text(
                screen_rect.center(),
                Align2::CENTER_CENTER,
                dim_text,
                FontId::proportional(11.0),
                Color32::WHITE,
            );
        }

        // 2. Live Marquee selection preview (marching-ants style)
        if let Some(rect) = self.state.live_marquee_rect {
            let screen_rect = Rect::from_two_pos(
                transform.scene_to_screen(rect.min),
                transform.scene_to_screen(rect.max),
            );
            painter.rect_filled(
                screen_rect,
                0.0,
                Color32::from_rgba_premultiplied(56, 189, 248, 35),
            );
            painter.rect_stroke(screen_rect, 0.0, Stroke::new(1.5_f32, primary_cyan));
        }

        // 3. Live Brush stroke preview
        if !self.state.live_brush_stroke.is_empty() {
            let radius = (self.state.brush_size * transform.scale / 2.0).max(1.5);
            let brush_color = Color32::from_rgba_premultiplied(
                self.state.foreground_color.r(),
                self.state.foreground_color.g(),
                self.state.foreground_color.b(),
                (self.state.brush_opacity * 255.0) as u8,
            );
            let stroke = Stroke::new(radius * 2.0, brush_color);
            for window in self.state.live_brush_stroke.windows(2) {
                let p1 = transform.scene_to_screen(window[0]);
                let p2 = transform.scene_to_screen(window[1]);
                painter.line_segment([p1, p2], stroke);
                painter.circle_filled(p1, radius, brush_color);
                painter.circle_filled(p2, radius, brush_color);
            }
            if self.state.live_brush_stroke.len() == 1 {
                let p0 = transform.scene_to_screen(self.state.live_brush_stroke[0]);
                painter.circle_filled(p0, radius, brush_color);
            }
        }

        // 4. Object Select Hover Highlight
        if self.state.active_tool == EditorTool::ObjectSelect {
            if let Some(hovered_id) = &self.state.hovered_object_id {
                if let Some(elem) = self.template.get_element_by_id(hovered_id) {
                    let elem_rect = Rect::from_min_size(
                        transform.scene_to_screen(Pos2::new(elem.x as f32, elem.y as f32)),
                        Vec2::new(
                            elem.width as f32 * transform.scale,
                            elem.height as f32 * transform.scale,
                        ),
                    );
                    painter.rect_stroke(
                        elem_rect,
                        2.0,
                        Stroke::new(2.5_f32, Color32::from_rgb(34, 211, 238)),
                    );
                    let badge_text = format!("{} ({})", elem.name, elem.r#type);
                    painter.text(
                        elem_rect.left_top() - Vec2::new(0.0, 16.0),
                        Align2::LEFT_TOP,
                        badge_text,
                        FontId::proportional(11.0),
                        Color32::from_rgb(34, 211, 238),
                    );
                }
            }
        }

        // 5. Gradient vector ray overlay
        if self.state.active_tool == EditorTool::Gradient {
            if let (Some(start), Some(end)) = (self.state.gradient_start, self.state.gradient_end) {
                let p_start = transform.scene_to_screen(start);
                let p_end = transform.scene_to_screen(end);
                painter.line_segment(
                    [p_start, p_end],
                    Stroke::new(2.0_f32, Color32::from_rgb(56, 189, 248)),
                );
                painter.circle_filled(p_start, 6.0, self.state.foreground_color);
                painter.circle_stroke(p_start, 6.0, Stroke::new(2.0_f32, Color32::WHITE));
                painter.circle_filled(p_end, 6.0, self.state.background_color);
                painter.circle_stroke(p_end, 6.0, Stroke::new(2.0_f32, Color32::WHITE));

                let mid = p_start + (p_end - p_start) * 0.5;
                painter.circle_filled(mid, 4.0, Color32::WHITE);
            }
        }

        // 6. Crop Tool Overlay: Dark Shield, Rule of Thirds grid, L-handles, Dimension badge
        if self.state.active_tool == EditorTool::Crop {
            let canvas_min = transform.scene_to_screen(Pos2::ZERO);
            let canvas_max = transform.scene_to_screen(Pos2::new(
                self.template.width_px as f32,
                self.template.height_px as f32,
            ));
            let canvas_screen = Rect::from_min_max(canvas_min, canvas_max);

            if let Some(crop_scene) = self.state.crop_rect {
                if crop_scene.width() > 2.0 && crop_scene.height() > 2.0 {
                    let screen_crop = Rect::from_min_max(
                        transform.scene_to_screen(crop_scene.min),
                        transform.scene_to_screen(crop_scene.max),
                    );

                    // 6a. Dark Shield on 4 sides outside the crop rect
                    let shield_color = Color32::from_black_alpha(160);
                    if screen_crop.top() > canvas_screen.top() {
                        painter.rect_filled(
                            Rect::from_min_max(
                                canvas_screen.min,
                                Pos2::new(canvas_screen.right(), screen_crop.top()),
                            ),
                            0.0,
                            shield_color,
                        );
                    }
                    if screen_crop.bottom() < canvas_screen.bottom() {
                        painter.rect_filled(
                            Rect::from_min_max(
                                Pos2::new(canvas_screen.left(), screen_crop.bottom()),
                                canvas_screen.max,
                            ),
                            0.0,
                            shield_color,
                        );
                    }
                    if screen_crop.left() > canvas_screen.left() {
                        painter.rect_filled(
                            Rect::from_min_max(
                                Pos2::new(
                                    canvas_screen.left(),
                                    screen_crop.top().max(canvas_screen.top()),
                                ),
                                Pos2::new(
                                    screen_crop.left(),
                                    screen_crop.bottom().min(canvas_screen.bottom()),
                                ),
                            ),
                            0.0,
                            shield_color,
                        );
                    }
                    if screen_crop.right() < canvas_screen.right() {
                        painter.rect_filled(
                            Rect::from_min_max(
                                Pos2::new(
                                    screen_crop.right(),
                                    screen_crop.top().max(canvas_screen.top()),
                                ),
                                Pos2::new(
                                    canvas_screen.right(),
                                    screen_crop.bottom().min(canvas_screen.bottom()),
                                ),
                            ),
                            0.0,
                            shield_color,
                        );
                    }

                    // 6b. Rule of Thirds grid
                    let grid_stroke = Stroke::new(1.0_f32, Color32::from_white_alpha(90));
                    let w3 = screen_crop.width() / 3.0;
                    let h3 = screen_crop.height() / 3.0;
                    for i in 1..=2 {
                        let x = screen_crop.left() + w3 * i as f32;
                        painter.line_segment(
                            [
                                Pos2::new(x, screen_crop.top()),
                                Pos2::new(x, screen_crop.bottom()),
                            ],
                            grid_stroke,
                        );
                        let y = screen_crop.top() + h3 * i as f32;
                        painter.line_segment(
                            [
                                Pos2::new(screen_crop.left(), y),
                                Pos2::new(screen_crop.right(), y),
                            ],
                            grid_stroke,
                        );
                    }

                    // 6c. Border around crop rect
                    painter.rect_stroke(screen_crop, 0.0, Stroke::new(1.5_f32, Color32::WHITE));

                    // 6d. 4 Corner L-bracket handles (Photocraft style)
                    let handle_len = 16.0_f32;
                    let handle_stroke = Stroke::new(3.5_f32, Color32::WHITE);
                    // Top-left
                    painter.line_segment(
                        [
                            screen_crop.left_top(),
                            screen_crop.left_top() + Vec2::new(handle_len, 0.0),
                        ],
                        handle_stroke,
                    );
                    painter.line_segment(
                        [
                            screen_crop.left_top(),
                            screen_crop.left_top() + Vec2::new(0.0, handle_len),
                        ],
                        handle_stroke,
                    );
                    // Top-right
                    painter.line_segment(
                        [
                            screen_crop.right_top(),
                            screen_crop.right_top() - Vec2::new(handle_len, 0.0),
                        ],
                        handle_stroke,
                    );
                    painter.line_segment(
                        [
                            screen_crop.right_top(),
                            screen_crop.right_top() + Vec2::new(0.0, handle_len),
                        ],
                        handle_stroke,
                    );
                    // Bottom-left
                    painter.line_segment(
                        [
                            screen_crop.left_bottom(),
                            screen_crop.left_bottom() + Vec2::new(handle_len, 0.0),
                        ],
                        handle_stroke,
                    );
                    painter.line_segment(
                        [
                            screen_crop.left_bottom(),
                            screen_crop.left_bottom() - Vec2::new(0.0, handle_len),
                        ],
                        handle_stroke,
                    );
                    // Bottom-right
                    painter.line_segment(
                        [
                            screen_crop.right_bottom(),
                            screen_crop.right_bottom() - Vec2::new(handle_len, 0.0),
                        ],
                        handle_stroke,
                    );
                    painter.line_segment(
                        [
                            screen_crop.right_bottom(),
                            screen_crop.right_bottom() - Vec2::new(0.0, handle_len),
                        ],
                        handle_stroke,
                    );

                    // 6e. 4 Edge bar handles
                    let bar_half = 9.0_f32;
                    let bar_stroke = Stroke::new(3.0_f32, Color32::WHITE);
                    let tc = Pos2::new(screen_crop.center().x, screen_crop.top());
                    painter.line_segment(
                        [tc - Vec2::new(bar_half, 0.0), tc + Vec2::new(bar_half, 0.0)],
                        bar_stroke,
                    );
                    let bc = Pos2::new(screen_crop.center().x, screen_crop.bottom());
                    painter.line_segment(
                        [bc - Vec2::new(bar_half, 0.0), bc + Vec2::new(bar_half, 0.0)],
                        bar_stroke,
                    );
                    let ml = Pos2::new(screen_crop.left(), screen_crop.center().y);
                    painter.line_segment(
                        [ml - Vec2::new(0.0, bar_half), ml + Vec2::new(0.0, bar_half)],
                        bar_stroke,
                    );
                    let mr = Pos2::new(screen_crop.right(), screen_crop.center().y);
                    painter.line_segment(
                        [mr - Vec2::new(0.0, bar_half), mr + Vec2::new(0.0, bar_half)],
                        bar_stroke,
                    );

                    // 6f. Dimension readout
                    let dpi = self.template.dpi.max(72) as f32;
                    let mm_w = crop_scene.width() / dpi * 25.4;
                    let mm_h = crop_scene.height() / dpi * 25.4;
                    let readout = format!(
                        "{:.0} × {:.0} px ({:.1} × {:.1} mm)  [↵ Commit | Esc Cancel]",
                        crop_scene.width(),
                        crop_scene.height(),
                        mm_w,
                        mm_h
                    );
                    let badge_pos = Pos2::new(screen_crop.center().x, screen_crop.bottom() + 18.0);
                    painter.rect_filled(
                        Rect::from_center_size(
                            badge_pos,
                            Vec2::new(readout.len() as f32 * 6.5 + 16.0, 20.0),
                        ),
                        4.0,
                        Color32::from_black_alpha(200),
                    );
                    painter.text(
                        badge_pos,
                        Align2::CENTER_CENTER,
                        readout,
                        FontId::proportional(11.0),
                        Color32::from_rgb(226, 232, 240),
                    );
                }
            } else {
                painter.text(
                    canvas_screen.center(),
                    Align2::CENTER_CENTER,
                    "⯐ Click and drag on canvas to select crop portion",
                    FontId::proportional(14.0),
                    Color32::from_white_alpha(175),
                );
            }
        }
    }

    /// Draw custom floating designed tool cursor over the canvas viewport.
    fn draw_custom_cursor(&self, painter: &egui::Painter, pos: Pos2, transform: CanvasTransform) {
        match self.state.active_tool {
            EditorTool::Zoom => {
                let badge_pos = pos + Vec2::new(14.0, 14.0);
                painter.rect_filled(
                    Rect::from_min_size(badge_pos, Vec2::new(42.0, 20.0)),
                    4.0,
                    Color32::from_black_alpha(200),
                );
                painter.text(
                    badge_pos + Vec2::new(21.0, 10.0),
                    Align2::CENTER_CENTER,
                    "🔍+",
                    FontId::proportional(12.0),
                    Color32::WHITE,
                );
            }
            EditorTool::Shape => {
                let badge_pos = pos + Vec2::new(14.0, 14.0);
                let shape_icon = self.state.active_shape.icon();
                painter.rect_filled(
                    Rect::from_min_size(badge_pos, Vec2::new(54.0, 20.0)),
                    4.0,
                    Color32::from_black_alpha(200),
                );
                painter.text(
                    badge_pos + Vec2::new(27.0, 10.0),
                    Align2::CENTER_CENTER,
                    format!("{shape_icon} Shape"),
                    FontId::proportional(11.0),
                    Color32::from_rgb(56, 189, 248),
                );
            }
            EditorTool::PaintBucket => {
                let badge_pos = pos + Vec2::new(14.0, 14.0);
                painter.rect_filled(
                    Rect::from_min_size(badge_pos, Vec2::new(48.0, 20.0)),
                    4.0,
                    Color32::from_black_alpha(200),
                );
                painter.text(
                    badge_pos + Vec2::new(16.0, 10.0),
                    Align2::CENTER_CENTER,
                    "🪣",
                    FontId::proportional(13.0),
                    Color32::WHITE,
                );
                // Mini color square
                let color_rect =
                    Rect::from_min_size(badge_pos + Vec2::new(28.0, 4.0), Vec2::splat(12.0));
                painter.rect_filled(color_rect, 2.0, self.state.foreground_color);
                painter.rect_stroke(color_rect, 2.0, Stroke::new(1.0_f32, Color32::WHITE));
            }
            EditorTool::Brush => {
                // Circular brush radius ring
                let radius = (self.state.brush_size * transform.scale / 2.0).max(3.0);
                painter.circle_stroke(
                    pos,
                    radius,
                    Stroke::new(
                        1.2_f32,
                        Color32::from_rgba_premultiplied(255, 255, 255, 200),
                    ),
                );
                painter.circle_filled(pos, 1.5, Color32::WHITE);
            }
            EditorTool::Eraser => {
                let radius = (self.state.brush_size / 2.0).max(4.0) * transform.scale;
                painter.circle_stroke(
                    pos,
                    radius,
                    Stroke::new(
                        1.5_f32,
                        Color32::from_rgba_premultiplied(255, 255, 255, 230),
                    ),
                );
                painter.circle_stroke(
                    pos,
                    radius + 0.5,
                    Stroke::new(0.75_f32, Color32::from_rgba_premultiplied(0, 0, 0, 160)),
                );
                painter.text(
                    pos + Vec2::new(radius + 6.0, 0.0),
                    Align2::LEFT_CENTER,
                    "⌫",
                    FontId::proportional(11.0),
                    Color32::from_rgba_premultiplied(255, 255, 255, 200),
                );
            }
            EditorTool::Eyedropper => {
                let badge_pos = pos + Vec2::new(14.0, 14.0);
                painter.rect_filled(
                    Rect::from_min_size(badge_pos, Vec2::new(42.0, 20.0)),
                    4.0,
                    Color32::from_black_alpha(200),
                );
                painter.text(
                    badge_pos + Vec2::new(21.0, 10.0),
                    Align2::CENTER_CENTER,
                    "💉 Pick",
                    FontId::proportional(10.0),
                    Color32::WHITE,
                );
            }
            EditorTool::Crop => {
                let badge_pos = pos + Vec2::new(14.0, 14.0);
                painter.rect_filled(
                    Rect::from_min_size(badge_pos, Vec2::new(46.0, 20.0)),
                    4.0,
                    Color32::from_black_alpha(200),
                );
                painter.text(
                    badge_pos + Vec2::new(23.0, 10.0),
                    Align2::CENTER_CENTER,
                    "⯐ Crop",
                    FontId::proportional(10.0),
                    Color32::WHITE,
                );
            }
            EditorTool::Marquee => {
                let badge_pos = pos + Vec2::new(14.0, 14.0);
                painter.rect_filled(
                    Rect::from_min_size(badge_pos, Vec2::new(48.0, 20.0)),
                    4.0,
                    Color32::from_black_alpha(200),
                );
                painter.text(
                    badge_pos + Vec2::new(24.0, 10.0),
                    Align2::CENTER_CENTER,
                    "⬚ Marq",
                    FontId::proportional(10.0),
                    Color32::WHITE,
                );
            }
            _ => {}
        }
    }

    /// Draw the TBox (Transform Box) with 8 resize handles and rotation grip.
    fn draw_tbox(
        &self,
        painter: &egui::Painter,
        element: &CanvasElement,
        transform: CanvasTransform,
    ) {
        if !self.state.show_transform_controls {
            return;
        }

        let elem_rect = Rect::from_min_size(
            transform.scene_to_screen(Pos2::new(element.x as f32, element.y as f32)),
            Vec2::new(
                element.width as f32 * transform.scale,
                element.height as f32 * transform.scale,
            ),
        );

        let primary_blue = Color32::from_rgb(37, 99, 235);
        let handle_fill = Color32::WHITE;
        let handle_stroke = Stroke::new(1.5_f32, primary_blue);

        // Bounding box outline
        painter.rect_stroke(
            elem_rect.expand(1.0),
            0.0,
            Stroke::new(1.5_f32, primary_blue),
        );

        // Dimension tag at top
        let dim_text = format!("{:.0} × {:.0} px", element.width, element.height);
        let tag_pos = elem_rect.left_top() - Vec2::new(0.0, 16.0);
        painter.rect_filled(
            Rect::from_min_size(tag_pos - Vec2::new(4.0, 2.0), Vec2::new(80.0, 14.0)),
            2.0,
            Color32::from_black_alpha(180),
        );
        painter.text(
            tag_pos,
            Align2::LEFT_TOP,
            dim_text,
            FontId::proportional(10.0),
            Color32::WHITE,
        );

        // Handles: corner handles always, mid handles only if space allows to prevent overlap
        let show_mid_w = elem_rect.width() >= HANDLE_SIZE * 2.5;
        let show_mid_h = elem_rect.height() >= HANDLE_SIZE * 2.5;

        let mut handles = vec![
            elem_rect.left_top(),
            elem_rect.right_top(),
            elem_rect.left_bottom(),
            elem_rect.right_bottom(),
        ];
        if show_mid_w {
            handles.push(Pos2::new(elem_rect.center().x, elem_rect.top()));
            handles.push(Pos2::new(elem_rect.center().x, elem_rect.bottom()));
        }
        if show_mid_h {
            handles.push(Pos2::new(elem_rect.left(), elem_rect.center().y));
            handles.push(Pos2::new(elem_rect.right(), elem_rect.center().y));
        }

        for pos in handles {
            let handle_rect = Rect::from_center_size(pos, Vec2::splat(HANDLE_SIZE));
            painter.rect_filled(handle_rect, 1.0, handle_fill);
            painter.rect_stroke(handle_rect, 1.0, handle_stroke);
        }

        // Rotation grip
        let top_center = Pos2::new(elem_rect.center().x, elem_rect.top());
        let rotate_pos = top_center - Vec2::new(0.0, 20.0);
        painter.line_segment([top_center, rotate_pos], handle_stroke);
        painter.circle_filled(rotate_pos, 4.0, handle_fill);
        painter.circle_stroke(rotate_pos, 4.0, handle_stroke);
    }

    /// Detect which TBox handle (if any) was clicked or hovered.
    fn hit_test_handle(
        &self,
        element: &CanvasElement,
        transform: CanvasTransform,
        pointer: Pos2,
    ) -> Option<TransformHandle> {
        let elem_rect = Rect::from_min_size(
            transform.scene_to_screen(Pos2::new(element.x as f32, element.y as f32)),
            Vec2::new(
                element.width as f32 * transform.scale,
                element.height as f32 * transform.scale,
            ),
        );

        let tolerance = HANDLE_SIZE + 4.0;
        let is_near = |center: Pos2| (center - pointer).length() <= tolerance;

        // Check corners first
        if is_near(elem_rect.left_top()) {
            return Some(TransformHandle::TopLeft);
        }
        if is_near(elem_rect.right_top()) {
            return Some(TransformHandle::TopRight);
        }
        if is_near(elem_rect.left_bottom()) {
            return Some(TransformHandle::BottomLeft);
        }
        if is_near(elem_rect.right_bottom()) {
            return Some(TransformHandle::BottomRight);
        }

        let show_mid_w = elem_rect.width() >= HANDLE_SIZE * 2.5;
        let show_mid_h = elem_rect.height() >= HANDLE_SIZE * 2.5;
        if show_mid_w && is_near(Pos2::new(elem_rect.center().x, elem_rect.top())) {
            return Some(TransformHandle::TopCenter);
        }
        if show_mid_h && is_near(Pos2::new(elem_rect.left(), elem_rect.center().y)) {
            return Some(TransformHandle::MiddleLeft);
        }
        if show_mid_h && is_near(Pos2::new(elem_rect.right(), elem_rect.center().y)) {
            return Some(TransformHandle::MiddleRight);
        }
        if show_mid_w && is_near(Pos2::new(elem_rect.center().x, elem_rect.bottom())) {
            return Some(TransformHandle::BottomCenter);
        }

        let rotate_pos = Pos2::new(elem_rect.center().x, elem_rect.top()) - Vec2::new(0.0, 20.0);
        if is_near(rotate_pos) {
            return Some(TransformHandle::Rotate);
        }

        if elem_rect.contains(pointer) {
            return Some(TransformHandle::Body);
        }

        None
    }

    fn draw_guides(&self, painter: &egui::Painter, canvas: Rect, transform: CanvasTransform) {
        if self.state.show_grid {
            let spacing = 20.0 * transform.scale;
            let mut x = canvas.left() + spacing;
            while x < canvas.right() {
                painter.line_segment(
                    [Pos2::new(x, canvas.top()), Pos2::new(x, canvas.bottom())],
                    Stroke::new(0.5_f32, Color32::from_gray(220)),
                );
                x += spacing;
            }
            let mut y = canvas.top() + spacing;
            while y < canvas.bottom() {
                painter.line_segment(
                    [Pos2::new(canvas.left(), y), Pos2::new(canvas.right(), y)],
                    Stroke::new(0.5_f32, Color32::from_gray(220)),
                );
                y += spacing;
            }
        }
        if self.state.show_safe_area {
            let margin = (self.template.safe_area_margin_mm / 25.4 * f64::from(self.template.dpi))
                as f32
                * transform.scale;
            painter.rect_stroke(
                canvas.shrink(margin),
                0.0,
                Stroke::new(1.0_f32, Color32::from_rgb(80, 160, 220)),
            );
        }
    }

    fn draw_element(
        &self,
        painter: &egui::Painter,
        element: &CanvasElement,
        transform: CanvasTransform,
    ) {
        let rect = Rect::from_min_size(
            transform.scene_to_screen(Pos2::new(element.x as f32, element.y as f32)),
            Vec2::new(
                element.width as f32 * transform.scale,
                element.height as f32 * transform.scale,
            ),
        );
        let fill = parse_color(
            &element.style.background_color,
            Color32::from_white_alpha(20),
        );
        let stroke_color = parse_color(&element.style.border_color, Color32::from_gray(100));
        let stroke = Stroke::new(
            (element.style.border_width.max(1) as f32 * transform.scale).max(1.0),
            stroke_color,
        );

        match element.r#type.as_str() {
            "line" => {
                painter.line_segment(
                    [rect.left_top(), rect.right_bottom()],
                    Stroke::new(2.0_f32, stroke_color),
                );
            }
            "brush" => {
                let stroke_width =
                    (element.style.border_width.max(1) as f32 * transform.scale).max(1.0);
                let brush_color = parse_color(&element.style.font_color, stroke_color);
                let brush_stroke = Stroke::new(stroke_width, brush_color);
                let radius = stroke_width / 2.0;

                if let Some(content) = element.static_content.as_deref() {
                    let paths = parse_brush_paths(content);
                    for pts in paths {
                        for window in pts.windows(2) {
                            let p1 =
                                transform.scene_to_screen(Pos2::new(window[0][0], window[0][1]));
                            let p2 =
                                transform.scene_to_screen(Pos2::new(window[1][0], window[1][1]));
                            painter.line_segment([p1, p2], brush_stroke);
                            painter.circle_filled(p1, radius, brush_color);
                            painter.circle_filled(p2, radius, brush_color);
                        }
                        if pts.len() == 1 {
                            let p0 = transform.scene_to_screen(Pos2::new(pts[0][0], pts[0][1]));
                            painter.circle_filled(p0, radius, brush_color);
                        }
                    }
                }
            }
            "gradient" => {
                let steps = 24;
                let c1 = fill;
                let c2 = stroke_color;
                let step_h = rect.height() / steps as f32;
                for i in 0..steps {
                    let t = i as f32 / (steps - 1) as f32;
                    let r = (c1.r() as f32 * (1.0 - t) + c2.r() as f32 * t) as u8;
                    let g = (c1.g() as f32 * (1.0 - t) + c2.g() as f32 * t) as u8;
                    let b = (c1.b() as f32 * (1.0 - t) + c2.b() as f32 * t) as u8;
                    let a = (c1.a() as f32 * (1.0 - t) + c2.a() as f32 * t) as u8;
                    let strip_rect = Rect::from_min_size(
                        Pos2::new(rect.left(), rect.top() + i as f32 * step_h),
                        Vec2::new(rect.width(), step_h + 1.0),
                    );
                    painter.rect_filled(
                        strip_rect,
                        0.0,
                        Color32::from_rgba_premultiplied(r, g, b, a),
                    );
                }
                painter.rect_stroke(rect, 0.0, stroke);
            }
            "ellipse" => {
                let rx = rect.width() / 2.0;
                let ry = rect.height() / 2.0;
                let center = rect.center();
                let pts: Vec<Pos2> = (0..32)
                    .map(|i| {
                        let a = i as f32 * std::f32::consts::TAU / 32.0;
                        Pos2::new(center.x + rx * a.cos(), center.y + ry * a.sin())
                    })
                    .collect();
                painter.add(egui::Shape::convex_polygon(pts, fill, stroke));
            }
            "photo" => {
                let bg_color = Color32::from_rgb(226, 232, 240);
                painter.rect_filled(rect, 4.0, bg_color);
                painter.rect_stroke(rect, 4.0, stroke);
                let soft_stroke = Stroke::new(1.0_f32, Color32::from_rgb(203, 213, 225));
                painter.line_segment([rect.left_top(), rect.right_bottom()], soft_stroke);
                painter.line_segment([rect.right_top(), rect.left_bottom()], soft_stroke);

                let center = rect.center();
                let icon_size = (28.0 * transform.scale).clamp(14.0, 36.0);
                painter.text(
                    center - Vec2::new(0.0, icon_size * 0.35),
                    Align2::CENTER_CENTER,
                    "📷",
                    FontId::proportional(icon_size),
                    Color32::from_rgb(100, 116, 139),
                );

                let key_hint = element
                    .binding
                    .as_deref()
                    .or_else(|| {
                        self.photo_key_column
                            .as_ref()
                            .and_then(|k| (**k).as_deref())
                    })
                    .unwrap_or("PIN");
                let label_text = format!("Photo [{key_hint}]");
                painter.text(
                    center + Vec2::new(0.0, icon_size * 0.5),
                    Align2::CENTER_CENTER,
                    label_text,
                    FontId::proportional((11.0 * transform.scale).clamp(8.0, 14.0)),
                    Color32::from_rgb(71, 85, 105),
                );
            }
            "round_rect" => {
                painter.rect_filled(rect, element.style.border_radius.max(8) as f32, fill);
                painter.rect_stroke(rect, element.style.border_radius.max(8) as f32, stroke);
            }
            _ => {
                painter.rect_filled(rect, 0.0, fill);
                painter.rect_stroke(rect, 0.0, stroke);
            }
        }

        let label = element
            .static_content
            .as_deref()
            .or(element.binding.as_deref())
            .unwrap_or(&element.name);

        if element.r#type == "text" || element.r#type == "dynamic_text" {
            if self.state.editing_text_id.as_deref() != Some(&element.id) {
                let padding = (4.0 * transform.scale).clamp(2.0, 6.0);
                let avail_w = (rect.width() - padding * 2.0).max(4.0);
                let avail_h = (rect.height() - padding * 2.0).max(4.0);

                let base_size = (element.style.font_size as f32 * transform.scale).max(6.0);
                let font_size = base_size.min(avail_h);
                let font_id = FontId::proportional(font_size);
                let font_color = parse_color(&element.style.font_color, Color32::DARK_GRAY);

                let text_painter = painter.with_clip_rect(rect);
                let galley = text_painter.layout(label.to_string(), font_id, font_color, avail_w);
                text_painter.galley(
                    rect.left_top() + Vec2::new(padding, padding),
                    galley,
                    font_color,
                );
            }
        } else if element.r#type != "line"
            && element.r#type != "brush"
            && element.r#type != "gradient"
            && element.r#type != "photo"
        {
            if let Some(content) = element.static_content.as_deref() {
                let padding = 4.0;
                let avail_w = (rect.width() - padding * 2.0).max(4.0);
                let avail_h = (rect.height() - padding * 2.0).max(4.0);
                let font_size = (element.style.font_size as f32 * transform.scale)
                    .min(avail_h)
                    .max(6.0);
                let font_id = FontId::proportional(font_size);
                let font_color = parse_color(&element.style.font_color, Color32::DARK_GRAY);
                let text_painter = painter.with_clip_rect(rect);
                let galley = text_painter.layout(content.to_string(), font_id, font_color, avail_w);
                text_painter.galley(
                    rect.left_top() + Vec2::new(padding, padding),
                    galley,
                    font_color,
                );
            }
        }
    }

    fn draw_rulers(
        &mut self,
        painter: &egui::Painter,
        view_rect: Rect,
        canvas_area: Rect,
        transform: CanvasTransform,
        pointer_pos: Option<Pos2>,
    ) {
        let bg_color = Color32::from_rgb(30, 30, 34);
        let border_stroke = Stroke::new(1.0_f32, Color32::from_rgb(58, 58, 62));
        let tick_stroke = Stroke::new(1.0_f32, Color32::from_gray(120));
        let sub_tick_stroke = Stroke::new(0.8_f32, Color32::from_gray(80));
        let text_color = Color32::from_gray(160);
        let hairline_stroke = Stroke::new(1.0_f32, Color32::from_rgb(239, 68, 68));

        let corner_rect = Rect::from_min_size(view_rect.min, Vec2::splat(RULER_THICKNESS));
        painter.rect_filled(corner_rect, 0.0, bg_color);
        painter.line_segment(
            [corner_rect.right_top(), corner_rect.right_bottom()],
            border_stroke,
        );
        painter.line_segment(
            [corner_rect.left_bottom(), corner_rect.right_bottom()],
            border_stroke,
        );
        painter.text(
            corner_rect.center(),
            Align2::CENTER_CENTER,
            &self.state.ruler_unit,
            FontId::proportional(9.0),
            text_color,
        );

        let dpi = self.template.dpi.max(72) as f32;
        let is_mm = self.state.ruler_unit == "mm";
        let base_step = if is_mm { 10.0 * dpi / 25.4 } else { 100.0 };
        let step = if transform.scale > 2.5 {
            base_step / 2.0
        } else if transform.scale < 0.6 {
            base_step * 2.0
        } else {
            base_step
        };

        // Horizontal Ruler
        let h_ruler_rect = Rect::from_min_max(
            Pos2::new(view_rect.min.x + RULER_THICKNESS, view_rect.min.y),
            Pos2::new(view_rect.max.x, view_rect.min.y + RULER_THICKNESS),
        );
        painter.rect_filled(h_ruler_rect, 0.0, bg_color);
        painter.line_segment(
            [h_ruler_rect.left_bottom(), h_ruler_rect.right_bottom()],
            border_stroke,
        );

        let scene_left = transform.screen_to_scene(h_ruler_rect.left_top()).x;
        let scene_right = transform.screen_to_scene(h_ruler_rect.right_top()).x;
        let mut val = (scene_left / step).floor() * step;
        while val <= scene_right + step {
            let screen_x = transform.scene_to_screen(Pos2::new(val, 0.0)).x;
            if screen_x >= h_ruler_rect.left() && screen_x <= h_ruler_rect.right() {
                painter.line_segment(
                    [
                        Pos2::new(screen_x, h_ruler_rect.bottom() - 7.0),
                        Pos2::new(screen_x, h_ruler_rect.bottom()),
                    ],
                    tick_stroke,
                );
                let label_val = if is_mm {
                    (val / dpi * 25.4).round() as i32
                } else {
                    val.round() as i32
                };
                painter.text(
                    Pos2::new(screen_x + 3.0, h_ruler_rect.top() + 3.0),
                    Align2::LEFT_TOP,
                    label_val.to_string(),
                    FontId::proportional(8.0),
                    text_color,
                );

                for i in 1..5 {
                    let sub_val = val + (step * i as f32 / 5.0);
                    let sub_x = transform.scene_to_screen(Pos2::new(sub_val, 0.0)).x;
                    if sub_x >= h_ruler_rect.left() && sub_x <= h_ruler_rect.right() {
                        let tick_h = if i == 2 || i == 3 { 5.0 } else { 3.0 };
                        painter.line_segment(
                            [
                                Pos2::new(sub_x, h_ruler_rect.bottom() - tick_h),
                                Pos2::new(sub_x, h_ruler_rect.bottom()),
                            ],
                            sub_tick_stroke,
                        );
                    }
                }
            }
            val += step;
        }

        // Vertical Ruler
        let v_ruler_rect = Rect::from_min_max(
            Pos2::new(view_rect.min.x, view_rect.min.y + RULER_THICKNESS),
            Pos2::new(view_rect.min.x + RULER_THICKNESS, canvas_area.bottom()),
        );
        painter.rect_filled(v_ruler_rect, 0.0, bg_color);
        painter.line_segment(
            [v_ruler_rect.right_top(), v_ruler_rect.right_bottom()],
            border_stroke,
        );

        let scene_top = transform.screen_to_scene(v_ruler_rect.left_top()).y;
        let scene_bottom = transform.screen_to_scene(v_ruler_rect.left_bottom()).y;
        let mut y_val = (scene_top / step).floor() * step;
        while y_val <= scene_bottom + step {
            let screen_y = transform.scene_to_screen(Pos2::new(0.0, y_val)).y;
            if screen_y >= v_ruler_rect.top() && screen_y <= v_ruler_rect.bottom() {
                painter.line_segment(
                    [
                        Pos2::new(v_ruler_rect.right() - 7.0, screen_y),
                        Pos2::new(v_ruler_rect.right(), screen_y),
                    ],
                    tick_stroke,
                );
                let label_val = if is_mm {
                    (y_val / dpi * 25.4).round() as i32
                } else {
                    y_val.round() as i32
                };
                painter.text(
                    Pos2::new(v_ruler_rect.left() + 3.0, screen_y + 3.0),
                    Align2::LEFT_TOP,
                    label_val.to_string(),
                    FontId::proportional(8.0),
                    text_color,
                );

                for i in 1..5 {
                    let sub_val = y_val + (step * i as f32 / 5.0);
                    let sub_y = transform.scene_to_screen(Pos2::new(0.0, sub_val)).y;
                    if sub_y >= v_ruler_rect.top() && sub_y <= v_ruler_rect.bottom() {
                        let tick_w = if i == 2 || i == 3 { 5.0 } else { 3.0 };
                        painter.line_segment(
                            [
                                Pos2::new(v_ruler_rect.right() - tick_w, sub_y),
                                Pos2::new(v_ruler_rect.right(), sub_y),
                            ],
                            sub_tick_stroke,
                        );
                    }
                }
            }
            y_val += step;
        }

        // Crosshair tracker lines
        if self.state.show_crosshairs {
            if let Some(pos) = pointer_pos {
                if pos.x >= h_ruler_rect.left() && pos.x <= h_ruler_rect.right() {
                    painter.line_segment(
                        [
                            Pos2::new(pos.x, h_ruler_rect.top()),
                            Pos2::new(pos.x, h_ruler_rect.bottom()),
                        ],
                        hairline_stroke,
                    );
                }
                if pos.y >= v_ruler_rect.top() && pos.y <= v_ruler_rect.bottom() {
                    painter.line_segment(
                        [
                            Pos2::new(v_ruler_rect.left(), pos.y),
                            Pos2::new(v_ruler_rect.right(), pos.y),
                        ],
                        hairline_stroke,
                    );
                }
            }
        }
    }

    /// Bottom HUD: Zoom, Coordinates, View Fit.
    fn draw_hud(&mut self, painter: &egui::Painter, view_rect: Rect) {
        let hud_rect = Rect::from_min_max(
            Pos2::new(view_rect.min.x, view_rect.max.y - 32.0),
            view_rect.max,
        );
        painter.rect_filled(hud_rect, 0.0, Color32::from_rgb(24, 24, 27));
        painter.line_segment(
            [hud_rect.left_top(), hud_rect.right_top()],
            Stroke::new(1.0_f32, Color32::from_rgb(45, 45, 50)),
        );

        let zoom_pct = (self.state.zoom * 100.0).round() as i32;
        let hud_text = if let Some(pos) = self.state.cursor_scene_pos {
            format!(
                "Zoom: {zoom_pct}%  |  X: {:.1} px  Y: {:.1} px  |  Tool: {}",
                pos.x,
                pos.y,
                self.state.active_tool.name()
            )
        } else {
            format!(
                "Zoom: {zoom_pct}%  |  Tool: {}",
                self.state.active_tool.name()
            )
        };

        painter.text(
            hud_rect.left_center() + Vec2::new(14.0, 0.0),
            Align2::LEFT_CENTER,
            hud_text,
            FontId::proportional(11.0),
            Color32::from_gray(180),
        );
    }

    /// Interactive canvas input handling with TBox bidirectional cursors, live tools, and zoom.
    fn handle_canvas_input(
        &mut self,
        response: Response,
        _view: Rect,
        canvas_area: Rect,
        transform: CanvasTransform,
        over_scrollbar: bool,
    ) {
        let pointer = response
            .interact_pointer_pos()
            .or_else(|| response.hover_pos());
        if let Some(pos) = pointer {
            self.state.cursor_scene_pos = Some(transform.screen_to_scene(pos));
        }

        let is_left_clicked = response.clicked()
            || response
                .ctx
                .input(|i| i.pointer.button_clicked(PointerButton::Primary));
        let is_right_clicked = response.secondary_clicked()
            || response
                .ctx
                .input(|i| i.pointer.button_clicked(PointerButton::Secondary));

        // ---------------------------------------------------------
        // A. Global Keyboard Shortcuts (Photocraft standard)
        // Disabled while typing in any text field or inline editor
        // ---------------------------------------------------------
        let is_typing = response.ctx.wants_keyboard_input() || self.state.editing_text_id.is_some();
        if !is_typing {
            response.ctx.input(|i| {
                // 1. Tool Selection Hotkeys
                if i.key_pressed(egui::Key::V) {
                    self.state.active_tool = EditorTool::Move;
                } else if i.key_pressed(egui::Key::M) {
                    self.state.active_tool = EditorTool::Marquee;
                } else if i.key_pressed(egui::Key::W) {
                    self.state.active_tool = EditorTool::ObjectSelect;
                } else if i.key_pressed(egui::Key::C) {
                    self.state.active_tool = EditorTool::Crop;
                    self.init_crop_if_needed();
                } else if i.key_pressed(egui::Key::I) {
                    self.state.active_tool = EditorTool::Eyedropper;
                } else if i.key_pressed(egui::Key::B) {
                    self.state.active_tool = EditorTool::Brush;
                } else if i.key_pressed(egui::Key::E) {
                    self.state.active_tool = EditorTool::Eraser;
                } else if i.key_pressed(egui::Key::G) {
                    self.state.active_tool = EditorTool::Gradient;
                } else if i.key_pressed(egui::Key::K) {
                    self.state.active_tool = EditorTool::PaintBucket;
                } else if i.key_pressed(egui::Key::T) {
                    self.state.active_tool = EditorTool::Text;
                } else if i.key_pressed(egui::Key::U) {
                    self.state.active_tool = EditorTool::Shape;
                } else if i.key_pressed(egui::Key::H) {
                    self.state.active_tool = EditorTool::Hand;
                } else if i.key_pressed(egui::Key::Z) {
                    self.state.active_tool = EditorTool::Zoom;
                }

                // 2. Undo & Redo (Ctrl+Z, Ctrl+Shift+Z, Ctrl+Y, Cmd variants)
                let is_ctrl = i.modifiers.ctrl || i.modifiers.command;
                if is_ctrl && !i.modifiers.shift && i.key_pressed(egui::Key::Z) {
                    self.state.history.undo(self.template);
                } else if is_ctrl
                    && (i.key_pressed(egui::Key::Y)
                        || (i.modifiers.shift && i.key_pressed(egui::Key::Z)))
                {
                    self.state.history.redo(self.template);
                }

                // 3. Crop Commit / Cancel keys
                if self.state.active_tool == EditorTool::Crop {
                    if i.key_pressed(egui::Key::Enter) {
                        self.commit_crop();
                    } else if i.key_pressed(egui::Key::Escape) {
                        self.cancel_crop();
                    } else if (i.key_pressed(egui::Key::Delete)
                        || i.key_pressed(egui::Key::Backspace))
                        && self.state.selected_id.is_none()
                    {
                        self.state.crop_rect = None;
                    }
                }

                // 4. Delete / Backspace to remove selected element
                if i.key_pressed(egui::Key::Delete) || i.key_pressed(egui::Key::Backspace) {
                    if let Some(id) = self.state.selected_id.clone() {
                        self.state
                            .execute(self.template, EditorCommand::Delete { id });
                        self.state.selected_id = None;
                    }
                }

                // 5. Arrow Keys Nudge (1px normal, 10px with Shift)
                if let Some(id) = &self.state.selected_id {
                    let step = if i.modifiers.shift { 10.0 } else { 1.0 };
                    let mut delta = Vec2::ZERO;
                    if i.key_pressed(egui::Key::ArrowLeft) {
                        delta.x -= step;
                    }
                    if i.key_pressed(egui::Key::ArrowRight) {
                        delta.x += step;
                    }
                    if i.key_pressed(egui::Key::ArrowUp) {
                        delta.y -= step;
                    }
                    if i.key_pressed(egui::Key::ArrowDown) {
                        delta.y += step;
                    }
                    if delta != Vec2::ZERO {
                        self.state.execute(
                            self.template,
                            EditorCommand::Move {
                                id: id.clone(),
                                delta,
                            },
                        );
                    }
                }
            });
        }

        // ---------------------------------------------------------
        // B. Temporary Pan Mode (Photocraft: Spacebar held)
        // ---------------------------------------------------------
        let space_held = response.ctx.input(|i| i.key_down(egui::Key::Space));
        if space_held {
            if response.dragged() {
                response.ctx.set_cursor_icon(CursorIcon::Grabbing);
                self.state.pan += response.drag_delta();
            } else {
                response.ctx.set_cursor_icon(CursorIcon::Grab);
            }
            return;
        }

        // Middle Mouse Button Pan
        let middle_down = response.hovered()
            && response
                .ctx
                .input(|input| input.pointer.button_down(PointerButton::Middle));
        if middle_down {
            self.state.pan += response.ctx.input(|input| input.pointer.delta());
        }

        // Mouse wheel: Ctrl+Wheel to Zoom, normal wheel to Pan (Y), Shift+Wheel to Pan (X)
        if response.hovered() {
            let scroll_y = response.ctx.input(|input| input.smooth_scroll_delta.y);
            let scroll_x = response.ctx.input(|input| input.smooth_scroll_delta.x);
            if response.ctx.input(|input| input.modifiers.ctrl) {
                if scroll_y != 0.0 {
                    self.state.zoom =
                        (self.state.zoom * (1.0 + scroll_y * 0.001)).clamp(MIN_ZOOM, MAX_ZOOM);
                }
            } else if scroll_y != 0.0 || scroll_x != 0.0 {
                if response.ctx.input(|input| input.modifiers.shift) {
                    self.state.pan.x += scroll_y;
                } else {
                    self.state.pan.y += scroll_y;
                    self.state.pan.x += scroll_x;
                }
            }
        }

        // Double-click to edit text element directly
        let is_double_clicked = response.double_clicked()
            || response
                .ctx
                .input(|i| i.pointer.button_double_clicked(PointerButton::Primary));
        if is_double_clicked && !over_scrollbar {
            if let Some(pos) = pointer {
                let scene_pos = transform.screen_to_scene(pos);
                if let Some(hit_id) = self.hit_test(scene_pos) {
                    if let Some(elem) = self.template.get_element_by_id(&hit_id) {
                        if elem.r#type == "text" || elem.r#type == "dynamic_text" {
                            self.start_editing_text(hit_id);
                            return;
                        }
                    }
                }
            }
        }

        // If hovering or interacting with scrollbar, skip canvas tool processing
        if over_scrollbar {
            return;
        }

        // ---------------------------------------------------------
        // C. Per-Tool Dispatch & Execution
        // ---------------------------------------------------------
        match self.state.active_tool {
            EditorTool::Hand => {
                if response.dragged() {
                    response.ctx.set_cursor_icon(CursorIcon::Grabbing);
                    self.state.pan += response.drag_delta();
                } else {
                    response.ctx.set_cursor_icon(CursorIcon::Grab);
                }
            }

            EditorTool::Zoom => {
                let alt_down = response.ctx.input(|i| i.modifiers.alt);
                if alt_down {
                    response.ctx.set_cursor_icon(CursorIcon::ZoomOut);
                } else {
                    response.ctx.set_cursor_icon(CursorIcon::ZoomIn);
                }

                if is_right_clicked || (is_left_clicked && alt_down) {
                    self.state.zoom = (self.state.zoom / 1.3).max(MIN_ZOOM);
                } else if is_left_clicked {
                    self.state.zoom = (self.state.zoom * 1.3).min(MAX_ZOOM);
                }
            }

            EditorTool::Crop => {
                let crop_opt = self.state.crop_rect;
                let is_full_canvas = if let Some(crop_scene) = crop_opt {
                    (crop_scene.min.x.abs() < 2.0 && crop_scene.min.y.abs() < 2.0)
                        && ((crop_scene.width() - self.template.width_px as f32).abs() < 4.0)
                        && ((crop_scene.height() - self.template.height_px as f32).abs() < 4.0)
                } else {
                    false
                };

                let mut active_handle: Option<CropHandle> = None;
                if let (Some(crop_scene), Some(pos)) = (crop_opt, pointer) {
                    let screen_crop = Rect::from_min_max(
                        transform.scene_to_screen(crop_scene.min),
                        transform.scene_to_screen(crop_scene.max),
                    );
                    if let Some(handle) = self.hit_test_crop_handle(screen_crop, pos) {
                        // If the crop frame is full canvas, dragging inside without hitting handles
                        // should allow drag-selecting a new portion of the canvas!
                        if is_full_canvas && handle == CropHandle::Inside {
                            response.ctx.set_cursor_icon(CursorIcon::Crosshair);
                            active_handle = None;
                        } else {
                            response.ctx.set_cursor_icon(handle.cursor_icon());
                            active_handle = Some(handle);
                        }
                    } else {
                        response.ctx.set_cursor_icon(CursorIcon::Crosshair);
                    }
                } else {
                    response.ctx.set_cursor_icon(CursorIcon::Crosshair);
                }

                if response.drag_started() {
                    if let Some(pos) = pointer {
                        let scene_pos = transform.screen_to_scene(pos);
                        if let Some(handle) = active_handle {
                            self.state.crop_drag_handle = Some(handle);
                            self.state.crop_drag_start_pointer = Some(scene_pos);
                            self.state.crop_drag_start_rect = crop_opt;
                        } else {
                            // Drag to select a new crop portion on the canvas
                            self.state.crop_drag_handle = None;
                            self.state.crop_drag_start_pointer = Some(scene_pos);
                            self.state.crop_drag_start_rect = None;
                            self.state.crop_rect = Some(Rect::from_two_pos(scene_pos, scene_pos));
                        }
                    }
                }

                if response.dragged() {
                    if let (Some(start_p), Some(curr_screen)) =
                        (self.state.crop_drag_start_pointer, pointer)
                    {
                        let curr_p = transform.screen_to_scene(curr_screen);

                        if let Some(handle) = self.state.crop_drag_handle {
                            if let Some(start_r) = self.state.crop_drag_start_rect {
                                response.ctx.set_cursor_icon(handle.cursor_icon());
                                let delta = curr_p - start_p;
                                let mut r = start_r;

                                match handle {
                                    CropHandle::Inside => {
                                        r = r.translate(delta);
                                    }
                                    CropHandle::TopLeft => {
                                        r.min.x =
                                            (start_r.min.x + delta.x).min(start_r.max.x - 10.0);
                                        r.min.y =
                                            (start_r.min.y + delta.y).min(start_r.max.y - 10.0);
                                    }
                                    CropHandle::TopCenter => {
                                        r.min.y =
                                            (start_r.min.y + delta.y).min(start_r.max.y - 10.0);
                                    }
                                    CropHandle::TopRight => {
                                        r.max.x =
                                            (start_r.max.x + delta.x).max(start_r.min.x + 10.0);
                                        r.min.y =
                                            (start_r.min.y + delta.y).min(start_r.max.y - 10.0);
                                    }
                                    CropHandle::MiddleLeft => {
                                        r.min.x =
                                            (start_r.min.x + delta.x).min(start_r.max.x - 10.0);
                                    }
                                    CropHandle::MiddleRight => {
                                        r.max.x =
                                            (start_r.max.x + delta.x).max(start_r.min.x + 10.0);
                                    }
                                    CropHandle::BottomLeft => {
                                        r.min.x =
                                            (start_r.min.x + delta.x).min(start_r.max.x - 10.0);
                                        r.max.y =
                                            (start_r.max.y + delta.y).max(start_r.min.y + 10.0);
                                    }
                                    CropHandle::BottomCenter => {
                                        r.max.y =
                                            (start_r.max.y + delta.y).max(start_r.min.y + 10.0);
                                    }
                                    CropHandle::BottomRight => {
                                        r.max.x =
                                            (start_r.max.x + delta.x).max(start_r.min.x + 10.0);
                                        r.max.y =
                                            (start_r.max.y + delta.y).max(start_r.min.y + 10.0);
                                    }
                                }

                                // Apply aspect ratio preset if constrained
                                let target_ratio = match self.state.crop_aspect_preset {
                                    CropAspectPreset::Free => None,
                                    CropAspectPreset::Custom => {
                                        if self.state.crop_height > 0.0 {
                                            Some(
                                                (self.state.crop_width / self.state.crop_height)
                                                    as f32,
                                            )
                                        } else {
                                            None
                                        }
                                    }
                                    CropAspectPreset::Original => Some(
                                        self.template.width_px as f32
                                            / self.template.height_px as f32,
                                    ),
                                    CropAspectPreset::Square => Some(1.0),
                                    CropAspectPreset::Cr80 => Some(85.6 / 54.0),
                                    CropAspectPreset::Ratio4_3 => Some(4.0 / 3.0),
                                    CropAspectPreset::Ratio16_9 => Some(16.0 / 9.0),
                                };

                                if let Some(ratio) = target_ratio {
                                    if handle != CropHandle::Inside {
                                        let current_w = r.width();
                                        let desired_h = (current_w / ratio).max(10.0);
                                        r.max.y = r.min.y + desired_h;
                                    }
                                }

                                self.state.crop_width = r.width().round() as f64;
                                self.state.crop_height = r.height().round() as f64;
                                self.state.crop_rect = Some(r);
                            }
                        } else {
                            // DRAGGING TO SELECT PORTION OF CANVAS
                            response.ctx.set_cursor_icon(CursorIcon::Crosshair);
                            let min_x = start_p.x.min(curr_p.x);
                            let min_y = start_p.y.min(curr_p.y);
                            let max_x = start_p.x.max(curr_p.x);
                            let mut max_y = start_p.y.max(curr_p.y);

                            // Apply aspect ratio preset if constrained
                            let target_ratio = match self.state.crop_aspect_preset {
                                CropAspectPreset::Free => None,
                                CropAspectPreset::Custom => {
                                    if self.state.crop_height > 0.0 {
                                        Some(
                                            (self.state.crop_width / self.state.crop_height) as f32,
                                        )
                                    } else {
                                        None
                                    }
                                }
                                CropAspectPreset::Original => Some(
                                    self.template.width_px as f32 / self.template.height_px as f32,
                                ),
                                CropAspectPreset::Square => Some(1.0),
                                CropAspectPreset::Cr80 => Some(85.6 / 54.0),
                                CropAspectPreset::Ratio4_3 => Some(4.0 / 3.0),
                                CropAspectPreset::Ratio16_9 => Some(16.0 / 9.0),
                            };

                            if let Some(ratio) = target_ratio {
                                let w = (max_x - min_x).max(1.0);
                                let h = (w / ratio).max(1.0);
                                max_y = min_y + h;
                            }

                            let r = Rect::from_min_max(
                                Pos2::new(min_x, min_y),
                                Pos2::new(max_x, max_y),
                            );
                            self.state.crop_width = r.width().round().max(10.0) as f64;
                            self.state.crop_height = r.height().round().max(10.0) as f64;
                            self.state.crop_rect = Some(r);
                        }
                    }
                }

                if response.drag_stopped() {
                    self.state.crop_drag_handle = None;
                    self.state.crop_drag_start_pointer = None;
                    self.state.crop_drag_start_rect = None;

                    if let Some(r) = self.state.crop_rect {
                        let normalized = Rect::from_min_max(
                            Pos2::new(r.min.x.min(r.max.x), r.min.y.min(r.max.y)),
                            Pos2::new(r.min.x.max(r.max.x), r.min.y.max(r.max.y)),
                        );
                        let w = normalized.width().max(10.0);
                        let h = normalized.height().max(10.0);
                        let final_rect = Rect::from_min_size(normalized.min, Vec2::new(w, h));
                        self.state.crop_rect = Some(final_rect);
                        self.state.crop_width = w.round() as f64;
                        self.state.crop_height = h.round() as f64;
                    }
                }
            }

            EditorTool::Eyedropper => {
                response.ctx.set_cursor_icon(CursorIcon::Crosshair);
                if is_left_clicked {
                    if let Some(pos) = pointer {
                        let scene_pos = transform.screen_to_scene(pos);
                        if let Some(hit_id) = self.hit_test(scene_pos) {
                            if let Some(el) = self.template.get_element_by_id(&hit_id) {
                                let c = parse_color(
                                    &el.style.background_color,
                                    parse_color(&el.style.font_color, Color32::BLACK),
                                );
                                self.state.foreground_color = c;
                                self.state.sampled_color = Some(c);
                                self.state.sampled_hex =
                                    format!("#{:02X}{:02X}{:02X}", c.r(), c.g(), c.b());
                            }
                        } else {
                            let c = parse_color(&self.template.background_color, Color32::WHITE);
                            self.state.foreground_color = c;
                            self.state.sampled_color = Some(c);
                            self.state.sampled_hex =
                                format!("#{:02X}{:02X}{:02X}", c.r(), c.g(), c.b());
                        }
                    }
                }
            }

            EditorTool::PaintBucket => {
                response.ctx.set_cursor_icon(CursorIcon::Crosshair);
                if is_left_clicked {
                    if let Some(pos) = pointer {
                        let scene_pos = transform.screen_to_scene(pos);
                        let hex = format!(
                            "#{:02X}{:02X}{:02X}",
                            self.state.foreground_color.r(),
                            self.state.foreground_color.g(),
                            self.state.foreground_color.b()
                        );
                        if let Some(hit_id) = self.hit_test(scene_pos) {
                            self.state.execute(
                                self.template,
                                EditorCommand::UpdateColor {
                                    id: hit_id,
                                    target: SwatchTarget::Fill,
                                    color: hex,
                                },
                            );
                        } else {
                            self.state.execute(
                                self.template,
                                EditorCommand::SetBackgroundColor { color: hex },
                            );
                        }
                    }
                }
            }

            EditorTool::Brush => {
                response.ctx.set_cursor_icon(CursorIcon::Crosshair);
                if response.drag_started() {
                    self.state.live_brush_stroke.clear();
                    if let Some(pos) = pointer {
                        self.state
                            .live_brush_stroke
                            .push(transform.screen_to_scene(pos));
                    }
                }
                if response.dragged() {
                    if let Some(pos) = pointer {
                        let sc = transform.screen_to_scene(pos);
                        if self
                            .state
                            .live_brush_stroke
                            .last()
                            .map_or(true, |last| (*last - sc).length() >= 2.0)
                        {
                            self.state.live_brush_stroke.push(sc);
                        }
                    }
                }
                if response.drag_stopped() {
                    if self.state.live_brush_stroke.len() >= 2 {
                        let pts = &self.state.live_brush_stroke;
                        let min_x = pts.iter().map(|p| p.x).fold(f32::INFINITY, f32::min) as f64;
                        let min_y = pts.iter().map(|p| p.y).fold(f32::INFINITY, f32::min) as f64;
                        let max_x =
                            pts.iter().map(|p| p.x).fold(f32::NEG_INFINITY, f32::max) as f64;
                        let max_y =
                            pts.iter().map(|p| p.y).fold(f32::NEG_INFINITY, f32::max) as f64;

                        let points_vec: Vec<[f32; 2]> = pts.iter().map(|p| [p.x, p.y]).collect();
                        let points_json = serde_json::to_string(&points_vec).unwrap_or_default();
                        let hex = format!(
                            "#{:02X}{:02X}{:02X}",
                            self.state.foreground_color.r(),
                            self.state.foreground_color.g(),
                            self.state.foreground_color.b()
                        );

                        let mut elem = self.create_default_element("brush");
                        elem.name = "Brush Stroke".into();
                        elem.x = min_x;
                        elem.y = min_y;
                        elem.width = (max_x - min_x).max(2.0);
                        elem.height = (max_y - min_y).max(2.0);
                        elem.static_content = Some(points_json);
                        elem.style.border_width = self.state.brush_size.round().max(1.0) as u32;
                        elem.style.font_color = hex.clone();
                        elem.style.border_color = hex;

                        let id = elem.id.clone();
                        self.state.execute(self.template, EditorCommand::Add(elem));
                        self.state.selected_id = Some(id);
                    }
                    self.state.live_brush_stroke.clear();
                }
            }

            EditorTool::Eraser => {
                response.ctx.set_cursor_icon(CursorIcon::Crosshair);
                let erase_radius = (self.state.brush_size / 2.0).max(4.0);

                if response.drag_started() {
                    self.state.eraser_drag_snapshot = Some(self.template.clone());
                    self.state.eraser_modified = false;
                    if let Some(pos) = pointer {
                        self.state.last_eraser_pos = Some(transform.screen_to_scene(pos));
                    }
                }

                if response.dragged() {
                    if let Some(pos) = pointer {
                        let curr_scene = transform.screen_to_scene(pos);
                        let prev_scene = self.state.last_eraser_pos.unwrap_or(curr_scene);
                        self.state.last_eraser_pos = Some(curr_scene);

                        let modified = Self::erase_brush_strokes(
                            self.template,
                            prev_scene,
                            curr_scene,
                            erase_radius,
                        );
                        if modified {
                            self.state.eraser_modified = true;
                        }
                    }
                }

                if response.drag_stopped()
                    || (!response.dragged()
                        && !response.drag_started()
                        && self.state.eraser_drag_snapshot.is_some())
                {
                    self.state.last_eraser_pos = None;
                    if self.state.eraser_modified {
                        if let Some(before) = self.state.eraser_drag_snapshot.take() {
                            self.state.history.record_action(
                                before,
                                self.template,
                                "Erase Brush Stroke".into(),
                            );
                        }
                    }
                    self.state.eraser_drag_snapshot = None;
                    self.state.eraser_modified = false;
                } else if is_left_clicked && !response.dragged() && !response.drag_started() {
                    // Single click without dragging: carve at click position
                    if let Some(pos) = pointer {
                        let scene_pos = transform.screen_to_scene(pos);
                        let before = self.template.clone();
                        let modified = Self::erase_brush_strokes(
                            self.template,
                            scene_pos,
                            scene_pos,
                            erase_radius,
                        );
                        if modified {
                            self.state.history.record_action(
                                before,
                                self.template,
                                "Erase Brush Stroke".into(),
                            );
                        }
                    }
                }

                if let Some(sel_id) = &self.state.selected_id {
                    if self.template.get_element_by_id(sel_id).is_none() {
                        self.state.selected_id = None;
                    }
                }
            }

            EditorTool::Gradient => {
                response.ctx.set_cursor_icon(CursorIcon::Crosshair);
                if response.drag_started() {
                    if let Some(pos) = pointer {
                        let sp = transform.screen_to_scene(pos);
                        self.state.gradient_start = Some(sp);
                        self.state.gradient_end = Some(sp);
                    }
                }
                if response.dragged() {
                    if let Some(pos) = pointer {
                        self.state.gradient_end = Some(transform.screen_to_scene(pos));
                    }
                }
                if response.drag_stopped() {
                    if let (Some(start), Some(end)) = (
                        self.state.gradient_start.take(),
                        self.state.gradient_end.take(),
                    ) {
                        let dist = (end - start).length();
                        if dist >= 5.0 {
                            let angle = (end.y - start.y).atan2(end.x - start.x).to_degrees();
                            let from_hex = format!(
                                "#{:02X}{:02X}{:02X}",
                                self.state.foreground_color.r(),
                                self.state.foreground_color.g(),
                                self.state.foreground_color.b()
                            );
                            let to_hex = format!(
                                "#{:02X}{:02X}{:02X}",
                                self.state.background_color.r(),
                                self.state.background_color.g(),
                                self.state.background_color.b()
                            );

                            if let Some(id) = self.state.selected_id.clone() {
                                self.state.execute(
                                    self.template,
                                    EditorCommand::UpdateColor {
                                        id,
                                        target: SwatchTarget::Fill,
                                        color: from_hex,
                                    },
                                );
                            } else {
                                self.state.execute(
                                    self.template,
                                    EditorCommand::SetBackgroundGradient {
                                        from_color: from_hex,
                                        to_color: to_hex,
                                        angle,
                                    },
                                );
                            }
                        }
                    }
                }
            }

            EditorTool::Text => {
                response.ctx.set_cursor_icon(CursorIcon::Text);
                if is_left_clicked {
                    if let Some(pos) = pointer {
                        let scene_pos = transform.screen_to_scene(pos);
                        let mut elem = self.create_default_element("text");
                        elem.x = f64::from(scene_pos.x);
                        elem.y = f64::from(scene_pos.y);
                        elem.style.font_family = self.state.font_family.clone();
                        elem.style.font_size = self.state.font_size;
                        elem.style.font_bold = self.state.font_bold;
                        elem.style.font_italic = self.state.font_italic;
                        let id = elem.id.clone();
                        self.state.execute(self.template, EditorCommand::Add(elem));
                        self.state.selected_id = Some(id.clone());
                        self.start_editing_text(id);
                    }
                }
            }

            EditorTool::Shape => {
                response.ctx.set_cursor_icon(CursorIcon::Crosshair);
                if response.drag_started() {
                    if let Some(pos) = pointer {
                        self.state.tool_drag_start = Some(transform.screen_to_scene(pos));
                    }
                }
                if response.dragged() {
                    if let (Some(start), Some(curr)) = (self.state.tool_drag_start, pointer) {
                        let curr_scene = transform.screen_to_scene(curr);
                        self.state.live_shape_rect = Some(Rect::from_two_pos(start, curr_scene));
                    }
                }
                if response.drag_stopped() {
                    if let Some(rect) = self.state.live_shape_rect.take() {
                        let w = (rect.width() as f64).abs();
                        let h = (rect.height() as f64).abs();
                        let min_x = rect.left() as f64;
                        let min_y = rect.top() as f64;

                        if w > 4.0 || h > 4.0 {
                            let kind = match self.state.active_shape {
                                ShapeKind::Rectangle => "rect",
                                ShapeKind::RoundedRectangle => "round_rect",
                                ShapeKind::Ellipse => "ellipse",
                                ShapeKind::Line => "line",
                            };
                            let mut elem = self.create_default_element(kind);
                            elem.x = min_x;
                            elem.y = min_y;
                            elem.width = w.max(10.0);
                            elem.height = h.max(10.0);
                            elem.style.border_radius = self.state.shape_corner_radius;
                            elem.style.border_width = self.state.shape_border_width;
                            let fill_hex = format!(
                                "#{:02X}{:02X}{:02X}",
                                self.state.shape_fill_color.r(),
                                self.state.shape_fill_color.g(),
                                self.state.shape_fill_color.b()
                            );
                            let stroke_hex = format!(
                                "#{:02X}{:02X}{:02X}",
                                self.state.shape_border_color.r(),
                                self.state.shape_border_color.g(),
                                self.state.shape_border_color.b()
                            );
                            elem.style.background_color = fill_hex;
                            elem.style.border_color = stroke_hex;

                            let id = elem.id.clone();
                            self.state.execute(self.template, EditorCommand::Add(elem));
                            self.state.selected_id = Some(id);
                        }
                    }
                    self.state.tool_drag_start = None;
                } else if is_left_clicked && self.state.live_shape_rect.is_none() {
                    if let Some(pos) = pointer {
                        let scene_pos = transform.screen_to_scene(pos);
                        let kind = match self.state.active_shape {
                            ShapeKind::Rectangle => "rect",
                            ShapeKind::RoundedRectangle => "round_rect",
                            ShapeKind::Ellipse => "ellipse",
                            ShapeKind::Line => "line",
                        };
                        let mut elem = self.create_default_element(kind);
                        elem.x = (scene_pos.x as f64 - elem.width / 2.0).max(0.0);
                        elem.y = (scene_pos.y as f64 - elem.height / 2.0).max(0.0);
                        let id = elem.id.clone();
                        self.state.execute(self.template, EditorCommand::Add(elem));
                        self.state.selected_id = Some(id);
                    }
                }
            }

            EditorTool::Marquee => {
                response.ctx.set_cursor_icon(CursorIcon::Crosshair);
                if response.drag_started() {
                    if let Some(pos) = pointer {
                        self.state.tool_drag_start = Some(transform.screen_to_scene(pos));
                    }
                }
                if response.dragged() {
                    if let (Some(start), Some(curr)) = (self.state.tool_drag_start, pointer) {
                        let curr_scene = transform.screen_to_scene(curr);
                        self.state.live_marquee_rect = Some(Rect::from_two_pos(start, curr_scene));
                    }
                }
                if response.drag_stopped() {
                    if let Some(rect) = self.state.live_marquee_rect.take() {
                        let hit = self.template.elements.iter().find(|elem| {
                            let elem_rect = Rect::from_min_size(
                                Pos2::new(elem.x as f32, elem.y as f32),
                                Vec2::new(elem.width as f32, elem.height as f32),
                            );
                            rect.intersects(elem_rect)
                        });
                        self.state.selected_id = hit.map(|elem| elem.id.clone());
                    }
                    self.state.tool_drag_start = None;
                }
            }

            EditorTool::ObjectSelect => {
                response.ctx.set_cursor_icon(CursorIcon::Crosshair);
                if let Some(pos) = pointer {
                    self.state.hovered_object_id = self.hit_test(transform.screen_to_scene(pos));
                }
                if is_left_clicked {
                    self.state.selected_id = self.state.hovered_object_id.clone();
                }
            }

            EditorTool::Move => {
                // TBox handle hover detection & Bidirectional cursor feedback
                if let Some(pos) = pointer {
                    if let Some(id) = &self.state.selected_id {
                        if let Some(elem) = self.template.get_element_by_id(id) {
                            if let Some(handle) = self.hit_test_handle(elem, transform, pos) {
                                response.ctx.set_cursor_icon(handle.cursor_icon());
                            }
                        }
                    }
                }

                if response.drag_started() {
                    if let Some(pos) = pointer {
                        let scene_pos = transform.screen_to_scene(pos);
                        let mut target_id = self.state.selected_id.clone();
                        let mut target_handle = None;

                        if let Some(id) = &target_id {
                            if let Some(element) = self.template.get_element_by_id(id) {
                                target_handle = self.hit_test_handle(element, transform, pos);
                            }
                        }

                        if target_handle.is_none() {
                            if let Some(hit_elem_id) = self.hit_test(scene_pos) {
                                self.state.selected_id = Some(hit_elem_id.clone());
                                target_id = Some(hit_elem_id);
                                target_handle = Some(TransformHandle::Body);
                            }
                        }

                        if let (Some(id), Some(handle)) = (target_id, target_handle) {
                            if let Some(element) = self.template.get_element_by_id(&id).cloned() {
                                if !element.locked {
                                    let elem_rect = Rect::from_min_size(
                                        Pos2::new(element.x as f32, element.y as f32),
                                        Vec2::new(element.width as f32, element.height as f32),
                                    );
                                    self.state.drag = Some(DragState {
                                        id: id.clone(),
                                        handle,
                                        start_element_rect: elem_rect,
                                        start_pointer_scene: transform.screen_to_scene(pos),
                                    });
                                    self.state.history.undo.push(self.template.clone());
                                    self.state
                                        .history
                                        .action_names
                                        .push("Transform element".into());
                                    self.state.history.redo.clear();
                                }
                            }
                        }
                    }
                }

                if response.dragged() {
                    if let (Some(drag), Some(pos)) = (self.state.drag.as_ref(), pointer) {
                        response.ctx.set_cursor_icon(drag.handle.cursor_icon());
                        let current_scene = transform.screen_to_scene(pos);
                        let delta = current_scene - drag.start_pointer_scene;

                        if let Some(element) = self
                            .template
                            .elements
                            .iter_mut()
                            .find(|el| el.id == drag.id)
                        {
                            let r = drag.start_element_rect;
                            let (mut nx, mut ny, mut nw, mut nh) = (
                                r.min.x as f64,
                                r.min.y as f64,
                                r.width() as f64,
                                r.height() as f64,
                            );

                            match drag.handle {
                                TransformHandle::Body => {
                                    nx += f64::from(delta.x);
                                    ny += f64::from(delta.y);
                                }
                                TransformHandle::TopLeft => {
                                    nx += f64::from(delta.x);
                                    ny += f64::from(delta.y);
                                    nw -= f64::from(delta.x);
                                    nh -= f64::from(delta.y);
                                }
                                TransformHandle::TopCenter => {
                                    ny += f64::from(delta.y);
                                    nh -= f64::from(delta.y);
                                }
                                TransformHandle::TopRight => {
                                    ny += f64::from(delta.y);
                                    nw += f64::from(delta.x);
                                    nh -= f64::from(delta.y);
                                }
                                TransformHandle::MiddleLeft => {
                                    nx += f64::from(delta.x);
                                    nw -= f64::from(delta.x);
                                }
                                TransformHandle::MiddleRight => {
                                    nw += f64::from(delta.x);
                                }
                                TransformHandle::BottomLeft => {
                                    nx += f64::from(delta.x);
                                    nw -= f64::from(delta.x);
                                    nh += f64::from(delta.y);
                                }
                                TransformHandle::BottomCenter => {
                                    nh += f64::from(delta.y);
                                }
                                TransformHandle::BottomRight => {
                                    nw += f64::from(delta.x);
                                    nh += f64::from(delta.y);
                                }
                                TransformHandle::Rotate => {}
                            }

                            if self.state.snap_to_grid {
                                nx = (nx / 5.0).round() * 5.0;
                                ny = (ny / 5.0).round() * 5.0;
                                nw = (nw / 5.0).round() * 5.0;
                                nh = (nh / 5.0).round() * 5.0;
                            }

                            let is_text =
                                element.r#type == "text" || element.r#type == "dynamic_text";
                            let (min_w, min_h) = if is_text {
                                (40.0, 20.0)
                            } else if element.r#type == "line" {
                                (10.0, 2.0)
                            } else {
                                (24.0, 24.0)
                            };

                            if nw < min_w {
                                match drag.handle {
                                    TransformHandle::TopLeft
                                    | TransformHandle::MiddleLeft
                                    | TransformHandle::BottomLeft => {
                                        nx = (r.max.x as f64) - min_w;
                                    }
                                    _ => {}
                                }
                                nw = min_w;
                            }
                            if nh < min_h {
                                match drag.handle {
                                    TransformHandle::TopLeft
                                    | TransformHandle::TopCenter
                                    | TransformHandle::TopRight => {
                                        ny = (r.max.y as f64) - min_h;
                                    }
                                    _ => {}
                                }
                                nh = min_h;
                            }

                            element.x = nx;
                            element.y = ny;
                            element.width = nw;
                            element.height = nh;
                        }
                    } else if response.dragged_by(PointerButton::Primary)
                        && self.state.selected_id.is_none()
                    {
                        self.state.pan += response.drag_motion();
                    }
                }

                if response.drag_stopped() {
                    self.state.drag = None;
                }

                // Single click selection
                if is_left_clicked && self.state.drag.is_none() {
                    if let Some(pos) = pointer {
                        if canvas_area.contains(pos) {
                            let hit = self.hit_test(transform.screen_to_scene(pos));
                            self.state.selected_id = hit;
                        }
                    }
                }
            }
        }
    }

    fn hit_test(&self, point: Pos2) -> Option<String> {
        self.template
            .elements
            .iter()
            .filter(|element| {
                element.visible
                    && element.x <= f64::from(point.x)
                    && element.y <= f64::from(point.y)
                    && element.x + element.width >= f64::from(point.x)
                    && element.y + element.height >= f64::from(point.y)
            })
            .max_by_key(|element| element.z_index)
            .map(|element| element.id.clone())
    }

    fn create_default_element(&self, kind: &str) -> CanvasElement {
        let (name, width, height) = match kind {
            "photo" => ("Profile Photo".into(), 160.0, 190.0),
            "dynamic_text" => ("Dynamic Text".into(), 220.0, 36.0),
            "text" => ("Text Layer".into(), 200.0, 32.0),
            "round_rect" => ("Rounded Card".into(), 240.0, 120.0),
            "ellipse" => ("Circle Shape".into(), 100.0, 100.0),
            "line" => ("Divider Line".into(), 240.0, 4.0),
            "brush" => ("Brush Stroke".into(), 10.0, 10.0),
            "gradient" => ("Gradient Fill".into(), 200.0, 100.0),
            _ => ("Rectangle".into(), 240.0, 120.0),
        };

        let fg_hex = format!(
            "#{:02X}{:02X}{:02X}",
            self.state.foreground_color.r(),
            self.state.foreground_color.g(),
            self.state.foreground_color.b()
        );

        let style = CanvasElementStyle {
            font_family: self.state.font_family.clone(),
            font_size: self.state.font_size,
            font_bold: self.state.font_bold,
            font_italic: self.state.font_italic,
            font_color: fg_hex.clone(),
            background_color: if kind == "rect" || kind == "round_rect" || kind == "ellipse" {
                fg_hex
            } else {
                "#00000000".into()
            },
            border_color: "#CBD5E1".into(),
            border_width: if kind == "rect" || kind == "round_rect" || kind == "ellipse" {
                1
            } else {
                0
            },
            border_radius: if kind == "round_rect" { 12 } else { 0 },
            ..Default::default()
        };

        CanvasElement {
            id: Uuid::new_v4().to_string(),
            name,
            r#type: kind.into(),
            x: 60.0,
            y: 60.0,
            width,
            height,
            z_index: self.template.elements.len() as i32 + 1,
            visible: true,
            locked: false,
            binding: None,
            static_content: if kind == "text" {
                Some("Sample Text".into())
            } else {
                None
            },
            style,
        }
    }

    fn add_element(&mut self, kind: &str) {
        let element = self.create_default_element(kind);
        let id = element.id.clone();
        self.state
            .execute(self.template, EditorCommand::Add(element));
        self.state.selected_id = Some(id);
    }

    pub fn erase_brush_strokes(
        template: &mut TemplateDefinition,
        p_start: Pos2,
        p_end: Pos2,
        erase_radius: f32,
    ) -> bool {
        erase_brush_strokes_impl(template, p_start, p_end, erase_radius)
    }
}

fn parse_color(hex: &str, fallback: Color32) -> Color32 {
    let clean = hex.trim().trim_start_matches('#');
    match clean.len() {
        6 => {
            let r = u8::from_str_radix(&clean[0..2], 16).unwrap_or(fallback.r());
            let g = u8::from_str_radix(&clean[2..4], 16).unwrap_or(fallback.g());
            let b = u8::from_str_radix(&clean[4..6], 16).unwrap_or(fallback.b());
            Color32::from_rgb(r, g, b)
        }
        8 => {
            let r = u8::from_str_radix(&clean[0..2], 16).unwrap_or(fallback.r());
            let g = u8::from_str_radix(&clean[2..4], 16).unwrap_or(fallback.g());
            let b = u8::from_str_radix(&clean[4..6], 16).unwrap_or(fallback.b());
            let a = u8::from_str_radix(&clean[6..8], 16).unwrap_or(fallback.a());
            Color32::from_rgba_premultiplied(r, g, b, a)
        }
        _ => fallback,
    }
}

/// Parse brush stroke points from JSON content.
/// Supports both single-path format `[[x, y], ...]` and multi-path format `[[[x, y], ...], ...]`.
pub fn parse_brush_paths(content: &str) -> Vec<Vec<[f32; 2]>> {
    if let Ok(multi) = serde_json::from_str::<Vec<Vec<[f32; 2]>>>(content) {
        if !multi.is_empty() {
            return multi;
        }
    }
    if let Ok(single) = serde_json::from_str::<Vec<[f32; 2]>>(content) {
        if !single.is_empty() {
            return vec![single];
        }
    }
    if let Ok(values) = serde_json::from_str::<Vec<serde_json::Value>>(content) {
        let single: Vec<[f32; 2]> = values
            .into_iter()
            .filter_map(|v| {
                if let (Some(x), Some(y)) = (
                    v.get("x").and_then(|x| x.as_f64()),
                    v.get("y").and_then(|y| y.as_f64()),
                ) {
                    Some([x as f32, y as f32])
                } else {
                    None
                }
            })
            .collect();
        if !single.is_empty() {
            return vec![single];
        }
    }
    Vec::new()
}

/// Serialize brush paths back into JSON string.
/// If there is only one path, serialize as a flat `[[x, y], ...]` for backwards compatibility.
/// If there are multiple paths, serialize as `[[[x, y], ...], ...]`.
pub fn serialize_brush_paths(paths: &[Vec<[f32; 2]>]) -> String {
    if paths.len() == 1 {
        serde_json::to_string(&paths[0]).unwrap_or_default()
    } else {
        serde_json::to_string(paths).unwrap_or_default()
    }
}

/// Helper to calculate distance from point `p` to line segment `a`->`b`.
fn point_to_segment_dist(p: Pos2, a: Pos2, b: Pos2) -> f32 {
    let ab = b - a;
    let len_sq = ab.length_sq();
    if len_sq <= 1e-6 {
        return (p - a).length();
    }
    let t = ((p - a).dot(ab) / len_sq).clamp(0.0, 1.0);
    let proj = a + ab * t;
    (p - proj).length()
}

/// Densifies a polyline so adjacent points are no further apart than `max_step`.
fn densify_path(path: &[[f32; 2]], max_step: f32) -> Vec<[f32; 2]> {
    if path.len() < 2 {
        return path.to_vec();
    }
    let mut dense = Vec::new();
    for window in path.windows(2) {
        let p1 = Pos2::new(window[0][0], window[0][1]);
        let p2 = Pos2::new(window[1][0], window[1][1]);
        let dist = (p2 - p1).length();
        let steps = (dist / max_step).ceil().max(1.0) as usize;
        for i in 0..steps {
            let t = i as f32 / steps as f32;
            let pt = p1 + (p2 - p1) * t;
            dense.push([pt.x, pt.y]);
        }
    }
    if let Some(last) = path.last() {
        dense.push(*last);
    }
    dense
}

pub fn erase_brush_strokes_impl(
    template: &mut TemplateDefinition,
    p_start: Pos2,
    p_end: Pos2,
    erase_radius: f32,
) -> bool {
    let mut any_modified = false;
    let mut to_delete = Vec::new();

    for elem in template.elements.iter_mut() {
        if elem.r#type != "brush" || !elem.visible || elem.locked {
            continue;
        }

        let Some(content) = elem.static_content.as_deref() else {
            continue;
        };

        let paths = parse_brush_paths(content);
        if paths.is_empty() {
            continue;
        }

        let stroke_width = (elem.style.border_width.max(1) as f32).max(1.0);
        let half_stroke = stroke_width / 2.0;

        // Quick bounding box rejection check
        let margin = erase_radius + half_stroke;
        let min_x = p_start.x.min(p_end.x) - margin;
        let max_x = p_start.x.max(p_end.x) + margin;
        let min_y = p_start.y.min(p_end.y) - margin;
        let max_y = p_start.y.max(p_end.y) + margin;

        if elem.x > max_x as f64
            || elem.x + elem.width < min_x as f64
            || elem.y > max_y as f64
            || elem.y + elem.height < min_y as f64
        {
            continue;
        }

        let mut surviving_paths: Vec<Vec<[f32; 2]>> = Vec::new();
        let mut element_modified = false;

        for path in paths {
            // Test if any point in this path touches the eraser
            let path_touches_eraser = path.iter().any(|pt| {
                point_to_segment_dist(Pos2::new(pt[0], pt[1]), p_start, p_end) <= erase_radius
            }) || path.windows(2).any(|w| {
                let p1 = Pos2::new(w[0][0], w[0][1]);
                let p2 = Pos2::new(w[1][0], w[1][1]);
                let mid = p1 + (p2 - p1) * 0.5;
                point_to_segment_dist(mid, p_start, p_end) <= erase_radius
            });

            if !path_touches_eraser {
                // Completely untouched path! Keep 100% of original points without any modification!
                surviving_paths.push(path);
                continue;
            }

            // Path is touched: densify only this path so the cut is clean and smooth
            let dense = densify_path(&path, 2.0);
            let mut current_segment: Vec<[f32; 2]> = Vec::new();

            for pt in dense {
                let pos = Pos2::new(pt[0], pt[1]);
                let dist = point_to_segment_dist(pos, p_start, p_end);
                if dist <= erase_radius {
                    element_modified = true;
                    if !current_segment.is_empty() {
                        surviving_paths.push(current_segment);
                        current_segment = Vec::new();
                    }
                } else {
                    current_segment.push(pt);
                }
            }

            if !current_segment.is_empty() {
                surviving_paths.push(current_segment);
            }
        }

        if element_modified {
            any_modified = true;
            if surviving_paths.is_empty() {
                to_delete.push(elem.id.clone());
            } else {
                let all_pts: Vec<Pos2> = surviving_paths
                    .iter()
                    .flat_map(|seg| seg.iter().map(|p| Pos2::new(p[0], p[1])))
                    .collect();
                let min_x = all_pts.iter().map(|p| p.x).fold(f32::INFINITY, f32::min) as f64;
                let min_y = all_pts.iter().map(|p| p.y).fold(f32::INFINITY, f32::min) as f64;
                let max_x = all_pts
                    .iter()
                    .map(|p| p.x)
                    .fold(f32::NEG_INFINITY, f32::max) as f64;
                let max_y = all_pts
                    .iter()
                    .map(|p| p.y)
                    .fold(f32::NEG_INFINITY, f32::max) as f64;

                elem.x = min_x;
                elem.y = min_y;
                elem.width = (max_x - min_x).max(2.0);
                elem.height = (max_y - min_y).max(2.0);
                elem.static_content = Some(serialize_brush_paths(&surviving_paths));
            }
        }
    }

    if !to_delete.is_empty() {
        template
            .elements
            .retain(|elem| !to_delete.contains(&elem.id));
    }

    any_modified
}
