//! Typed, UI-independent review state management.
//!
//! Review state is keyed by the imported record's stable `record_id`.  The
//! source order is kept separately from the map so navigation remains
//! deterministic while lookups and persistence remain keyed and cheap.

use std::collections::BTreeMap;
use std::time::{SystemTime, UNIX_EPOCH};

use thiserror::Error;

use crate::data::models::{ProjectConfiguration, ReviewRecord, ReviewStatus, SourceRecord};

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum ReviewError {
    #[error("review record id cannot be empty")]
    EmptyRecordId,
    #[error("duplicate review record id: {0}")]
    DuplicateRecordId(String),
    #[error("review record not found: {0}")]
    UnknownRecord(String),
}

/// A deterministic review session over a source-ordered set of records.
#[derive(Debug, Clone, Default)]
pub struct ReviewManager {
    records: BTreeMap<String, ReviewRecord>,
    source_order: Vec<String>,
    current_record_id: Option<String>,
    search_query: String,
}

impl ReviewManager {
    /// Construct a manager from already materialized review records.
    pub fn new(records: Vec<ReviewRecord>) -> Self {
        Self::try_new(records).expect("review records must have unique, non-empty record IDs")
    }

    /// Fallible constructor useful at import or persistence boundaries.
    pub fn try_new(records: Vec<ReviewRecord>) -> Result<Self, ReviewError> {
        let mut manager = Self::default();
        for record in records {
            manager.insert(record)?;
        }
        manager.current_record_id = manager.source_order.first().cloned();
        Ok(manager)
    }

    pub fn from_review_records(records: Vec<ReviewRecord>) -> Result<Self, ReviewError> {
        Self::try_new(records)
    }

    /// Build review records in source order, applying persisted statuses and
    /// any paths produced by generation.
    pub fn from_source_records(
        source_records: &[SourceRecord],
        saved_states: &BTreeMap<String, ReviewStatus>,
        rendered_image_paths: &BTreeMap<String, String>,
    ) -> Result<Self, ReviewError> {
        let records = source_records
            .iter()
            .map(|source| {
                let pin = source.pin_or_raw().to_owned();
                let pin = if pin.is_empty() {
                    format!("REC-{}", source.row_index)
                } else {
                    pin
                };
                let name = source.get_value("Name");
                let name = if name.is_empty() {
                    source
                        .data
                        .iter()
                        .find(|(k, v)| k.to_lowercase().contains("name") && !v.is_null())
                        .map(|(_, v)| match v {
                            serde_json::Value::String(s) => s.clone(),
                            other => other.to_string(),
                        })
                        .unwrap_or_else(|| "Card".into())
                } else {
                    name
                };
                ReviewRecord {
                    record_id: source.record_id.clone(),
                    pin,
                    name,
                    status: saved_states
                        .get(&source.record_id)
                        .cloned()
                        .unwrap_or_default(),
                    comments: None,
                    rendered_image_path: rendered_image_paths.get(&source.record_id).cloned(),
                    last_reviewed_at: None,
                }
            })
            .collect();
        Self::try_new(records)
    }

    /// Source-record convenience constructor for sessions without generated
    /// images yet.
    pub fn from_sources(
        source_records: &[SourceRecord],
        saved_states: &BTreeMap<String, ReviewStatus>,
    ) -> Result<Self, ReviewError> {
        Self::from_sources_with_comments(source_records, saved_states, &BTreeMap::new())
    }

    pub fn from_sources_with_comments(
        source_records: &[SourceRecord],
        saved_states: &BTreeMap<String, ReviewStatus>,
        saved_comments: &BTreeMap<String, String>,
    ) -> Result<Self, ReviewError> {
        let mut manager =
            Self::from_source_records(source_records, saved_states, &BTreeMap::new())?;
        for (record_id, comment) in saved_comments {
            if let Some(record) = manager.records.get_mut(record_id) {
                record.comments = (!comment.trim().is_empty()).then(|| comment.clone());
            }
        }
        Ok(manager)
    }

    /// Initialize from the native generation results used by this crate.
    pub fn from_generation(
        source_records: &[SourceRecord],
        generation_results: &[crate::generation::RenderResult],
        saved_states: &BTreeMap<String, ReviewStatus>,
    ) -> Result<Self, ReviewError> {
        let rendered_image_paths = generation_results
            .iter()
            .filter_map(|result| {
                result
                    .image_path
                    .as_ref()
                    .map(|path| (result.record_id.clone(), path.clone()))
            })
            .collect();
        Self::from_source_records(source_records, saved_states, &rendered_image_paths)
    }

    /// Restore persisted statuses onto a set of review records.
    pub fn from_project_configuration(
        project: &ProjectConfiguration,
        records: Vec<ReviewRecord>,
    ) -> Result<Self, ReviewError> {
        let mut manager = Self::try_new(records)?;
        manager.load_review_states(&project.review_states);
        Ok(manager)
    }

    /// Add one record while retaining insertion/source order.
    pub fn insert(&mut self, record: ReviewRecord) -> Result<(), ReviewError> {
        if record.record_id.is_empty() {
            return Err(ReviewError::EmptyRecordId);
        }
        if self.records.contains_key(&record.record_id) {
            return Err(ReviewError::DuplicateRecordId(record.record_id));
        }
        let record_id = record.record_id.clone();
        self.source_order.push(record_id.clone());
        self.records.insert(record_id.clone(), record);
        if self.current_record_id.is_none() {
            self.current_record_id = Some(record_id);
        }
        Ok(())
    }

    pub fn len(&self) -> usize {
        self.records.len()
    }

    pub fn is_empty(&self) -> bool {
        self.records.is_empty()
    }

    pub fn records(&self) -> Vec<&ReviewRecord> {
        self.source_order
            .iter()
            .filter_map(|record_id| self.records.get(record_id))
            .collect()
    }

    pub fn record(&self, record_id: &str) -> Option<&ReviewRecord> {
        self.records.get(record_id)
    }

    pub fn current_record(&self) -> Option<&ReviewRecord> {
        let visible = self.visible_ids();
        let id = self
            .current_record_id
            .as_deref()
            .filter(|current| visible.iter().any(|id| id == current))
            .or_else(|| visible.first().map(String::as_str))?;
        self.records.get(id)
    }

    pub fn current_record_id(&self) -> Option<&str> {
        self.current_record()
            .map(|record| record.record_id.as_str())
    }

    /// Zero-based position in the current source-ordered search result.
    pub fn current_index(&self) -> Option<usize> {
        let current = self.current_record_id()?;
        self.visible_ids().iter().position(|id| id == current)
    }

    pub fn first(&mut self) -> Option<&ReviewRecord> {
        self.current_record_id = self.visible_ids().first().cloned();
        self.current_record()
    }

    pub fn last(&mut self) -> Option<&ReviewRecord> {
        self.current_record_id = self.visible_ids().last().cloned();
        self.current_record()
    }

    #[allow(clippy::should_implement_trait)]
    pub fn next(&mut self) -> Option<&ReviewRecord> {
        let visible = self.visible_ids();
        if let Some(index) = self
            .current_record_id
            .as_ref()
            .and_then(|current| visible.iter().position(|id| id == current))
        {
            if let Some(next) = visible.get(index + 1) {
                self.current_record_id = Some(next.clone());
            }
        } else {
            self.current_record_id = visible.first().cloned();
        }
        self.current_record()
    }

    pub fn previous(&mut self) -> Option<&ReviewRecord> {
        let visible = self.visible_ids();
        if let Some(index) = self
            .current_record_id
            .as_ref()
            .and_then(|current| visible.iter().position(|id| id == current))
        {
            if index > 0 {
                self.current_record_id = Some(visible[index - 1].clone());
            }
        } else {
            self.current_record_id = visible.first().cloned();
        }
        self.current_record()
    }

    pub fn prev(&mut self) -> Option<&ReviewRecord> {
        self.previous()
    }

    pub fn first_record(&mut self) -> Option<&ReviewRecord> {
        self.first()
    }

    pub fn last_record(&mut self) -> Option<&ReviewRecord> {
        self.last()
    }

    pub fn next_record(&mut self) -> Option<&ReviewRecord> {
        self.next()
    }

    pub fn previous_record(&mut self) -> Option<&ReviewRecord> {
        self.previous()
    }

    /// Search record id, PIN, or name case-insensitively without changing the
    /// current search or navigation position.
    pub fn search(&self, query: &str) -> Vec<&ReviewRecord> {
        let query = query.trim().to_lowercase();
        self.records()
            .into_iter()
            .filter(|record| {
                query.is_empty()
                    || record.record_id.to_lowercase().contains(&query)
                    || record.pin.to_lowercase().contains(&query)
                    || record.name.to_lowercase().contains(&query)
            })
            .collect()
    }

    pub fn search_records(&self, query: &str) -> Vec<&ReviewRecord> {
        self.search(query)
    }

    pub fn set_search_query(&mut self, query: impl Into<String>) {
        self.search_query = query.into();
        self.current_record_id = self.visible_ids().first().cloned();
    }

    pub fn search_query(&self) -> &str {
        &self.search_query
    }

    pub fn clear_search(&mut self) {
        self.set_search_query(String::new());
    }

    pub fn set_status(
        &mut self,
        record_id: &str,
        status: ReviewStatus,
    ) -> Result<&ReviewRecord, ReviewError> {
        self.transition(record_id, status)
    }

    pub fn update_status(
        &mut self,
        record_id: &str,
        status: ReviewStatus,
        comments: Option<String>,
    ) -> Result<&ReviewRecord, ReviewError> {
        let record = self.record_mut(record_id)?;
        record.status = status;
        record.comments = comments;
        record.last_reviewed_at = Some(reviewed_at());
        Ok(record)
    }

    pub fn transition(
        &mut self,
        record_id: &str,
        status: ReviewStatus,
    ) -> Result<&ReviewRecord, ReviewError> {
        let record = self.record_mut(record_id)?;
        record.status = status;
        record.last_reviewed_at = Some(reviewed_at());
        Ok(record)
    }

    pub fn select_record(&mut self, record_id: &str) -> bool {
        if self.records.contains_key(record_id) {
            self.current_record_id = Some(record_id.to_owned());
            true
        } else {
            false
        }
    }

    /// Records with status `Pending` in source order.
    pub fn pending_records(&self) -> Vec<&ReviewRecord> {
        self.source_order
            .iter()
            .filter_map(|record_id| self.records.get(record_id))
            .filter(|record| record.status == ReviewStatus::Pending)
            .collect()
    }

    /// Count of records currently pending approval.
    pub fn pending_count(&self) -> usize {
        self.records
            .values()
            .filter(|record| record.status == ReviewStatus::Pending)
            .count()
    }

    /// Count of records currently approved.
    pub fn approved_count(&self) -> usize {
        self.records
            .values()
            .filter(|record| record.status == ReviewStatus::Approved)
            .count()
    }

    pub fn approve(&mut self, record_id: &str) -> Result<&ReviewRecord, ReviewError> {
        self.transition(record_id, ReviewStatus::Approved)
    }

    /// Transition all records to Approved at once.
    pub fn approve_all(&mut self) {
        let timestamp = reviewed_at();
        for record in self.records.values_mut() {
            record.status = ReviewStatus::Approved;
            record.last_reviewed_at = Some(timestamp.clone());
        }
    }

    pub fn reject(&mut self, record_id: &str) -> Result<&ReviewRecord, ReviewError> {
        self.transition(record_id, ReviewStatus::Rejected)
    }

    pub fn mark_correction(&mut self, record_id: &str) -> Result<&ReviewRecord, ReviewError> {
        self.transition(record_id, ReviewStatus::Correction)
    }

    pub fn skip(&mut self, record_id: &str) -> Result<&ReviewRecord, ReviewError> {
        self.transition(record_id, ReviewStatus::Skipped)
    }

    pub fn pending(&mut self, record_id: &str) -> Result<&ReviewRecord, ReviewError> {
        self.transition(record_id, ReviewStatus::Pending)
    }

    pub fn set_pending(&mut self, record_id: &str) -> Result<&ReviewRecord, ReviewError> {
        self.pending(record_id)
    }

    pub fn set_approved(&mut self, record_id: &str) -> Result<&ReviewRecord, ReviewError> {
        self.approve(record_id)
    }

    pub fn set_rejected(&mut self, record_id: &str) -> Result<&ReviewRecord, ReviewError> {
        self.reject(record_id)
    }

    pub fn set_correction(&mut self, record_id: &str) -> Result<&ReviewRecord, ReviewError> {
        self.mark_correction(record_id)
    }

    pub fn set_skipped(&mut self, record_id: &str) -> Result<&ReviewRecord, ReviewError> {
        self.skip(record_id)
    }

    pub fn set_comment(
        &mut self,
        record_id: &str,
        comment: Option<String>,
    ) -> Result<&ReviewRecord, ReviewError> {
        let record = self.record_mut(record_id)?;
        record.comments = comment;
        record.last_reviewed_at = Some(reviewed_at());
        Ok(record)
    }

    pub fn comment(&self, record_id: &str) -> Option<&str> {
        self.record(record_id)?.comments.as_deref()
    }

    /// Invalidate a record after regeneration. A missing path means the old
    /// rendered image is no longer available; a supplied path replaces it.
    pub fn regenerate(
        &mut self,
        record_id: &str,
        rendered_image_path: Option<String>,
    ) -> Result<&ReviewRecord, ReviewError> {
        let record = self.record_mut(record_id)?;
        record.status = ReviewStatus::Pending;
        record.rendered_image_path = rendered_image_path;
        record.last_reviewed_at = None;
        Ok(record)
    }

    pub fn invalidate_regeneration(
        &mut self,
        record_id: &str,
    ) -> Result<&ReviewRecord, ReviewError> {
        self.regenerate(record_id, None)
    }

    /// Compatibility name for callers that only need to invalidate approval
    /// while retaining the currently displayed image.
    pub fn invalidate_approval(&mut self, record_id: &str) -> Result<&ReviewRecord, ReviewError> {
        let record = self.record_mut(record_id)?;
        record.status = ReviewStatus::Pending;
        Ok(record)
    }

    pub fn to_review_records(&self) -> Vec<ReviewRecord> {
        self.records().into_iter().cloned().collect::<Vec<_>>()
    }

    pub fn into_review_records(self) -> Vec<ReviewRecord> {
        self.source_order
            .into_iter()
            .filter_map(|record_id| self.records.get(&record_id).cloned())
            .collect()
    }

    pub fn to_review_states(&self) -> BTreeMap<String, ReviewStatus> {
        self.source_order
            .iter()
            .filter_map(|record_id| {
                self.records
                    .get(record_id)
                    .map(|record| (record_id.clone(), record.status.clone()))
            })
            .collect()
    }

    pub fn review_states(&self) -> BTreeMap<String, ReviewStatus> {
        self.to_review_states()
    }

    pub fn load_review_states(&mut self, states: &BTreeMap<String, ReviewStatus>) {
        for (record_id, status) in states {
            if let Some(record) = self.records.get_mut(record_id) {
                record.status = status.clone();
            }
        }
    }

    pub fn apply_to_project_configuration(&self, project: &mut ProjectConfiguration) {
        project.review_states = self.to_review_states();
        project.review_comments = self
            .records()
            .into_iter()
            .filter_map(|record| {
                record
                    .comments
                    .as_ref()
                    .filter(|comment| !comment.trim().is_empty())
                    .map(|comment| (record.record_id.clone(), comment.clone()))
            })
            .collect();
    }

    pub fn update_project_configuration(&self, project: &mut ProjectConfiguration) {
        self.apply_to_project_configuration(project);
    }

    fn record_mut(&mut self, record_id: &str) -> Result<&mut ReviewRecord, ReviewError> {
        self.records
            .get_mut(record_id)
            .ok_or_else(|| ReviewError::UnknownRecord(record_id.to_owned()))
    }

    fn visible_ids(&self) -> Vec<String> {
        let query = self.search_query.trim().to_lowercase();
        if query.is_empty() {
            return self.source_order.clone();
        }
        self.source_order
            .iter()
            .filter(|record_id| {
                self.records.get(*record_id).is_some_and(|record| {
                    record.record_id.to_lowercase().contains(&query)
                        || record.pin.to_lowercase().contains(&query)
                        || record.name.to_lowercase().contains(&query)
                })
            })
            .cloned()
            .collect()
    }
}

fn reviewed_at() -> String {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
        .to_string()
}
