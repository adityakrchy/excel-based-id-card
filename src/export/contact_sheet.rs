//! Printable multi-card contact sheet generation.
//!
//! Arranges exported or rendered ID cards in a printable grid layout (e.g. A4 or
//! US Letter at 300 DPI) with headers, pagination, card borders, cut/trim guides,
//! and labels.

use std::{
    fs::{self, File},
    io::BufWriter,
    path::{Path, PathBuf},
};

use ab_glyph::{FontArc, PxScale};
use image::{imageops, GenericImageView, ImageFormat, Rgba, RgbaImage};
use imageproc::drawing::{draw_hollow_rect_mut, draw_line_segment_mut, draw_text_mut, text_size};
use imageproc::rect::Rect;
use thiserror::Error;

use crate::rendering::NativeRenderer;

#[derive(Debug, Error)]
pub enum ContactSheetError {
    #[error("no cards provided for contact sheet")]
    EmptyCards,
    #[error("failed to create output directory {path}: {source}")]
    CreateDir {
        path: PathBuf,
        source: std::io::Error,
    },
    #[error("failed to save contact sheet image to {path}: {source}")]
    SaveImage {
        path: PathBuf,
        source: image::ImageError,
    },
    #[error("grid configuration must have at least 1 column and 1 row")]
    InvalidGrid,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PageSize {
    A4,
    Letter,
    Custom { width_px: u32, height_px: u32 },
}

impl PageSize {
    pub fn dimensions_px(self, dpi: u32) -> (u32, u32) {
        let dpi_f = dpi as f64;
        match self {
            Self::A4 => {
                let w = (210.0 / 25.4 * dpi_f).round() as u32;
                let h = (297.0 / 25.4 * dpi_f).round() as u32;
                (w, h)
            }
            Self::Letter => {
                let w = (8.5 * dpi_f).round() as u32;
                let h = (11.0 * dpi_f).round() as u32;
                (w, h)
            }
            Self::Custom {
                width_px,
                height_px,
            } => (width_px.max(100), height_px.max(100)),
        }
    }
}

#[derive(Debug, Clone)]
pub struct ContactSheetOptions {
    pub page_size: PageSize,
    pub dpi: u32,
    pub columns: u32,
    pub rows: u32,
    pub margin_px: u32,
    pub spacing_px: u32,
    pub title: String,
    pub draw_cut_marks: bool,
    pub draw_card_borders: bool,
    pub draw_labels: bool,
}

impl Default for ContactSheetOptions {
    fn default() -> Self {
        Self {
            page_size: PageSize::A4,
            dpi: 300,
            columns: 2,
            rows: 3,
            margin_px: 120,
            spacing_px: 60,
            title: "ID Cards — Contact Sheet".to_owned(),
            draw_cut_marks: true,
            draw_card_borders: true,
            draw_labels: true,
        }
    }
}

#[derive(Debug, Clone)]
pub struct ContactSheetCardItem {
    pub image_path: PathBuf,
    pub pin: String,
    pub name: String,
}

pub struct ContactSheetGenerator;

impl ContactSheetGenerator {
    /// Generate printable contact sheet PNG pages and save them to `output_dir`.
    /// Returns the list of generated page file paths.
    pub fn generate_sheets(
        cards: &[ContactSheetCardItem],
        output_dir: &Path,
        options: &ContactSheetOptions,
    ) -> Result<Vec<PathBuf>, ContactSheetError> {
        if cards.is_empty() {
            return Err(ContactSheetError::EmptyCards);
        }
        if options.columns == 0 || options.rows == 0 {
            return Err(ContactSheetError::InvalidGrid);
        }

        fs::create_dir_all(output_dir).map_err(|source| ContactSheetError::CreateDir {
            path: output_dir.to_path_buf(),
            source,
        })?;

        let (page_w, page_h) = options.page_size.dimensions_px(options.dpi);
        let per_page = (options.columns * options.rows) as usize;
        let total_pages = cards.len().div_ceil(per_page);

        let font = load_font();
        let mut generated_paths = Vec::new();

        for (page_idx, chunk) in cards.chunks(per_page).enumerate() {
            let page_num = page_idx + 1;
            let mut page = RgbaImage::from_pixel(page_w, page_h, Rgba([255, 255, 255, 255]));

            // Draw header
            let header_bottom = draw_page_header(
                &mut page,
                page_w,
                options,
                page_num,
                total_pages,
                font.as_ref(),
            );

            // Compute grid layout
            let grid_top = header_bottom + options.spacing_px;
            let grid_bottom = page_h.saturating_sub(options.margin_px);
            let grid_left = options.margin_px;
            let grid_right = page_w.saturating_sub(options.margin_px);

            let available_w = grid_right.saturating_sub(grid_left);
            let available_h = grid_bottom.saturating_sub(grid_top);

            let total_col_spacing = (options.columns - 1) * options.spacing_px;
            let total_row_spacing = (options.rows - 1) * options.spacing_px;

            let cell_w = (available_w.saturating_sub(total_col_spacing)) / options.columns;
            let cell_h = (available_h.saturating_sub(total_row_spacing)) / options.rows;

            let label_h = if options.draw_labels {
                (36.0 * (options.dpi as f32 / 300.0)).round() as u32
            } else {
                0
            };

            for (card_idx, card) in chunk.iter().enumerate() {
                let col = (card_idx as u32) % options.columns;
                let row = (card_idx as u32) / options.columns;

                let cell_x = grid_left + col * (cell_w + options.spacing_px);
                let cell_y = grid_top + row * (cell_h + options.spacing_px);

                let card_area_h = cell_h.saturating_sub(label_h);

                // Load card image
                if let Ok(card_img) = image::open(&card.image_path) {
                    let (img_w, img_h) = card_img.dimensions();
                    if img_w > 0 && img_h > 0 {
                        // Fit inside card_area preserving aspect ratio
                        let scale_w = cell_w as f32 / img_w as f32;
                        let scale_h = card_area_h as f32 / img_h as f32;
                        let scale = scale_w.min(scale_h);

                        let target_w = (img_w as f32 * scale).round().max(1.0) as u32;
                        let target_h = (img_h as f32 * scale).round().max(1.0) as u32;

                        let card_x = cell_x + (cell_w.saturating_sub(target_w)) / 2;
                        let card_y = cell_y + (card_area_h.saturating_sub(target_h)) / 2;

                        let resized = imageops::resize(
                            &card_img.to_rgba8(),
                            target_w,
                            target_h,
                            imageops::FilterType::Lanczos3,
                        );

                        imageops::overlay(
                            &mut page,
                            &resized,
                            i64::from(card_x),
                            i64::from(card_y),
                        );

                        // Card border
                        if options.draw_card_borders {
                            draw_hollow_rect_mut(
                                &mut page,
                                Rect::at(card_x as i32, card_y as i32).of_size(target_w, target_h),
                                Rgba([203, 213, 225, 255]),
                            );
                        }

                        // Cut marks
                        if options.draw_cut_marks {
                            draw_cut_marks_around(
                                &mut page,
                                card_x,
                                card_y,
                                target_w,
                                target_h,
                                options.dpi,
                            );
                        }

                        // Label
                        if options.draw_labels {
                            let label_text = format!("PIN: {} · {}", card.pin, card.name);
                            let label_y = cell_y + card_area_h + 8;
                            draw_card_label(
                                &mut page,
                                cell_x,
                                cell_w,
                                label_y,
                                &label_text,
                                font.as_ref(),
                                options.dpi,
                            );
                        }
                    }
                } else {
                    // Placeholder box when image fails to load
                    draw_hollow_rect_mut(
                        &mut page,
                        Rect::at(cell_x as i32, cell_y as i32).of_size(cell_w, card_area_h),
                        Rgba([239, 68, 68, 255]),
                    );
                    if options.draw_labels {
                        let label_text = format!("PIN: {} · (Missing Image)", card.pin);
                        let label_y = cell_y + card_area_h + 8;
                        draw_card_label(
                            &mut page,
                            cell_x,
                            cell_w,
                            label_y,
                            &label_text,
                            font.as_ref(),
                            options.dpi,
                        );
                    }
                }
            }

            let file_name = if total_pages == 1 {
                "contact_sheet.png".to_owned()
            } else {
                format!("contact_sheet_page_{page_num}.png")
            };
            let page_path = output_dir.join(file_name);

            let file = File::create(&page_path).map_err(|source| ContactSheetError::SaveImage {
                path: page_path.clone(),
                source: image::ImageError::IoError(source),
            })?;
            let mut writer = BufWriter::new(file);
            page.write_to(&mut writer, ImageFormat::Png)
                .map_err(|source| ContactSheetError::SaveImage {
                    path: page_path.clone(),
                    source,
                })?;

            generated_paths.push(page_path);
        }

        Ok(generated_paths)
    }
}

fn load_font() -> Option<FontArc> {
    let font_path = NativeRenderer::resolve_system_font_path("Segoe UI", true, false)
        .or_else(|| NativeRenderer::resolve_system_font_path("Arial", true, false))
        .or_else(|| NativeRenderer::resolve_system_font_path("Helvetica", true, false))?;
    let bytes = fs::read(font_path).ok()?;
    FontArc::try_from_vec(bytes).ok()
}

fn draw_page_header(
    page: &mut RgbaImage,
    page_w: u32,
    options: &ContactSheetOptions,
    page_num: usize,
    total_pages: usize,
    font: Option<&FontArc>,
) -> u32 {
    let header_y = options.margin_px;
    let dpi_ratio = options.dpi as f32 / 300.0;
    let title_size = (36.0 * dpi_ratio).max(14.0);
    let page_text_size = (22.0 * dpi_ratio).max(10.0);

    let title_color = Rgba([30, 41, 59, 255]);
    let meta_color = Rgba([100, 116, 139, 255]);
    let divider_color = Rgba([226, 232, 240, 255]);

    if let Some(font) = font {
        draw_text_mut(
            page,
            title_color,
            options.margin_px as i32,
            header_y as i32,
            PxScale::from(title_size),
            font,
            &options.title,
        );

        let page_text = format!("Page {page_num} of {total_pages}");
        let (pt_w, _) = text_size(PxScale::from(page_text_size), font, &page_text);
        let pt_x = (page_w - options.margin_px).saturating_sub(pt_w);
        draw_text_mut(
            page,
            meta_color,
            pt_x as i32,
            (header_y + (title_size - page_text_size) as u32) as i32,
            PxScale::from(page_text_size),
            font,
            &page_text,
        );
    }

    let divider_y = header_y + (title_size as u32) + (16.0 * dpi_ratio).round() as u32;
    draw_line_segment_mut(
        page,
        (options.margin_px as f32, divider_y as f32),
        ((page_w - options.margin_px) as f32, divider_y as f32),
        divider_color,
    );

    divider_y
}

fn draw_cut_marks_around(page: &mut RgbaImage, x: u32, y: u32, width: u32, height: u32, dpi: u32) {
    let mark_len = (18.0 * (dpi as f32 / 300.0)).max(6.0);
    let mark_color = Rgba([148, 163, 184, 255]);

    let x0 = x as f32;
    let y0 = y as f32;
    let x1 = (x + width) as f32;
    let y1 = (y + height) as f32;

    // Top-left
    draw_line_segment_mut(page, (x0 - mark_len, y0), (x0, y0), mark_color);
    draw_line_segment_mut(page, (x0, y0 - mark_len), (x0, y0), mark_color);

    // Top-right
    draw_line_segment_mut(page, (x1, y0), (x1 + mark_len, y0), mark_color);
    draw_line_segment_mut(page, (x1, y0 - mark_len), (x1, y0), mark_color);

    // Bottom-left
    draw_line_segment_mut(page, (x0 - mark_len, y1), (x0, y1), mark_color);
    draw_line_segment_mut(page, (x0, y1), (x0, y1 + mark_len), mark_color);

    // Bottom-right
    draw_line_segment_mut(page, (x1, y1), (x1 + mark_len, y1), mark_color);
    draw_line_segment_mut(page, (x1, y1), (x1, y1 + mark_len), mark_color);
}

fn draw_card_label(
    page: &mut RgbaImage,
    cell_x: u32,
    cell_w: u32,
    y: u32,
    text: &str,
    font: Option<&FontArc>,
    dpi: u32,
) {
    let font_size = (20.0 * (dpi as f32 / 300.0)).max(9.0);
    let color = Rgba([51, 65, 85, 255]);

    if let Some(font) = font {
        let (txt_w, _) = text_size(PxScale::from(font_size), font, text);
        let txt_x = if txt_w < cell_w {
            cell_x + (cell_w - txt_w) / 2
        } else {
            cell_x
        };
        draw_text_mut(
            page,
            color,
            txt_x as i32,
            y as i32,
            PxScale::from(font_size),
            font,
            text,
        );
    }
}
