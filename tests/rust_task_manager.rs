use std::time::Duration;

use excel_id_card_rust::tasks::{TaskEvent, TaskKind, TaskManager, TaskStatus};

fn terminal_event(receiver: &crossbeam_channel::Receiver<TaskEvent>) -> TaskEvent {
    loop {
        if let event @ (TaskEvent::Completed { .. }
        | TaskEvent::Failed { .. }
        | TaskEvent::Cancelled { .. }) = receiver.recv_timeout(Duration::from_secs(2)).unwrap()
        {
            return event;
        }
    }
}

#[test]
fn event_delivery_is_bounded_and_preserves_progress() {
    let manager = TaskManager::new(1);
    let receiver = manager.event_receiver();
    let handle = manager
        .spawn(TaskKind::Import, |context| {
            assert!(context.report_progress(1, Some(2)));
            assert!(context.report_progress(2, Some(2)));
            Ok(())
        })
        .unwrap();

    assert!(receiver.len() <= 1);
    assert!(matches!(
        receiver.recv_timeout(Duration::from_secs(2)).unwrap(),
        TaskEvent::Started { .. }
    ));
    assert!(matches!(
        receiver.recv_timeout(Duration::from_secs(2)).unwrap(),
        TaskEvent::Progress { .. }
    ));
    assert!(matches!(
        receiver.recv_timeout(Duration::from_secs(2)).unwrap(),
        TaskEvent::Progress { .. }
    ));
    assert!(matches!(
        terminal_event(&receiver),
        TaskEvent::Completed { .. }
    ));
    assert_eq!(manager.status(handle.id()), Some(TaskStatus::Completed));
}

#[test]
fn cancellation_is_cooperative_and_emits_a_terminal_event() {
    let manager = TaskManager::new(4);
    let receiver = manager.event_receiver();
    let handle = manager
        .spawn(TaskKind::PhotoIndex, |context| {
            while !context.is_cancelled() {
                std::thread::sleep(Duration::from_millis(2));
            }
            Ok(())
        })
        .unwrap();

    assert!(matches!(
        receiver.recv_timeout(Duration::from_secs(2)).unwrap(),
        TaskEvent::Started { .. }
    ));
    handle.cancel();
    assert!(matches!(
        terminal_event(&receiver),
        TaskEvent::Cancelled { .. }
    ));
    assert_eq!(manager.status(handle.id()), Some(TaskStatus::Cancelled));
}

#[test]
fn cancellation_unblocks_progress_backpressure() {
    let manager = TaskManager::new(1);
    let handle = manager
        .spawn(TaskKind::Preview, |context| {
            while context.report_progress(1, Some(1)) {}
            Ok(())
        })
        .unwrap();

    // Started occupies the only event slot, so the worker is blocked in its
    // first progress report until cancellation is observed.
    std::thread::sleep(Duration::from_millis(20));
    handle.cancel();
    let deadline = std::time::Instant::now() + Duration::from_secs(2);
    while manager.pending_worker_count() != 0 && std::time::Instant::now() < deadline {
        std::thread::sleep(Duration::from_millis(2));
    }
    assert_eq!(manager.pending_worker_count(), 0);
    assert_eq!(manager.status(handle.id()), Some(TaskStatus::Cancelled));
}

#[test]
fn completion_and_error_are_reported_with_status() {
    let manager = TaskManager::new(8);
    let receiver = manager.event_receiver();
    let completed = manager.spawn(TaskKind::Generation, |_| Ok(())).unwrap();
    let failed = manager
        .spawn(TaskKind::Export, |_| Err("output unavailable".to_owned()))
        .unwrap();

    let mut completed_event = false;
    let mut failed_event = false;
    while !(completed_event && failed_event) {
        match receiver.recv_timeout(Duration::from_secs(2)).unwrap() {
            TaskEvent::Completed { id, .. } if id == completed.id() => completed_event = true,
            TaskEvent::Failed { id, error, .. } if id == failed.id() => {
                assert_eq!(error, "output unavailable");
                failed_event = true;
            }
            _ => {}
        }
    }
    assert_eq!(manager.status(completed.id()), Some(TaskStatus::Completed));
    assert_eq!(
        manager.status(failed.id()),
        Some(TaskStatus::Failed("output unavailable".into()))
    );
}

#[test]
fn dropping_a_manager_wakes_workers_blocked_by_a_full_event_queue() {
    let manager = TaskManager::new(1);
    let _handle = manager
        .spawn(TaskKind::Thumbnail, |context| {
            while !context.is_cancelled() {
                std::thread::sleep(Duration::from_millis(2));
            }
            Ok(())
        })
        .unwrap();
    std::thread::sleep(Duration::from_millis(20));
    drop(manager);
}
