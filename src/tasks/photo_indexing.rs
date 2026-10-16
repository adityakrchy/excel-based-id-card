//! Cancellable, progressive filename indexing on a bounded channel.

use std::{
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread::{self, JoinHandle},
    time::Duration,
};

use crossbeam_channel::{bounded, Receiver, RecvTimeoutError, SendTimeoutError, Sender};
use walkdir::WalkDir;

use crate::photos::scanner::{image_stem, PhotoIndex};

pub const DEFAULT_DISCOVERY_CAPACITY: usize = 64;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PhotoDiscovery {
    pub stem: String,
    pub path: PathBuf,
}

#[derive(Debug, Clone)]
pub enum IndexEvent {
    Discovered {
        batch: Vec<PhotoDiscovery>,
        indexed_count: usize,
    },
    Finished {
        index: PhotoIndex,
    },
    Cancelled {
        indexed_count: usize,
    },
    Failed(String),
}

pub struct PhotoIndexingTask {
    receiver: Receiver<IndexEvent>,
    cancel: Arc<AtomicBool>,
    join: Option<JoinHandle<()>>,
}

impl PhotoIndexingTask {
    pub fn start(root: impl AsRef<Path>, batch_size: usize, channel_capacity: usize) -> Self {
        let root = root.as_ref().to_path_buf();
        let batch_size = batch_size.max(1);
        let channel_capacity = channel_capacity.max(1);
        let (sender, receiver) = bounded(channel_capacity);
        let cancel = Arc::new(AtomicBool::new(false));
        let worker_cancel = Arc::clone(&cancel);
        let join = thread::spawn(move || scan_worker(root, batch_size, sender, worker_cancel));
        Self {
            receiver,
            cancel,
            join: Some(join),
        }
    }

    pub fn cancel(&self) {
        self.cancel.store(true, Ordering::Release);
    }
    pub fn try_recv(&self) -> Result<IndexEvent, crossbeam_channel::TryRecvError> {
        self.receiver.try_recv()
    }
    pub fn recv_timeout(&self, timeout: Duration) -> Result<IndexEvent, RecvTimeoutError> {
        self.receiver.recv_timeout(timeout)
    }
    pub fn is_cancelled(&self) -> bool {
        self.cancel.load(Ordering::Acquire)
    }

    pub fn join(&mut self) -> thread::Result<()> {
        self.join
            .take()
            .expect("indexing worker already joined")
            .join()
    }
}

fn send_event(sender: &Sender<IndexEvent>, mut event: IndexEvent, cancel: &AtomicBool) -> bool {
    loop {
        if cancel.load(Ordering::Acquire) {
            return false;
        }
        match sender.send_timeout(event, Duration::from_millis(25)) {
            Ok(()) => return true,
            Err(SendTimeoutError::Timeout(returned)) => event = returned,
            Err(SendTimeoutError::Disconnected(_)) => return false,
        }
    }
}

fn scan_worker(
    root: PathBuf,
    batch_size: usize,
    sender: Sender<IndexEvent>,
    cancel: Arc<AtomicBool>,
) {
    let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        let mut index = PhotoIndex::default();
        let mut batch = Vec::with_capacity(batch_size);
        let mut indexed_count = 0;
        if !root.is_dir() {
            let _ = send_event(&sender, IndexEvent::Finished { index }, &cancel);
            return;
        }
        for entry in WalkDir::new(&root)
            .follow_links(false)
            .into_iter()
            .filter_map(Result::ok)
        {
            if cancel.load(Ordering::Acquire) {
                let _ = sender.try_send(IndexEvent::Cancelled { indexed_count });
                return;
            }
            if !entry.file_type().is_file() {
                continue;
            }
            let Some(stem) = image_stem(entry.path()) else {
                continue;
            };
            let path = entry.path().to_path_buf();
            index.insert(stem.clone(), path.clone());
            batch.push(PhotoDiscovery { stem, path });
            indexed_count += 1;
            if batch.len() >= batch_size {
                let outgoing = std::mem::take(&mut batch);
                if !send_event(
                    &sender,
                    IndexEvent::Discovered {
                        batch: outgoing,
                        indexed_count,
                    },
                    &cancel,
                ) {
                    return;
                }
            }
        }
        if !batch.is_empty()
            && !send_event(
                &sender,
                IndexEvent::Discovered {
                    batch,
                    indexed_count,
                },
                &cancel,
            )
        {
            return;
        }
        if cancel.load(Ordering::Acquire) {
            let _ = sender.try_send(IndexEvent::Cancelled { indexed_count });
        } else {
            let _ = send_event(&sender, IndexEvent::Finished { index }, &cancel);
        }
    }));
    if outcome.is_err() {
        let _ = sender.send(IndexEvent::Failed("photo indexing worker panicked".into()));
    }
}
