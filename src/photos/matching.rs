//! Generic column matching with explicit matched/ambiguous/missing states.

use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Path, PathBuf},
};

use super::scanner::{normalize_key, PhotoIndex};
use crate::data::models::{MatchStatus, PhotoMatchResult, SourceRecord};

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct MatchSummary {
    pub total_records: usize,
    pub matched_count: usize,
    pub missing_count: usize,
    pub ambiguous_count: usize,
    pub overridden_count: usize,
    pub unassigned_photos_count: usize,
    pub unassigned_photo_paths: Vec<PathBuf>,
}

#[derive(Debug, Clone, Default)]
pub struct PhotoMatcher {
    pub index: PhotoIndex,
    pub overrides: BTreeMap<String, String>,
    pub key_column: Option<String>,
    pub prefix: String,
    pub suffix: String,
}

impl PhotoMatcher {
    pub fn set_index(&mut self, index: PhotoIndex) {
        self.index = index;
    }
    pub fn set_key_column(&mut self, column: Option<String>) {
        self.key_column = column;
    }
    pub fn set_affixes(&mut self, prefix: impl Into<String>, suffix: impl Into<String>) {
        self.prefix = prefix.into();
        self.suffix = suffix.into();
    }
    pub fn set_override(&mut self, key_or_record_id: impl Into<String>, path: impl Into<String>) {
        self.overrides
            .insert(key_or_record_id.into().trim().to_owned(), path.into());
    }
    pub fn remove_override(&mut self, key_or_record_id: &str) {
        self.overrides.remove(key_or_record_id.trim());
    }
    pub fn clear_overrides(&mut self) {
        self.overrides.clear();
    }

    pub fn lookup_key(&self, record: &SourceRecord) -> String {
        self.key_column
            .as_ref()
            .map(|column| record.get_value(column))
            .filter(|value| !value.is_empty())
            .map(|value| normalize_key(&value))
            .unwrap_or_else(|| normalize_key(&record.pin))
    }

    pub fn match_record(&self, record: &SourceRecord) -> PhotoMatchResult {
        let key = self.lookup_key(record);
        let pin = if record.pin.is_empty() {
            key.clone()
        } else {
            record.pin.clone()
        };
        let override_path = self
            .overrides
            .get(&record.record_id)
            .or_else(|| self.overrides.get(&key))
            .or_else(|| self.overrides.get(&pin));
        if let Some(path) = override_path {
            let path = Path::new(path);
            if path.is_file() {
                return result(
                    record,
                    pin,
                    key,
                    MatchStatus::Overridden,
                    Some(path),
                    Vec::new(),
                    true,
                    format!("Manually overridden: {}", path.display()),
                );
            }
        }
        if key.is_empty() {
            return result(
                record,
                pin,
                key,
                MatchStatus::Missing,
                None,
                Vec::new(),
                false,
                "Record has no value for the configured photo key column".into(),
            );
        }
        let patterns = [
            format!("{}{}{}", self.prefix, key, self.suffix),
            key.clone(),
        ];
        let mut candidates = Vec::new();
        for pattern in patterns.iter().filter(|pattern| !pattern.is_empty()) {
            for paths in self
                .index
                .exact
                .get(pattern)
                .into_iter()
                .chain(self.index.lower.get(&pattern.to_ascii_lowercase()))
            {
                for path in paths {
                    if !candidates.contains(path) {
                        candidates.push(path.clone());
                    }
                }
            }
        }
        match candidates.len() {
            1 => result(
                record,
                pin,
                key,
                MatchStatus::Matched,
                candidates.first().map(|path| path.as_path()),
                Vec::new(),
                false,
                format!("Matched {}", candidates[0].display()),
            ),
            count if count > 1 => result(
                record,
                pin,
                key,
                MatchStatus::Ambiguous,
                None,
                candidates
                    .iter()
                    .map(|path| path.to_string_lossy().into_owned())
                    .collect(),
                false,
                format!("Ambiguous: {count} photos found"),
            ),
            _ => result(
                record,
                pin,
                key,
                MatchStatus::Missing,
                None,
                Vec::new(),
                false,
                "No photo found for lookup key".into(),
            ),
        }
    }

    pub fn match_all(
        &self,
        records: &[SourceRecord],
    ) -> (BTreeMap<String, PhotoMatchResult>, MatchSummary) {
        let mut summary = MatchSummary {
            total_records: records.len(),
            ..Default::default()
        };
        let mut results = BTreeMap::new();
        let mut assigned = BTreeSet::new();
        for record in records {
            let result = self.match_record(record);
            match result.status {
                MatchStatus::Matched => summary.matched_count += 1,
                MatchStatus::Overridden => summary.overridden_count += 1,
                MatchStatus::Ambiguous => summary.ambiguous_count += 1,
                MatchStatus::Missing => summary.missing_count += 1,
            }
            if let Some(path) = &result.photo_path {
                assigned.insert(PathBuf::from(path));
            }
            results.insert(record.record_id.clone(), result);
        }
        for paths in self.index.exact.values() {
            for path in paths {
                if !assigned.contains(path) {
                    summary.unassigned_photo_paths.push(path.clone());
                }
            }
        }
        summary.unassigned_photos_count = summary.unassigned_photo_paths.len();
        (results, summary)
    }
}

#[allow(clippy::too_many_arguments)]
fn result(
    record: &SourceRecord,
    pin: String,
    key: String,
    status: MatchStatus,
    path: Option<&Path>,
    candidates: Vec<String>,
    overridden: bool,
    details: String,
) -> PhotoMatchResult {
    PhotoMatchResult {
        pin,
        key_value: Some(key),
        record_id: Some(record.record_id.clone()),
        status,
        photo_path: path.map(|path| path.to_string_lossy().into_owned()),
        candidate_paths: candidates,
        is_overridden: overridden,
        details,
    }
}
