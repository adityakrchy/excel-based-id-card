//! Native, compatibility-first renderer for template previews and exports.
//!
//! The renderer deliberately returns an RGBA image for both preview and export
//! callers. Export callers can pass that same rendered image to [`encode`], so
//! preview and file output share one rendering path.

use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
};

use ab_glyph::{FontArc, PxScale};
use image::{
    codecs::jpeg::{JpegEncoder, PixelDensity},
    imageops::{self, FilterType},
    ExtendedColorType, Rgba, RgbaImage,
};
use imageproc::{
    drawing::{
        draw_filled_circle_mut, draw_filled_ellipse_mut, draw_filled_rect_mut,
        draw_hollow_ellipse_mut, draw_hollow_rect_mut, draw_line_segment_mut, draw_text_mut,
        text_size,
    },
    rect::Rect,
};
use thiserror::Error;

use crate::data::models::{
    CanvasElement, ImageFitMode, MissingPhotoPolicy, OutputFormat, RenderSettings, SourceRecord,
    TemplateDefinition, TextOverflowPolicy,
};

/// A non-fatal issue encountered while rendering.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RenderWarning {
    MissingTemplateBackground {
        path: String,
    },
    CorruptTemplateBackground {
        path: String,
        details: String,
    },
    MissingImage {
        element: String,
        path: String,
    },
    CorruptImage {
        element: String,
        path: String,
        details: String,
    },
    MissingPhoto {
        pin: String,
    },
    CorruptPhoto {
        path: String,
        details: String,
    },
    MissingFont {
        family: String,
    },
    InvalidColor {
        context: String,
        value: String,
    },
    TextOverflow {
        element: String,
    },
    UnknownElementType {
        element: String,
        element_type: String,
    },
}

/// A failure that prevents a rendered image or encoded output from being produced.
#[derive(Debug, Error)]
pub enum RenderError {
    #[error("template dimensions must be non-zero, got {width}x{height}")]
    InvalidDimensions { width: u32, height: u32 },
    #[error("required photo is missing for PIN '{pin}'")]
    MissingRequiredPhoto { pin: String },
    #[error("could not encode {format} output: {details}")]
    Encode { format: String, details: String },
}

/// The RGBA result shared by preview and export callers.
#[derive(Debug, Clone)]
pub struct RenderedImage {
    pub image: RgbaImage,
    pub warnings: Vec<RenderWarning>,
}

impl RenderedImage {
    pub fn dimensions(&self) -> (u32, u32) {
        self.image.dimensions()
    }

    /// Encode this result using the template's dimensions and DPI metadata.
    pub fn encode<W: Write>(
        &self,
        template: &TemplateDefinition,
        settings: &RenderSettings,
        writer: W,
    ) -> Result<(), RenderError> {
        NativeRenderer::encode(self, template, settings, writer)
    }
}

/// Stateless native renderer used by both preview and export-oriented callers.
pub struct NativeRenderer;

impl NativeRenderer {
    /// Render one template/record/photo combination into an RGBA image.
    pub fn render(
        template: &TemplateDefinition,
        record: Option<&SourceRecord>,
        photo_path: Option<&Path>,
    ) -> Result<RenderedImage, RenderError> {
        Self::render_with_settings(template, record, photo_path, None)
    }

    /// Render with optional export settings. The image returned is always RGBA;
    /// settings only affect policies used during rendering.
    pub fn render_with_settings(
        template: &TemplateDefinition,
        record: Option<&SourceRecord>,
        photo_path: Option<&Path>,
        settings: Option<&RenderSettings>,
    ) -> Result<RenderedImage, RenderError> {
        if template.width_px == 0 || template.height_px == 0 {
            return Err(RenderError::InvalidDimensions {
                width: template.width_px,
                height: template.height_px,
            });
        }

        let mut warnings = Vec::new();
        let background = parse_color(
            &template.background_color,
            "template background",
            &mut warnings,
        );
        let mut canvas = RgbaImage::from_pixel(template.width_px, template.height_px, background);

        if let Some(path) = template.background_image_path.as_deref() {
            match load_image(path) {
                Ok(image) => {
                    let fitted = fit_image(
                        &image,
                        template.width_px,
                        template.height_px,
                        &ImageFitMode::Cover,
                    );
                    imageops::overlay(&mut canvas, &fitted, 0, 0);
                }
                Err(_details) if !Path::new(path).exists() => {
                    warnings.push(RenderWarning::MissingTemplateBackground { path: path.into() });
                }
                Err(details) => warnings.push(RenderWarning::CorruptTemplateBackground {
                    path: path.into(),
                    details,
                }),
            }
        }

        let mut elements: Vec<(usize, &CanvasElement)> =
            template.elements.iter().enumerate().collect();
        elements.sort_by(|(left_index, left), (right_index, right)| {
            left.z_index
                .cmp(&right.z_index)
                .then_with(|| left_index.cmp(right_index))
        });

        for (_, element) in elements {
            if !element.visible || element.width <= 0.0 || element.height <= 0.0 {
                continue;
            }
            Self::render_element(
                &mut canvas,
                template,
                element,
                record,
                photo_path,
                settings,
                &mut warnings,
            )?;
        }

        if template.border_width > 0 {
            if let Some(color) = template.border_color.as_deref() {
                let color = parse_color(color, "template border", &mut warnings);
                let rect = Rect::at(0, 0).of_size(template.width_px, template.height_px);
                draw_hollow_rect_mut(&mut canvas, rect, color);
            }
        }

        Ok(RenderedImage {
            image: canvas,
            warnings,
        })
    }

    /// Convenience method for export callers: render and encode through the
    /// same renderer implementation used for previews.
    pub fn render_to<W: Write>(
        template: &TemplateDefinition,
        record: Option<&SourceRecord>,
        photo_path: Option<&Path>,
        settings: &RenderSettings,
        writer: W,
    ) -> Result<RenderedImage, RenderError> {
        let rendered = Self::render_with_settings(template, record, photo_path, Some(settings))?;
        rendered.encode(template, settings, writer)?;
        Ok(rendered)
    }

    /// Encode an RGBA render as PNG or JPEG. PNG uses a pHYs chunk and JPEG
    /// uses JFIF density, both derived from `template.dpi`.
    pub fn encode<W: Write>(
        rendered: &RenderedImage,
        template: &TemplateDefinition,
        settings: &RenderSettings,
        writer: W,
    ) -> Result<(), RenderError> {
        match &settings.output_format {
            OutputFormat::Png => encode_png(rendered, template.dpi, writer),
            OutputFormat::Jpeg => encode_jpeg(rendered, template, settings.jpeg_quality, writer),
        }
    }

    /// Resolve a usable system font without bundling a font in the crate.
    /// `font_family` is treated as a path when it names an existing file.
    pub fn resolve_system_font_path(
        font_family: &str,
        bold: bool,
        italic: bool,
    ) -> Option<PathBuf> {
        resolve_system_font_path(font_family, bold, italic)
    }

    fn render_element(
        canvas: &mut RgbaImage,
        template: &TemplateDefinition,
        element: &CanvasElement,
        record: Option<&SourceRecord>,
        photo_path: Option<&Path>,
        settings: Option<&RenderSettings>,
        warnings: &mut Vec<RenderWarning>,
    ) -> Result<(), RenderError> {
        let x = element.x.round() as i32;
        let y = element.y.round() as i32;
        let width = element.width.round().max(1.0) as u32;
        let height = element.height.round().max(1.0) as u32;
        let opacity = element.style.opacity.clamp(0.0, 1.0);
        let mut layer = RgbaImage::from_pixel(canvas.width(), canvas.height(), Rgba([0, 0, 0, 0]));

        match element.r#type.as_str() {
            "rect" | "round_rect" | "line" | "ellipse" | "gradient" => {
                draw_shape(&mut layer, element, x, y, width, height, opacity, warnings);
            }
            "brush" => {
                draw_brush_element(&mut layer, element, opacity, warnings);
            }
            "static_text" => {
                let text = element.static_content.as_deref().unwrap_or_default();
                draw_text_element(
                    &mut layer, element, text, x, y, width, height, opacity, warnings,
                );
            }
            "dynamic_text" | "pin_field" => {
                let text = resolve_bound_text(element, record);
                draw_text_element(
                    &mut layer, element, &text, x, y, width, height, opacity, warnings,
                );
            }
            "photo" => {
                draw_photo(
                    &mut layer, template, element, record, photo_path, x, y, width, height,
                    settings, warnings,
                )?;
            }
            "image" => {
                if let Some(path) = element.static_content.as_deref() {
                    match load_image(path) {
                        Ok(image) => {
                            let fitted = fit_image(&image, width, height, &element.style.fit_mode);
                            let fitted = apply_mask_and_opacity(
                                fitted,
                                &element.style.mask_shape,
                                element.style.border_radius,
                                opacity,
                            );
                            imageops::overlay(&mut layer, &fitted, x as i64, y as i64);
                            draw_border(
                                &mut layer, element, x, y, width, height, opacity, warnings,
                            );
                        }
                        Err(_details) if !Path::new(path).exists() => {
                            warnings.push(RenderWarning::MissingImage {
                                element: element.name.clone(),
                                path: path.into(),
                            })
                        }
                        Err(details) => warnings.push(RenderWarning::CorruptImage {
                            element: element.name.clone(),
                            path: path.into(),
                            details,
                        }),
                    }
                }
            }
            element_type => warnings.push(RenderWarning::UnknownElementType {
                element: element.name.clone(),
                element_type: element_type.into(),
            }),
        }

        imageops::overlay(canvas, &layer, 0, 0);
        Ok(())
    }
}

#[allow(clippy::too_many_arguments)]
fn draw_shape(
    layer: &mut RgbaImage,
    element: &CanvasElement,
    x: i32,
    y: i32,
    width: u32,
    height: u32,
    opacity: f32,
    warnings: &mut Vec<RenderWarning>,
) {
    let fill = parse_color(&element.style.background_color, "shape fill", warnings);
    let border = parse_color(&element.style.border_color, "shape border", warnings);

    if element.r#type == "line" {
        let color = if fill[3] > 0 { fill } else { border };
        let stroke_w = element.style.border_width.max(1) as i32;
        let start = (x as f32, y as f32);
        let end = ((x + width as i32) as f32, (y + height as i32) as f32);
        for offset in 0..stroke_w {
            let dy = offset as f32 - (stroke_w as f32 / 2.0);
            draw_line_segment_mut(
                layer,
                (start.0, start.1 + dy),
                (end.0, end.1 + dy),
                apply_opacity(color, opacity),
            );
        }
        return;
    }

    if element.r#type == "ellipse" {
        let center_x = x + (width as i32) / 2;
        let center_y = y + (height as i32) / 2;
        let rx = ((width / 2) as i32).max(1);
        let ry = ((height / 2) as i32).max(1);
        if fill[3] > 0 {
            draw_filled_ellipse_mut(
                layer,
                (center_x, center_y),
                rx,
                ry,
                apply_opacity(fill, opacity),
            );
        }
        if element.style.border_width > 0 && border[3] > 0 {
            let stroke_w = element.style.border_width as i32;
            for w in 0..stroke_w {
                let r_x = (rx - w).max(1);
                let r_y = (ry - w).max(1);
                draw_hollow_ellipse_mut(
                    layer,
                    (center_x, center_y),
                    r_x,
                    r_y,
                    apply_opacity(border, opacity),
                );
            }
        }
        return;
    }

    if element.r#type == "gradient" {
        let c1 = fill;
        let c2 = border;
        let h = (height as f32).max(1.0);
        let img_w = layer.width() as i32;
        let img_h = layer.height() as i32;
        for py in 0..height {
            let curr_y = y + py as i32;
            if curr_y < 0 || curr_y >= img_h {
                continue;
            }
            let t = py as f32 / h;
            let r = (c1[0] as f32 * (1.0 - t) + c2[0] as f32 * t) as u8;
            let g = (c1[1] as f32 * (1.0 - t) + c2[1] as f32 * t) as u8;
            let b = (c1[2] as f32 * (1.0 - t) + c2[2] as f32 * t) as u8;
            let a = ((c1[3] as f32 * (1.0 - t) + c2[3] as f32 * t) * opacity.clamp(0.0, 1.0)) as u8;
            let col = Rgba([r, g, b, a]);
            for px in 0..width {
                let curr_x = x + px as i32;
                if curr_x < 0 || curr_x >= img_w {
                    continue;
                }
                layer.put_pixel(curr_x as u32, curr_y as u32, col);
            }
        }
        return;
    }

    let rounded = element.r#type == "round_rect" || element.style.border_radius > 0;
    if rounded {
        fill_rounded_rect(
            layer,
            x,
            y,
            width,
            height,
            element.style.border_radius,
            apply_opacity(fill, opacity),
        );
        if element.style.border_width > 0 {
            let inset = element.style.border_width.min(width / 2).min(height / 2);
            let inner_width = width.saturating_sub(inset * 2);
            let inner_height = height.saturating_sub(inset * 2);
            fill_rounded_rect(
                layer,
                x + inset as i32,
                y + inset as i32,
                inner_width,
                inner_height,
                element.style.border_radius.saturating_sub(inset),
                apply_opacity(fill, opacity),
            );
            stroke_rounded_rect(
                layer,
                x,
                y,
                width,
                height,
                element.style.border_radius,
                element.style.border_width,
                apply_opacity(border, opacity),
            );
        }
    } else {
        let rect = Rect::at(x, y).of_size(width, height);
        if element.style.border_width > 0 {
            draw_filled_rect_mut(layer, rect, apply_opacity(border, opacity));
            let inset = element.style.border_width.min(width / 2).min(height / 2);
            if width > inset * 2 && height > inset * 2 {
                draw_filled_rect_mut(
                    layer,
                    Rect::at(x + inset as i32, y + inset as i32)
                        .of_size(width - inset * 2, height - inset * 2),
                    apply_opacity(fill, opacity),
                );
            }
        } else {
            draw_filled_rect_mut(layer, rect, apply_opacity(fill, opacity));
        }
    }
}

fn draw_brush_element(
    layer: &mut RgbaImage,
    element: &CanvasElement,
    opacity: f32,
    warnings: &mut Vec<RenderWarning>,
) {
    let Some(content) = element.static_content.as_deref() else {
        return;
    };
    let stroke_color = parse_color(&element.style.font_color, "brush stroke", warnings);
    let color = apply_opacity(stroke_color, opacity);
    let radius = (element.style.border_width / 2).max(1) as i32;

    let paths: Vec<Vec<(f32, f32)>> =
        if let Ok(multi) = serde_json::from_str::<Vec<Vec<[f32; 2]>>>(content) {
            multi
                .into_iter()
                .map(|p| p.into_iter().map(|pt| (pt[0], pt[1])).collect())
                .collect()
        } else if let Ok(parsed) = serde_json::from_str::<Vec<[f32; 2]>>(content) {
            vec![parsed.into_iter().map(|p| (p[0], p[1])).collect()]
        } else if let Ok(parsed) = serde_json::from_str::<Vec<serde_json::Value>>(content) {
            let single: Vec<(f32, f32)> = parsed
                .into_iter()
                .filter_map(|v| {
                    if let (Some(x), Some(y)) = (
                        v.get("x").and_then(|x| x.as_f64()),
                        v.get("y").and_then(|y| y.as_f64()),
                    ) {
                        Some((x as f32, y as f32))
                    } else {
                        None
                    }
                })
                .collect();
            if single.is_empty() {
                Vec::new()
            } else {
                vec![single]
            }
        } else {
            Vec::new()
        };

    if paths.is_empty() {
        return;
    }

    let img_w = layer.width() as i32;
    let img_h = layer.height() as i32;

    for points in &paths {
        for i in 0..points.len() {
            let (px, py) = points[i];
            let ix = px.round() as i32;
            let iy = py.round() as i32;
            if ix + radius >= 0 && ix - radius < img_w && iy + radius >= 0 && iy - radius < img_h {
                draw_filled_circle_mut(layer, (ix, iy), radius, color);
            }
            if i + 1 < points.len() {
                let (nx, ny) = points[i + 1];
                draw_line_segment_mut(layer, (px, py), (nx, ny), color);
            }
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn draw_text_element(
    layer: &mut RgbaImage,
    element: &CanvasElement,
    text: &str,
    x: i32,
    y: i32,
    width: u32,
    height: u32,
    opacity: f32,
    warnings: &mut Vec<RenderWarning>,
) {
    if text.is_empty() {
        return;
    }
    let Some(path) = resolve_system_font_path(
        &element.style.font_family,
        element.style.font_bold,
        element.style.font_italic,
    ) else {
        warnings.push(RenderWarning::MissingFont {
            family: element.style.font_family.clone(),
        });
        return;
    };
    let Ok(font_bytes) = fs::read(&path) else {
        warnings.push(RenderWarning::MissingFont {
            family: element.style.font_family.clone(),
        });
        return;
    };
    let Ok(font) = FontArc::try_from_vec(font_bytes) else {
        warnings.push(RenderWarning::MissingFont {
            family: element.style.font_family.clone(),
        });
        return;
    };

    let mut font_size = element.style.font_size.max(1) as f32;
    let min_size = element.style.min_font_size.max(1) as f32;
    let max_size = element.style.max_font_size.max(element.style.min_font_size) as f32;
    font_size = font_size.clamp(min_size, max_size);
    let mut lines = wrap_lines(
        text,
        &font,
        PxScale::from(font_size),
        width,
        element.style.wrap,
    );
    if matches!(
        element.style.overflow_policy,
        TextOverflowPolicy::AutoShrink
    ) {
        while (lines.len() as f32 * font_size * element.style.line_spacing) > height as f32
            && font_size > min_size
        {
            font_size = (font_size - 1.0).max(min_size);
            lines = wrap_lines(
                text,
                &font,
                PxScale::from(font_size),
                width,
                element.style.wrap,
            );
        }
    }
    let line_height = (font_size * element.style.line_spacing.max(0.5)).ceil() as i32;
    let total_height = line_height.saturating_mul(lines.len() as i32);
    let start_y = match element.style.vertical_align.to_ascii_lowercase().as_str() {
        "middle" | "center" => y + ((height as i32 - total_height) / 2).max(0),
        "bottom" | "end" => y + (height as i32 - total_height).max(0),
        _ => y,
    };
    let color = parse_color(&element.style.font_color, "font color", warnings);
    for (index, line) in lines.iter().enumerate() {
        let scale = PxScale::from(font_size);
        let (line_width, _) = text_size(scale, &font, line);
        let line_x = match element.style.text_align.to_ascii_lowercase().as_str() {
            "center" | "middle" => x + ((width as i32 - line_width as i32) / 2).max(0),
            "right" | "end" => x + (width as i32 - line_width as i32).max(0),
            _ => x,
        };
        if (line_x - x) as u32 > width || index as i32 * line_height >= height as i32 {
            warnings.push(RenderWarning::TextOverflow {
                element: element.name.clone(),
            });
            break;
        }
        draw_text_mut(
            layer,
            apply_opacity(color, opacity),
            line_x,
            start_y + index as i32 * line_height,
            scale,
            &font,
            line,
        );
    }
}

#[allow(clippy::too_many_arguments)]
fn draw_photo(
    layer: &mut RgbaImage,
    _template: &TemplateDefinition,
    element: &CanvasElement,
    record: Option<&SourceRecord>,
    photo_path: Option<&Path>,
    x: i32,
    y: i32,
    width: u32,
    height: u32,
    settings: Option<&RenderSettings>,
    warnings: &mut Vec<RenderWarning>,
) -> Result<(), RenderError> {
    let path = photo_path.filter(|path| path.exists());
    let image = match path {
        Some(path) => match load_image(path) {
            Ok(image) => image,
            Err(details) => {
                warnings.push(RenderWarning::CorruptPhoto {
                    path: path.display().to_string(),
                    details,
                });
                placeholder(width, height, record)
            }
        },
        None => {
            let pin = record
                .map(|record| record.pin.clone())
                .unwrap_or_else(|| "unknown".into());
            warnings.push(RenderWarning::MissingPhoto { pin: pin.clone() });
            if settings
                .map(|settings| settings.missing_photo_policy == MissingPhotoPolicy::FailRecord)
                .unwrap_or(false)
            {
                return Err(RenderError::MissingRequiredPhoto { pin });
            }
            placeholder(width, height, record)
        }
    };
    let fitted = fit_image(&image, width, height, &element.style.fit_mode);
    let fitted = apply_mask_and_opacity(
        fitted,
        &element.style.mask_shape,
        element.style.border_radius,
        element.style.opacity.clamp(0.0, 1.0),
    );
    imageops::overlay(layer, &fitted, x as i64, y as i64);
    draw_border(
        layer,
        element,
        x,
        y,
        width,
        height,
        element.style.opacity,
        warnings,
    );
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn draw_border(
    layer: &mut RgbaImage,
    element: &CanvasElement,
    x: i32,
    y: i32,
    width: u32,
    height: u32,
    opacity: f32,
    warnings: &mut Vec<RenderWarning>,
) {
    if element.style.border_width == 0 {
        return;
    }
    let color = parse_color(&element.style.border_color, "image border", warnings);
    let shape = element.style.mask_shape.to_ascii_lowercase();
    if shape == "circle" {
        stroke_ellipse(
            layer,
            x,
            y,
            width,
            height,
            element.style.border_width,
            apply_opacity(color, opacity),
        );
    } else if shape == "rounded" || element.style.border_radius > 0 {
        stroke_rounded_rect(
            layer,
            x,
            y,
            width,
            height,
            element.style.border_radius,
            element.style.border_width,
            apply_opacity(color, opacity),
        );
    } else {
        draw_hollow_rect_mut(
            layer,
            Rect::at(x, y).of_size(width, height),
            apply_opacity(color, opacity),
        );
    }
}

fn resolve_bound_text(element: &CanvasElement, record: Option<&SourceRecord>) -> String {
    let Some(record) = record else {
        return format!("[{}]", element.binding.as_deref().unwrap_or(&element.name));
    };
    if element.r#type == "pin_field"
        || element
            .binding
            .as_deref()
            .map(|binding| {
                matches!(
                    binding.to_ascii_lowercase().as_str(),
                    "pin" | "pin number" | "id"
                )
            })
            .unwrap_or(false)
    {
        return if record.pin.is_empty() {
            record.raw_pin.clone()
        } else {
            record.pin.clone()
        };
    }
    element
        .binding
        .as_deref()
        .map(|binding| record.get_value(binding))
        .filter(|value| !value.is_empty())
        .or_else(|| element.static_content.clone())
        .unwrap_or_default()
}

fn wrap_lines(text: &str, font: &FontArc, scale: PxScale, width: u32, wrap: bool) -> Vec<String> {
    let mut result = Vec::new();
    for paragraph in text.lines() {
        if !wrap {
            result.push(paragraph.to_owned());
            continue;
        }
        let mut line = String::new();
        for word in paragraph.split_whitespace() {
            let candidate = if line.is_empty() {
                word.to_owned()
            } else {
                format!("{line} {word}")
            };
            if !line.is_empty() && text_size(scale, font, &candidate).0 > width {
                result.push(line);
                line = word.to_owned();
            } else {
                line = candidate;
            }
        }
        result.push(line);
    }
    if result.is_empty() {
        result.push(String::new());
    }
    result
}

fn load_image(path: impl AsRef<Path>) -> Result<RgbaImage, String> {
    image::open(path.as_ref())
        .map(|image| image.to_rgba8())
        .map_err(|error| error.to_string())
}

fn fit_image(image: &RgbaImage, width: u32, height: u32, mode: &ImageFitMode) -> RgbaImage {
    if width == 0 || height == 0 || image.width() == 0 || image.height() == 0 {
        return RgbaImage::new(width, height);
    }
    match mode {
        ImageFitMode::Stretch => imageops::resize(image, width, height, FilterType::Lanczos3),
        ImageFitMode::Contain => {
            let scale =
                (width as f32 / image.width() as f32).min(height as f32 / image.height() as f32);
            let resized = imageops::resize(
                image,
                (image.width() as f32 * scale).round().max(1.0) as u32,
                (image.height() as f32 * scale).round().max(1.0) as u32,
                FilterType::Lanczos3,
            );
            let mut result = RgbaImage::new(width, height);
            imageops::overlay(
                &mut result,
                &resized,
                ((width - resized.width()) / 2) as i64,
                ((height - resized.height()) / 2) as i64,
            );
            result
        }
        ImageFitMode::Cover => {
            let scale =
                (width as f32 / image.width() as f32).max(height as f32 / image.height() as f32);
            let resized = imageops::resize(
                image,
                (image.width() as f32 * scale).round().max(width as f32) as u32,
                (image.height() as f32 * scale).round().max(height as f32) as u32,
                FilterType::Lanczos3,
            );
            let left = resized.width().saturating_sub(width) / 2;
            let top = resized.height().saturating_sub(height) / 2;
            imageops::crop_imm(&resized, left, top, width, height).to_image()
        }
        ImageFitMode::Crop => {
            let left = image.width().saturating_sub(width) / 2;
            let top = image.height().saturating_sub(height) / 2;
            let crop_width = width.min(image.width());
            let crop_height = height.min(image.height());
            let cropped = imageops::crop_imm(image, left, top, crop_width, crop_height).to_image();
            imageops::resize(&cropped, width, height, FilterType::Lanczos3)
        }
    }
}

fn apply_mask_and_opacity(
    mut image: RgbaImage,
    shape: &str,
    radius: u32,
    opacity: f32,
) -> RgbaImage {
    let shape = shape.to_ascii_lowercase();
    for y in 0..image.height() {
        for x in 0..image.width() {
            let inside = match shape.as_str() {
                "circle" => {
                    let dx = (x as f32 + 0.5) / image.width() as f32 - 0.5;
                    let dy = (y as f32 + 0.5) / image.height() as f32 - 0.5;
                    dx * dx + dy * dy <= 0.25
                }
                "rounded" => point_in_rounded(x, y, image.width(), image.height(), radius),
                _ => true,
            };
            let pixel = image.get_pixel_mut(x, y);
            pixel[3] = if inside {
                (pixel[3] as f32 * opacity) as u8
            } else {
                0
            };
        }
    }
    image
}

fn placeholder(width: u32, height: u32, record: Option<&SourceRecord>) -> RgbaImage {
    let mut image = RgbaImage::from_pixel(width, height, Rgba([226, 232, 240, 255]));
    let color = Rgba([100, 116, 139, 255]);
    let pin = record.map(|record| record.pin.as_str()).unwrap_or("?");
    let mark = pin.chars().next().unwrap_or('?') as u8;
    for y in height / 3..(height * 2 / 3).max(height / 3 + 1) {
        for x in width / 3..(width * 2 / 3).max(width / 3 + 1) {
            if (x + y + mark as u32) % 7 == 0 {
                image.put_pixel(
                    x.min(width.saturating_sub(1)),
                    y.min(height.saturating_sub(1)),
                    color,
                );
            }
        }
    }
    image
}

fn fill_rounded_rect(
    image: &mut RgbaImage,
    x: i32,
    y: i32,
    width: u32,
    height: u32,
    radius: u32,
    color: Rgba<u8>,
) {
    for py in 0..height {
        for px in 0..width {
            if point_in_rounded(px, py, width, height, radius) {
                let tx = x + px as i32;
                let ty = y + py as i32;
                if tx >= 0 && ty >= 0 && (tx as u32) < image.width() && (ty as u32) < image.height()
                {
                    image.put_pixel(tx as u32, ty as u32, color);
                }
            }
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn stroke_rounded_rect(
    image: &mut RgbaImage,
    x: i32,
    y: i32,
    width: u32,
    height: u32,
    radius: u32,
    border_width: u32,
    color: Rgba<u8>,
) {
    let outer_radius = radius.min(width.min(height) / 2);
    for py in 0..height {
        for px in 0..width {
            let outer = point_in_rounded(px, py, width, height, outer_radius);
            let inner_x = border_width.min(width / 2);
            let inner_y = border_width.min(height / 2);
            let inner = px >= inner_x
                && py >= inner_y
                && width > inner_x * 2
                && height > inner_y * 2
                && point_in_rounded(
                    px - inner_x,
                    py - inner_y,
                    width - inner_x * 2,
                    height - inner_y * 2,
                    outer_radius.saturating_sub(border_width),
                );
            if outer && !inner {
                let tx = x + px as i32;
                let ty = y + py as i32;
                if tx >= 0 && ty >= 0 && (tx as u32) < image.width() && (ty as u32) < image.height()
                {
                    image.put_pixel(tx as u32, ty as u32, color);
                }
            }
        }
    }
}

fn stroke_ellipse(
    image: &mut RgbaImage,
    x: i32,
    y: i32,
    width: u32,
    height: u32,
    border_width: u32,
    color: Rgba<u8>,
) {
    let outer_rx = width as f32 / 2.0;
    let outer_ry = height as f32 / 2.0;
    let inner_rx = (width.saturating_sub(border_width * 2)) as f32 / 2.0;
    let inner_ry = (height.saturating_sub(border_width * 2)) as f32 / 2.0;
    for py in 0..height {
        for px in 0..width {
            let ox = ((px as f32 + 0.5) - outer_rx) / outer_rx.max(1.0);
            let oy = ((py as f32 + 0.5) - outer_ry) / outer_ry.max(1.0);
            let ix = ((px as f32 + 0.5) - outer_rx) / inner_rx.max(1.0);
            let iy = ((py as f32 + 0.5) - outer_ry) / inner_ry.max(1.0);
            if ox * ox + oy * oy <= 1.0 && ix * ix + iy * iy > 1.0 {
                let tx = x + px as i32;
                let ty = y + py as i32;
                if tx >= 0 && ty >= 0 && (tx as u32) < image.width() && (ty as u32) < image.height()
                {
                    image.put_pixel(tx as u32, ty as u32, color);
                }
            }
        }
    }
}

fn point_in_rounded(x: u32, y: u32, width: u32, height: u32, radius: u32) -> bool {
    if radius == 0 {
        return true;
    }
    let radius = radius.min(width.min(height) / 2) as f32;
    let x = x as f32 + 0.5;
    let y = y as f32 + 0.5;
    let nearest_x = x.clamp(radius, width as f32 - radius);
    let nearest_y = y.clamp(radius, height as f32 - radius);
    let dx = x - nearest_x;
    let dy = y - nearest_y;
    dx * dx + dy * dy <= radius * radius
}

fn parse_color(value: &str, context: &str, warnings: &mut Vec<RenderWarning>) -> Rgba<u8> {
    let value = value.trim();
    if value.eq_ignore_ascii_case("transparent") || value.is_empty() {
        return Rgba([0, 0, 0, 0]);
    }
    let hex = value.strip_prefix('#').unwrap_or(value);
    let parsed = match hex.len() {
        3 => u32::from_str_radix(hex, 16).ok().map(|value| {
            Rgba([
                ((value >> 8) & 0xf) as u8 * 17,
                ((value >> 4) & 0xf) as u8 * 17,
                (value & 0xf) as u8 * 17,
                255,
            ])
        }),
        6 => u32::from_str_radix(hex, 16)
            .ok()
            .map(|value| Rgba([(value >> 16) as u8, (value >> 8) as u8, value as u8, 255])),
        8 => u32::from_str_radix(hex, 16).ok().map(|value| {
            Rgba([
                (value >> 24) as u8,
                (value >> 16) as u8,
                (value >> 8) as u8,
                value as u8,
            ])
        }),
        _ => match value.to_ascii_lowercase().as_str() {
            "black" => Some(Rgba([0, 0, 0, 255])),
            "white" => Some(Rgba([255, 255, 255, 255])),
            "red" => Some(Rgba([255, 0, 0, 255])),
            "green" => Some(Rgba([0, 128, 0, 255])),
            "blue" => Some(Rgba([0, 0, 255, 255])),
            _ => None,
        },
    };
    parsed.unwrap_or_else(|| {
        warnings.push(RenderWarning::InvalidColor {
            context: context.into(),
            value: value.into(),
        });
        Rgba([0, 0, 0, 0])
    })
}

fn apply_opacity(mut color: Rgba<u8>, opacity: f32) -> Rgba<u8> {
    color[3] = (color[3] as f32 * opacity.clamp(0.0, 1.0)) as u8;
    color
}

fn encode_png<W: Write>(rendered: &RenderedImage, dpi: u32, writer: W) -> Result<(), RenderError> {
    let mut encoder = png::Encoder::new(writer, rendered.image.width(), rendered.image.height());
    encoder.set_color(png::ColorType::Rgba);
    encoder.set_depth(png::BitDepth::Eight);
    let pixels_per_meter = ((dpi as f64 * 39.37007874015748).round() as u32).max(1);
    encoder.set_pixel_dims(Some(png::PixelDimensions {
        xppu: pixels_per_meter,
        yppu: pixels_per_meter,
        unit: png::Unit::Meter,
    }));
    let mut output = encoder
        .write_header()
        .map_err(|error| RenderError::Encode {
            format: "PNG".into(),
            details: error.to_string(),
        })?;
    output
        .write_image_data(rendered.image.as_raw())
        .map_err(|error| RenderError::Encode {
            format: "PNG".into(),
            details: error.to_string(),
        })
}

fn encode_jpeg<W: Write>(
    rendered: &RenderedImage,
    template: &TemplateDefinition,
    quality: u8,
    writer: W,
) -> Result<(), RenderError> {
    let background = {
        let mut warnings = Vec::new();
        parse_color(&template.background_color, "JPEG background", &mut warnings)
    };
    let mut rgb =
        Vec::with_capacity((rendered.image.width() * rendered.image.height() * 3) as usize);
    for pixel in rendered.image.pixels() {
        let alpha = pixel[3] as u16;
        rgb.push(((pixel[0] as u16 * alpha + background[0] as u16 * (255 - alpha)) / 255) as u8);
        rgb.push(((pixel[1] as u16 * alpha + background[1] as u16 * (255 - alpha)) / 255) as u8);
        rgb.push(((pixel[2] as u16 * alpha + background[2] as u16 * (255 - alpha)) / 255) as u8);
    }
    let mut encoder = JpegEncoder::new_with_quality(writer, quality.clamp(1, 100));
    encoder.set_pixel_density(PixelDensity::dpi(template.dpi.min(u16::MAX as u32) as u16));
    encoder
        .encode(
            &rgb,
            rendered.image.width(),
            rendered.image.height(),
            ExtendedColorType::Rgb8,
        )
        .map_err(|error| RenderError::Encode {
            format: "JPEG".into(),
            details: error.to_string(),
        })
}

fn resolve_system_font_path(font_family: &str, _bold: bool, _italic: bool) -> Option<PathBuf> {
    let requested = Path::new(font_family);
    if requested.is_file() {
        return Some(requested.to_path_buf());
    }
    let family = font_family.to_ascii_lowercase();
    let mut candidates = Vec::new();
    #[cfg(target_os = "windows")]
    {
        let windows = std::env::var_os("WINDIR")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(r"C:\Windows"));
        let names = if family.contains("segoe") {
            match (_bold, _italic) {
                (true, true) => vec!["segoeuiz.ttf".to_owned()],
                (true, false) => vec!["segoeuib.ttf".to_owned()],
                (false, true) => vec!["segoeuii.ttf".to_owned()],
                (false, false) => vec!["segoeui.ttf".to_owned()],
            }
        } else if family.contains("calibri") {
            match (_bold, _italic) {
                (true, true) => vec!["calibriz.ttf".to_owned()],
                (true, false) => vec!["calibrib.ttf".to_owned()],
                (false, true) => vec!["calibrii.ttf".to_owned()],
                (false, false) => vec!["calibri.ttf".to_owned()],
            }
        } else {
            match (_bold, _italic) {
                (true, true) => vec!["arialbi.ttf".to_owned(), "segoeuiz.ttf".to_owned()],
                (true, false) => vec!["arialbd.ttf".to_owned(), "segoeuib.ttf".to_owned()],
                (false, true) => vec!["ariali.ttf".to_owned(), "segoeuii.ttf".to_owned()],
                (false, false) => vec!["arial.ttf".to_owned(), "segoeui.ttf".to_owned()],
            }
        };
        candidates.extend(
            names
                .into_iter()
                .map(|name| windows.join("Fonts").join(name)),
        );
    }
    #[cfg(target_os = "macos")]
    {
        let name = if family.contains("helvetica") {
            "Helvetica"
        } else if family.contains("arial") {
            "Arial"
        } else {
            "SFNS"
        };
        candidates.push(PathBuf::from(format!(
            "/System/Library/Fonts/Supplemental/{name}.ttf"
        )));
        candidates.push(PathBuf::from(format!("/Library/Fonts/{name}.ttf")));
        candidates.push(PathBuf::from("/System/Library/Fonts/SFNS.ttf"));
    }
    #[cfg(target_os = "linux")]
    {
        let style = match (_bold, _italic) {
            (true, true) => "BoldItalic",
            (true, false) => "Bold",
            (false, true) => "Italic",
            (false, false) => "Regular",
        };
        let family_name = if family.contains("liberation") || family.contains("arial") {
            "LiberationSans"
        } else {
            "DejaVuSans"
        };
        let linux_style = if family_name == "DejaVuSans" && style == "Italic" {
            "Oblique"
        } else if family_name == "DejaVuSans" && style == "BoldItalic" {
            "BoldOblique"
        } else {
            style
        };
        let file_name = format!("{family_name}-{linux_style}.ttf");
        candidates.extend([
            PathBuf::from(format!("/usr/share/fonts/truetype/dejavu/{file_name}")),
            PathBuf::from(format!("/usr/share/fonts/truetype/liberation2/{file_name}")),
            PathBuf::from(format!("/usr/local/share/fonts/{file_name}")),
        ]);
        if let Some(home) = std::env::var_os("HOME") {
            candidates.push(PathBuf::from(home).join(".fonts").join(file_name));
        }
    }
    candidates.into_iter().find(|candidate| candidate.is_file())
}
