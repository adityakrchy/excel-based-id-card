//! Versioned JSON project/template persistence with recovery and reference checks.

use std::{
    collections::BTreeMap,
    fs,
    io::Write,
    path::{Component, Path, PathBuf},
};

use serde::{de::DeserializeOwned, Serialize};
use thiserror::Error;
use uuid::Uuid;

use crate::data::models::{ProjectConfiguration, TemplateDefinition, CURRENT_FORMAT_VERSION};

#[derive(Debug, Error)]
pub enum PersistenceError {
    #[error("path does not exist: {0}")]
    MissingPath(PathBuf),
    #[error("could not read {path}: {source}")]
    Read {
        path: PathBuf,
        source: std::io::Error,
    },
    #[error("could not write {path}: {source}")]
    Write {
        path: PathBuf,
        source: std::io::Error,
    },
    #[error("invalid JSON in {path}: {source}")]
    Json {
        path: PathBuf,
        source: serde_json::Error,
    },
    #[error("unsupported or missing version in {path}: {version}")]
    Version { path: PathBuf, version: String },
    #[error(
        "could not load {path}; primary failed: {primary}; backup {backup_path} failed: {backup}"
    )]
    RecoveryFailed {
        path: PathBuf,
        backup_path: PathBuf,
        primary: Box<Self>,
        backup: Box<Self>,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MissingReference {
    pub key: String,
    pub path: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RecoveryMetadata {
    pub recovered_from_backup: bool,
    pub primary_path: PathBuf,
    pub backup_path: PathBuf,
    pub primary_error: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct LoadedValue<T> {
    pub value: T,
    pub recovery: RecoveryMetadata,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UnsafeReference {
    pub key: String,
    pub path: PathBuf,
    pub reason: String,
}

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum AssetPathError {
    #[error("asset path contains a NUL byte")]
    NulByte,
    #[error("relative asset path escapes the project directory")]
    Traversal,
    #[error("asset path resolves through a symlink outside the project directory")]
    SymlinkEscape,
}

pub struct ProjectStore;

impl ProjectStore {
    pub fn save_project(
        path: &Path,
        project: &ProjectConfiguration,
    ) -> Result<(), PersistenceError> {
        atomic_json_save(path, project)
    }

    pub fn load_project(path: &Path) -> Result<ProjectConfiguration, PersistenceError> {
        Ok(Self::load_project_with_metadata(path)?.value)
    }

    pub fn load_project_with_metadata(
        path: &Path,
    ) -> Result<LoadedValue<ProjectConfiguration>, PersistenceError> {
        load_versioned_with_metadata(path)
    }

    pub fn save_template(
        path: &Path,
        template: &TemplateDefinition,
    ) -> Result<(), PersistenceError> {
        atomic_json_save(path, template)
    }

    pub fn load_template(path: &Path) -> Result<TemplateDefinition, PersistenceError> {
        Ok(Self::load_template_with_metadata(path)?.value)
    }

    pub fn load_template_with_metadata(
        path: &Path,
    ) -> Result<LoadedValue<TemplateDefinition>, PersistenceError> {
        load_versioned_with_metadata(path)
    }

    pub fn backup_path(path: &Path) -> PathBuf {
        let mut backup = path.as_os_str().to_os_string();
        backup.push(".bak");
        PathBuf::from(backup)
    }

    pub fn check_missing_references(project: &ProjectConfiguration) -> Vec<MissingReference> {
        Self::check_missing_references_at(Path::new("."), project)
    }

    pub fn check_missing_references_at(
        project_path: &Path,
        project: &ProjectConfiguration,
    ) -> Vec<MissingReference> {
        referenced_paths(project)
            .into_iter()
            .filter_map(|(key, raw_path)| {
                let path = resolve_asset_path(project_path, raw_path)
                    .unwrap_or_else(|_| PathBuf::from(raw_path));
                let expected_directory = key == "photo_dir";
                let exists = if expected_directory {
                    path.is_dir()
                } else {
                    path.is_file()
                };
                (!exists).then_some(MissingReference { key, path })
            })
            .collect()
    }

    /// Finds relative references that leave the project directory or escape it
    /// through an existing symlink. Absolute references remain supported for
    /// compatibility with projects written by the Python application.
    pub fn validate_referenced_asset_paths(
        project_path: &Path,
        project: &ProjectConfiguration,
    ) -> Vec<UnsafeReference> {
        referenced_paths(project)
            .into_iter()
            .filter_map(|(key, raw_path)| {
                resolve_asset_path(project_path, raw_path)
                    .err()
                    .map(|error| UnsafeReference {
                        key,
                        path: PathBuf::from(raw_path),
                        reason: error.to_string(),
                    })
            })
            .collect()
    }

    pub fn relink_references(
        project: &mut ProjectConfiguration,
        replacements: &BTreeMap<String, String>,
    ) {
        if let Some(path) = replacements.get("excel_file") {
            project.excel_file_path = Some(path.clone());
        }
        if let Some(path) = replacements.get("photo_dir") {
            project.photo_dir_path = Some(path.clone());
        }
        if let (Some(template), Some(path)) = (
            project.template.as_mut(),
            replacements.get("background_image"),
        ) {
            template.background_image_path = Some(path.clone());
        }
    }
}

pub fn resolve_asset_path(project_path: &Path, raw_path: &str) -> Result<PathBuf, AssetPathError> {
    if raw_path.contains('\0') {
        return Err(AssetPathError::NulByte);
    }

    let raw = Path::new(raw_path);
    if raw.is_absolute() {
        return normalize_path(raw).ok_or(AssetPathError::Traversal);
    }

    let base = project_path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    let base = if base.is_absolute() {
        base.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|_| AssetPathError::Traversal)?
            .join(base)
    };
    let base = normalize_path(&base).ok_or(AssetPathError::Traversal)?;
    let resolved = base.join(raw);
    let resolved = normalize_path(&resolved).ok_or(AssetPathError::Traversal)?;
    if !resolved.starts_with(&base) {
        return Err(AssetPathError::Traversal);
    }

    if resolved.exists() {
        let canonical_base = fs::canonicalize(&base).map_err(|_| AssetPathError::SymlinkEscape)?;
        let canonical_path =
            fs::canonicalize(&resolved).map_err(|_| AssetPathError::SymlinkEscape)?;
        if !canonical_path.starts_with(canonical_base) {
            return Err(AssetPathError::SymlinkEscape);
        }
    }
    Ok(resolved)
}

fn referenced_paths(project: &ProjectConfiguration) -> Vec<(String, &str)> {
    let mut paths = Vec::new();
    if let Some(path) = &project.excel_file_path {
        paths.push(("excel_file".into(), path.as_str()));
    }
    if let Some(path) = &project.photo_dir_path {
        paths.push(("photo_dir".into(), path.as_str()));
    }
    if let Some(template) = &project.template {
        if let Some(path) = &template.background_image_path {
            paths.push(("background_image".into(), path.as_str()));
        }
    }
    paths.extend(
        project
            .photo_overrides
            .iter()
            .map(|(key, path)| (format!("photo_override:{key}"), path.as_str())),
    );
    paths
}

fn load_versioned_with_metadata<T: DeserializeOwned>(
    path: &Path,
) -> Result<LoadedValue<T>, PersistenceError> {
    let backup = ProjectStore::backup_path(path);
    match read_versioned(path) {
        Ok(value) => Ok(LoadedValue {
            value,
            recovery: RecoveryMetadata {
                recovered_from_backup: false,
                primary_path: path.to_path_buf(),
                backup_path: backup,
                primary_error: None,
            },
        }),
        Err(primary) => match read_versioned(&backup) {
            Ok(value) => Ok(LoadedValue {
                value,
                recovery: RecoveryMetadata {
                    recovered_from_backup: true,
                    primary_path: path.to_path_buf(),
                    backup_path: backup,
                    primary_error: Some(primary.to_string()),
                },
            }),
            Err(backup_error) => Err(PersistenceError::RecoveryFailed {
                path: path.to_path_buf(),
                backup_path: backup,
                primary: Box::new(primary),
                backup: Box::new(backup_error),
            }),
        },
    }
}

fn read_versioned<T: DeserializeOwned>(path: &Path) -> Result<T, PersistenceError> {
    let bytes = fs::read(path).map_err(|source| {
        if source.kind() == std::io::ErrorKind::NotFound {
            PersistenceError::MissingPath(path.to_path_buf())
        } else {
            PersistenceError::Read {
                path: path.to_path_buf(),
                source,
            }
        }
    })?;
    let value: serde_json::Value =
        serde_json::from_slice(&bytes).map_err(|source| PersistenceError::Json {
            path: path.to_path_buf(),
            source,
        })?;
    let version = value
        .get("version")
        .and_then(|value| value.as_str())
        .unwrap_or_default();
    let current_major = CURRENT_FORMAT_VERSION.split('.').next();
    let version_is_supported = !version.is_empty() && version.split('.').next() == current_major;
    if !version_is_supported {
        return Err(PersistenceError::Version {
            path: path.to_path_buf(),
            version: version.into(),
        });
    }
    serde_json::from_value(value).map_err(|source| PersistenceError::Json {
        path: path.to_path_buf(),
        source,
    })
}

fn atomic_json_save<T: Serialize>(path: &Path, value: &T) -> Result<(), PersistenceError> {
    if let Some(parent) = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
    {
        fs::create_dir_all(parent).map_err(|source| PersistenceError::Write {
            path: parent.to_path_buf(),
            source,
        })?;
    }
    let json =
        serde_json::to_vec_pretty(value).expect("serializing compatibility models cannot fail");
    let temp_path = temporary_path(path, "tmp");
    let backup = ProjectStore::backup_path(path);
    let backup_temp_path = temporary_path(&backup, "tmp");
    let result = (|| {
        write_synced_file(&temp_path, &json)?;
        if path.exists() {
            copy_to_synced_file(path, &backup_temp_path)?;
        } else {
            copy_to_synced_file(&temp_path, &backup_temp_path)?;
        }
        replace_file(&backup_temp_path, &backup)?;
        replace_file(&temp_path, path)?;
        Ok::<(), std::io::Error>(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp_path);
        let _ = fs::remove_file(&backup_temp_path);
    }
    result.map_err(|source| PersistenceError::Write {
        path: path.to_path_buf(),
        source,
    })
}

fn temporary_path(path: &Path, suffix: &str) -> PathBuf {
    let mut temporary = path.as_os_str().to_os_string();
    temporary.push(format!(".{}.{}", Uuid::new_v4(), suffix));
    PathBuf::from(temporary)
}

fn write_synced_file(path: &Path, bytes: &[u8]) -> Result<(), std::io::Error> {
    let mut file = fs::File::create(path)?;
    file.write_all(bytes)?;
    file.sync_all()
}

fn copy_to_synced_file(source: &Path, destination: &Path) -> Result<(), std::io::Error> {
    let mut input = fs::File::open(source)?;
    let mut output = fs::File::create(destination)?;
    std::io::copy(&mut input, &mut output)?;
    output.sync_all()
}

fn replace_file(source: &Path, destination: &Path) -> Result<(), std::io::Error> {
    #[cfg(windows)]
    if destination.exists() {
        fs::remove_file(destination)?;
    }
    fs::rename(source, destination)
}

fn normalize_path(path: &Path) -> Option<PathBuf> {
    let mut normalized = PathBuf::new();
    for component in path.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                if !normalized.pop() {
                    return None;
                }
            }
            Component::Normal(value) => normalized.push(value),
            Component::RootDir | Component::Prefix(_) => normalized.push(component.as_os_str()),
        }
    }
    Some(normalized)
}

pub fn current_format_version() -> &'static str {
    CURRENT_FORMAT_VERSION
}
