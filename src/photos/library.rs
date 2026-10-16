//! Persistent, metadata-only photo library indexing.
//!
//! Indexing never opens image bytes.  Image decoding lives in the thumbnail
//! task module and is only performed when a thumbnail is explicitly requested.

use std::{
    collections::BTreeMap,
    fs, io,
    path::{Path, PathBuf},
    time::UNIX_EPOCH,
};

use serde::{Deserialize, Serialize};
use walkdir::WalkDir;

use super::scanner::{image_stem, PhotoIndex};

pub const PHOTO_INDEX_VERSION: u32 = 1;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PhotoMetadata {
    /// A deterministic identifier based on the canonical absolute path.
    pub id: String,
    pub path: PathBuf,
    /// The filename stem before match-key normalization.
    pub stem: String,
    /// Lowercase extension without the leading dot.
    pub extension: String,
    pub size: u64,
    /// Modification time in nanoseconds since the Unix epoch.
    pub modified_time: u64,
    /// The normalized key used by the existing filename matcher.
    pub match_key: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PersistedPhotoIndex {
    pub version: u32,
    pub root_directory: PathBuf,
    pub photos: Vec<PhotoMetadata>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RescanReport {
    pub added: Vec<PhotoMetadata>,
    pub modified: Vec<PhotoMetadata>,
    pub removed: Vec<PhotoMetadata>,
}

impl RescanReport {
    pub fn is_empty(&self) -> bool {
        self.added.is_empty() && self.modified.is_empty() && self.removed.is_empty()
    }

    pub fn changed_count(&self) -> usize {
        self.added.len() + self.modified.len() + self.removed.len()
    }
}

#[derive(Debug, thiserror::Error)]
pub enum PhotoLibraryError {
    #[error("photo library I/O failed: {0}")]
    Io(#[from] io::Error),
    #[error("photo library JSON is invalid: {0}")]
    Json(#[from] serde_json::Error),
    #[error("unsupported photo index version {0}")]
    UnsupportedVersion(u32),
    #[error("photo index root {actual:?} does not match requested root {expected:?}")]
    RootMismatch { expected: PathBuf, actual: PathBuf },
}

#[derive(Debug, Clone)]
pub struct PhotoLibrary {
    root_directory: PathBuf,
    records: BTreeMap<String, PhotoMetadata>,
    invalidated_records: Vec<PhotoMetadata>,
}

impl PhotoLibrary {
    pub fn new(root: impl AsRef<Path>) -> Self {
        Self {
            root_directory: stable_root(root.as_ref()),
            records: BTreeMap::new(),
            invalidated_records: Vec::new(),
        }
    }

    pub fn root_directory(&self) -> &Path {
        &self.root_directory
    }

    pub fn records(&self) -> impl Iterator<Item = &PhotoMetadata> {
        self.records.values()
    }

    pub fn record_count(&self) -> usize {
        self.records.len()
    }

    pub fn invalidated_records(&self) -> &[PhotoMetadata] {
        &self.invalidated_records
    }

    /// Load an index and retain only records whose on-disk metadata still
    /// validates.  Stale, missing, or replaced files are deliberately omitted
    /// until the next rescan reports them as changes.
    pub fn load(path: impl AsRef<Path>) -> Result<Self, PhotoLibraryError> {
        let document: PersistedPhotoIndex = serde_json::from_slice(&fs::read(path)?)?;
        Self::from_document(document, None)
    }

    pub fn load_for_root(
        path: impl AsRef<Path>,
        root: impl AsRef<Path>,
    ) -> Result<Self, PhotoLibraryError> {
        let expected = stable_root(root.as_ref());
        let document: PersistedPhotoIndex = serde_json::from_slice(&fs::read(path)?)?;
        Self::from_document(document, Some(expected))
    }

    pub fn save(&self, path: impl AsRef<Path>) -> Result<(), PhotoLibraryError> {
        let path = path.as_ref();
        let document = PersistedPhotoIndex {
            version: PHOTO_INDEX_VERSION,
            root_directory: self.root_directory.clone(),
            photos: self.records.values().cloned().collect(),
        };
        let bytes = serde_json::to_vec_pretty(&document)?;
        let temporary = path.with_extension(format!(
            "{}.tmp",
            path.extension()
                .and_then(|extension| extension.to_str())
                .unwrap_or("json")
        ));
        fs::write(&temporary, bytes)?;
        fs::rename(temporary, path)?;
        Ok(())
    }

    /// Scan the directory and update only changed records.  The scan reads
    /// filesystem metadata and filenames, never image contents.
    pub fn rescan(&mut self) -> Result<RescanReport, PhotoLibraryError> {
        let mut current = BTreeMap::new();
        if self.root_directory.is_dir() {
            for entry in WalkDir::new(&self.root_directory)
                .follow_links(false)
                .into_iter()
                .filter_map(Result::ok)
            {
                if !entry.file_type().is_file() {
                    continue;
                }
                let Some(record) = metadata_for_path(entry.path()) else {
                    continue;
                };
                current.insert(record.id.clone(), record);
            }
        }

        let mut report = RescanReport {
            added: Vec::new(),
            modified: Vec::new(),
            removed: Vec::new(),
        };
        for (id, record) in &current {
            match self.records.get(id) {
                None => report.added.push(record.clone()),
                Some(previous) if previous != record => report.modified.push(record.clone()),
                Some(_) => {}
            }
        }
        for (id, record) in &self.records {
            if !current.contains_key(id) {
                report.removed.push(record.clone());
            }
        }
        self.records = current;
        Ok(report)
    }

    /// Adapt the metadata records to the filename-only matcher used by the
    /// earlier photo API.
    pub fn photo_index(&self) -> PhotoIndex {
        let mut index = PhotoIndex::default();
        for record in self.records.values() {
            index.insert(record.match_key.clone(), record.path.clone());
        }
        index
    }

    fn from_document(
        document: PersistedPhotoIndex,
        expected_root: Option<PathBuf>,
    ) -> Result<Self, PhotoLibraryError> {
        if document.version != PHOTO_INDEX_VERSION {
            return Err(PhotoLibraryError::UnsupportedVersion(document.version));
        }
        let actual_root = stable_root(&document.root_directory);
        if let Some(expected) = expected_root {
            if expected != actual_root {
                return Err(PhotoLibraryError::RootMismatch {
                    expected,
                    actual: actual_root,
                });
            }
        }
        let mut library = Self {
            root_directory: actual_root,
            records: BTreeMap::new(),
            invalidated_records: Vec::new(),
        };
        for record in document.photos {
            if record.id == stable_id(&record.path)
                && record.path.starts_with(&library.root_directory)
                && metadata_for_path(&record.path).as_ref() == Some(&record)
            {
                library.records.insert(record.id.clone(), record);
            } else {
                library.invalidated_records.push(record);
            }
        }
        Ok(library)
    }
}

fn stable_root(path: &Path) -> PathBuf {
    fs::canonicalize(path).unwrap_or_else(|_| {
        if path.is_absolute() {
            path.to_path_buf()
        } else {
            std::env::current_dir()
                .unwrap_or_else(|_| PathBuf::from("."))
                .join(path)
        }
    })
}

fn stable_id(path: &Path) -> String {
    stable_root(path).to_string_lossy().into_owned()
}

fn metadata_for_path(path: &Path) -> Option<PhotoMetadata> {
    let match_key = image_stem(path)?;
    let metadata = fs::metadata(path).ok()?;
    let stem = path.file_stem()?.to_string_lossy().into_owned();
    let extension = path.extension()?.to_string_lossy().to_ascii_lowercase();
    let modified_time = metadata
        .modified()
        .ok()?
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos()
        .min(u64::MAX as u128) as u64;
    let path = stable_root(path);
    Some(PhotoMetadata {
        id: stable_id(&path),
        path,
        stem,
        extension,
        size: metadata.len(),
        modified_time,
        match_key,
    })
}

#[cfg(test)]
mod tests {
    use super::stable_id;
    use std::path::Path;

    #[test]
    fn stable_id_is_path_based() {
        assert_eq!(
            stable_id(Path::new("photo.jpg")),
            stable_id(Path::new("photo.jpg"))
        );
    }
}
