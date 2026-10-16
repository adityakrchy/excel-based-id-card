//! Canonical physical geometry and DPI conversion.

use serde::{Deserialize, Serialize};
use thiserror::Error;

pub const MM_PER_INCH: f64 = 25.4;
pub const CR80_WIDTH_MM: f64 = 85.6;
pub const CR80_HEIGHT_MM: f64 = 54.0;
pub const DEFAULT_DPI: u32 = 300;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum Unit {
    #[serde(rename = "mm")]
    Mm,
    #[serde(rename = "cm")]
    Cm,
    #[serde(rename = "inch")]
    Inch,
    #[serde(rename = "px")]
    Pixels,
}

#[derive(Debug, Error, PartialEq)]
pub enum GeometryError {
    #[error("measurement values must be finite and non-negative")]
    InvalidValue,
    #[error("DPI must be greater than zero")]
    InvalidDpi,
    #[error("unsupported measurement unit: {0}")]
    UnsupportedUnit(String),
}

impl Unit {
    pub fn parse(value: &str) -> Result<Self, GeometryError> {
        match value.trim().to_ascii_lowercase().as_str() {
            "mm" | "millimeter" | "millimeters" => Ok(Self::Mm),
            "cm" | "centimeter" | "centimeters" => Ok(Self::Cm),
            "in" | "inch" | "inches" => Ok(Self::Inch),
            "px" | "pixel" | "pixels" => Ok(Self::Pixels),
            _ => Err(GeometryError::UnsupportedUnit(value.to_owned())),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CardDimensions {
    pub width_px: u32,
    pub height_px: u32,
    pub width_mm: f64,
    pub height_mm: f64,
}

fn validate(value: f64, dpi: u32) -> Result<(), GeometryError> {
    if !value.is_finite() || value < 0.0 {
        return Err(GeometryError::InvalidValue);
    }
    if dpi == 0 {
        return Err(GeometryError::InvalidDpi);
    }
    Ok(())
}

pub fn to_inches(value: f64, unit: Unit, dpi: u32) -> Result<f64, GeometryError> {
    validate(value, dpi)?;
    Ok(match unit {
        Unit::Mm => value / MM_PER_INCH,
        Unit::Cm => value / 2.54,
        Unit::Inch => value,
        Unit::Pixels => value / f64::from(dpi),
    })
}

pub fn from_inches(inches: f64, unit: Unit, dpi: u32) -> Result<f64, GeometryError> {
    validate(inches, dpi)?;
    Ok(match unit {
        Unit::Mm => inches * MM_PER_INCH,
        Unit::Cm => inches * 2.54,
        Unit::Inch => inches,
        Unit::Pixels => inches * f64::from(dpi),
    })
}

pub fn convert_unit(value: f64, from: Unit, to: Unit, dpi: u32) -> Result<f64, GeometryError> {
    if from == to {
        validate(value, dpi)?;
        return Ok(value);
    }
    from_inches(to_inches(value, from, dpi)?, to, dpi)
}

pub fn physical_to_pixels(value: f64, unit: Unit, dpi: u32) -> Result<u32, GeometryError> {
    let pixels = from_inches(to_inches(value, unit, dpi)?, Unit::Pixels, dpi)?;
    Ok(pixels.round().max(1.0) as u32)
}

pub fn pixels_to_physical(pixels: u32, dpi: u32, target: Unit) -> Result<f64, GeometryError> {
    from_inches(
        to_inches(f64::from(pixels), Unit::Pixels, dpi)?,
        target,
        dpi,
    )
}

pub fn calculate_card_dimensions(
    width: f64,
    height: f64,
    unit: Unit,
    dpi: u32,
    orientation: &str,
) -> Result<CardDimensions, GeometryError> {
    let mut width_inches = to_inches(width, unit, dpi)?;
    let mut height_inches = to_inches(height, unit, dpi)?;

    match orientation.to_ascii_lowercase().as_str() {
        "portrait" if width_inches > height_inches => {
            std::mem::swap(&mut width_inches, &mut height_inches)
        }
        "landscape" if height_inches > width_inches => {
            std::mem::swap(&mut width_inches, &mut height_inches)
        }
        _ => {}
    }

    Ok(CardDimensions {
        width_px: physical_to_pixels(width_inches, Unit::Inch, dpi)?,
        height_px: physical_to_pixels(height_inches, Unit::Inch, dpi)?,
        width_mm: (width_inches * MM_PER_INCH * 100.0).round() / 100.0,
        height_mm: (height_inches * MM_PER_INCH * 100.0).round() / 100.0,
    })
}

pub fn cr80_dimensions(dpi: u32, orientation: &str) -> Result<CardDimensions, GeometryError> {
    calculate_card_dimensions(CR80_WIDTH_MM, CR80_HEIGHT_MM, Unit::Mm, dpi, orientation)
}
