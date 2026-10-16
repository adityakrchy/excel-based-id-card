//! Focused, compatibility-first Rust migration foundation.
//!
//! The Python application remains the product implementation.  This crate owns
//! only the first migration slice and deliberately keeps the data contracts
//! close to the existing JSON files.

pub mod app;
pub mod data;
pub mod editor;
pub mod export;
pub mod generation;
pub mod photos;
pub mod projects;
pub mod rendering;
pub mod review;
pub mod tasks;
pub mod templates;
pub mod ui;

pub use data::models;
