//! Filename-only photo indexing. No image bytes are decoded here.

use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
};

use walkdir::WalkDir;

const IMAGE_EXTENSIONS: &[&str] = &["jpg", "jpeg", "png", "bmp", "webp", "tiff", "tif"];

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct PhotoIndex {
    pub exact: BTreeMap<String, Vec<PathBuf>>,
    pub lower: BTreeMap<String, Vec<PathBuf>>,
}

impl PhotoIndex {
    pub fn insert(&mut self, stem: String, path: PathBuf) {
        self.exact
            .entry(stem.clone())
            .or_default()
            .push(path.clone());
        self.lower
            .entry(stem.to_ascii_lowercase())
            .or_default()
            .push(path);
    }

    pub fn total_files(&self) -> usize {
        self.exact.values().map(Vec::len).sum()
    }
}

pub fn normalize_key(value: &str) -> String {
    let trimmed = value.trim();
    if trimmed.ends_with(".0") && trimmed[..trimmed.len() - 2].parse::<i64>().is_ok() {
        trimmed[..trimmed.len() - 2].to_owned()
    } else {
        trimmed.to_owned()
    }
}

pub fn image_stem(path: &Path) -> Option<String> {
    let extension = path.extension()?.to_string_lossy().to_ascii_lowercase();
    if !IMAGE_EXTENSIONS.contains(&extension.as_str()) {
        return None;
    }
    let stem = path.file_stem()?.to_string_lossy();
    let stem = normalize_key(&stem);
    (!stem.is_empty()).then_some(stem)
}

pub fn scan_directory(root: &Path) -> PhotoIndex {
    let mut index = PhotoIndex::default();
    if !root.is_dir() {
        return index;
    }
    for entry in WalkDir::new(root)
        .follow_links(false)
        .into_iter()
        .filter_map(Result::ok)
    {
        if entry.file_type().is_file() {
            if let Some(stem) = image_stem(entry.path()) {
                index.insert(stem, entry.path().to_path_buf());
            }
        }
    }
    index
}
