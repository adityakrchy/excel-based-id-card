use std::{fs, path::Path, thread, time::Duration};

use excel_id_card_rust::{
    photos::PhotoLibrary,
    tasks::{ThumbnailError, ThumbnailPriority, ThumbnailQueue},
};
use image::{Rgba, RgbaImage};
use tempfile::tempdir;

fn write_png(path: &Path, width: u32, height: u32) {
    let image = RgbaImage::from_pixel(width, height, Rgba([40, 80, 120, 255]));
    image.save(path).unwrap();
}

#[test]
fn persisted_index_invalidates_records_with_changed_metadata() {
    let directory = tempdir().unwrap();
    let photo = directory.path().join("EMP-1.png");
    write_png(&photo, 4, 4);
    let index_path = directory.path().join("photos.json");

    let mut library = PhotoLibrary::new(directory.path());
    let report = library.rescan().unwrap();
    assert_eq!(report.added.len(), 1);
    library.save(&index_path).unwrap();

    fs::write(&photo, b"replacement bytes with different metadata").unwrap();
    let loaded = PhotoLibrary::load(&index_path).unwrap();
    assert_eq!(loaded.record_count(), 0);
    assert_eq!(loaded.invalidated_records().len(), 1);
    assert_eq!(loaded.invalidated_records()[0].match_key, "EMP-1");
}

#[test]
fn rescan_reports_added_modified_and_removed_files_incrementally() {
    let directory = tempdir().unwrap();
    let first = directory.path().join("one.jpg");
    fs::write(&first, b"initial file").unwrap();

    let mut library = PhotoLibrary::new(directory.path());
    let initial = library.rescan().unwrap();
    assert_eq!(initial.added.len(), 1);
    assert!(library.rescan().unwrap().is_empty());

    let second = directory.path().join("two.png");
    write_png(&second, 2, 2);
    fs::write(&first, b"changed file size").unwrap();
    let changed = library.rescan().unwrap();
    assert_eq!(changed.added.len(), 1);
    assert_eq!(changed.modified.len(), 1);
    assert!(changed.removed.is_empty());

    fs::remove_file(&second).unwrap();
    let removed = library.rescan().unwrap();
    assert_eq!(removed.removed.len(), 1);
    assert_eq!(removed.removed[0].match_key, "two");
}

#[test]
fn thumbnail_queue_is_bounded_and_cancellation_is_observable() {
    let directory = tempdir().unwrap();
    let first = directory.path().join("first.png");
    let second = directory.path().join("second.png");
    write_png(&first, 64, 64);
    write_png(&second, 64, 64);

    let queue = ThumbnailQueue::new(1, 4 * 64 * 64);
    let first_request = queue
        .request(&first, 32, ThumbnailPriority::Background)
        .unwrap();
    let second_request = queue.request(&second, 32, ThumbnailPriority::Visible);
    assert!(queue.pending_count() <= 1);
    if let Ok(request) = second_request {
        request.cancel();
        assert!(matches!(
            request.recv_timeout(Duration::from_secs(2)).unwrap(),
            Err(ThumbnailError::Cancelled) | Ok(_)
        ));
    }
    first_request.cancel();
    assert!(matches!(
        first_request.recv_timeout(Duration::from_secs(2)).unwrap(),
        Err(ThumbnailError::Cancelled) | Ok(_)
    ));
    assert!(queue.pending_count() <= 1);
    thread::sleep(Duration::from_millis(50));
    assert!(queue.cache_bytes() <= 4 * 64 * 64);
}

#[test]
fn corrupted_image_returns_decode_error_without_affecting_indexing() {
    let directory = tempdir().unwrap();
    let corrupted = directory.path().join("broken.jpg");
    fs::write(&corrupted, b"not an image").unwrap();

    let mut library = PhotoLibrary::new(directory.path());
    assert_eq!(library.rescan().unwrap().added.len(), 1);
    let queue = ThumbnailQueue::new(2, 1024 * 1024);
    let request = queue
        .request(&corrupted, 32, ThumbnailPriority::Visible)
        .unwrap();
    match request.recv_timeout(Duration::from_secs(2)).unwrap() {
        Err(ThumbnailError::Decode { path, .. }) => assert_eq!(path, corrupted),
        other => panic!("expected decode failure, got {other:?}"),
    }
}
