//! Bounded, cancellable thumbnail work. Full-resolution decoding is lazy and
//! happens only in this task worker, never while building a photo index.

use std::{
    collections::{HashMap, VecDeque},
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering},
        Arc, Condvar, Mutex,
    },
    thread::{self, JoinHandle},
    time::Duration,
};

use crossbeam_channel::{bounded, Receiver, RecvTimeoutError, Sender, TryRecvError};

const WORKER_POLL_INTERVAL: Duration = Duration::from_millis(25);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ThumbnailPriority {
    Visible,
    Background,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RgbaThumbnail {
    pub width: u32,
    pub height: u32,
    pub pixels: Vec<u8>,
}

impl RgbaThumbnail {
    pub fn byte_len(&self) -> usize {
        self.pixels.len()
    }
}

#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum ThumbnailError {
    #[error("thumbnail request was cancelled")]
    Cancelled,
    #[error("thumbnail dimensions must be greater than zero")]
    InvalidDimensions,
    #[error("thumbnail decode failed for {path}: {message}")]
    Decode { path: PathBuf, message: String },
}

pub type ThumbnailResult = Result<RgbaThumbnail, ThumbnailError>;

#[derive(Debug, Clone, Hash, PartialEq, Eq)]
struct ThumbnailKey {
    path: PathBuf,
    max_dimension: u32,
}

#[derive(Debug)]
struct Subscriber {
    sender: Sender<ThumbnailResult>,
    cancelled: Arc<AtomicBool>,
}

struct QueuedThumbnail {
    key: ThumbnailKey,
}

type JobMap = HashMap<ThumbnailKey, Vec<Subscriber>>;

#[derive(Debug)]
struct CacheEntry {
    thumbnail: RgbaThumbnail,
    bytes: usize,
}

#[derive(Debug)]
struct ThumbnailCache {
    max_bytes: usize,
    bytes: usize,
    entries: HashMap<ThumbnailKey, CacheEntry>,
    lru: VecDeque<ThumbnailKey>,
}

impl ThumbnailCache {
    fn new(max_bytes: usize) -> Self {
        Self {
            max_bytes,
            bytes: 0,
            entries: HashMap::new(),
            lru: VecDeque::new(),
        }
    }

    fn get(&mut self, key: &ThumbnailKey) -> Option<RgbaThumbnail> {
        let value = self.entries.get(key).map(|entry| entry.thumbnail.clone());
        if value.is_some() {
            self.touch(key);
        }
        value
    }

    fn insert(&mut self, key: ThumbnailKey, thumbnail: RgbaThumbnail) {
        let bytes = thumbnail.byte_len();
        if bytes > self.max_bytes {
            return;
        }
        if let Some(previous) = self.entries.remove(&key) {
            self.bytes = self.bytes.saturating_sub(previous.bytes);
            self.lru.retain(|item| item != &key);
        }
        self.entries
            .insert(key.clone(), CacheEntry { thumbnail, bytes });
        self.bytes += bytes;
        self.lru.push_back(key);
        while self.bytes > self.max_bytes {
            let Some(oldest) = self.lru.pop_front() else {
                break;
            };
            if let Some(entry) = self.entries.remove(&oldest) {
                self.bytes = self.bytes.saturating_sub(entry.bytes);
            }
        }
    }

    fn touch(&mut self, key: &ThumbnailKey) {
        self.lru.retain(|item| item != key);
        self.lru.push_back(key.clone());
    }
}

pub struct ThumbnailRequest {
    id: u64,
    receiver: Receiver<ThumbnailResult>,
    cancelled: Arc<AtomicBool>,
    cancel_sender: Sender<ThumbnailResult>,
}

impl ThumbnailRequest {
    pub fn id(&self) -> u64 {
        self.id
    }

    pub fn cancel(&self) {
        if !self.cancelled.swap(true, Ordering::AcqRel) {
            let _ = self.cancel_sender.try_send(Err(ThumbnailError::Cancelled));
        }
    }

    pub fn is_cancelled(&self) -> bool {
        self.cancelled.load(Ordering::Acquire)
    }

    pub fn try_recv(&self) -> Result<ThumbnailResult, crossbeam_channel::TryRecvError> {
        self.receiver.try_recv()
    }

    pub fn recv_timeout(&self, timeout: Duration) -> Result<ThumbnailResult, RecvTimeoutError> {
        self.receiver.recv_timeout(timeout)
    }
}

pub struct ThumbnailQueue {
    visible_sender: Sender<QueuedThumbnail>,
    background_sender: Sender<QueuedThumbnail>,
    jobs: Arc<Mutex<JobMap>>,
    cache: Arc<Mutex<ThumbnailCache>>,
    pending: Arc<AtomicUsize>,
    capacity: usize,
    next_id: AtomicU64,
    shutdown: Arc<AtomicBool>,
    wake: Arc<(Mutex<bool>, Condvar)>,
    worker: Option<JoinHandle<()>>,
}

impl ThumbnailQueue {
    pub fn new(max_pending: usize, cache_bytes: usize) -> Self {
        let capacity = max_pending.max(1);
        let (visible_sender, visible_receiver) = bounded(capacity);
        let (background_sender, background_receiver) = bounded(capacity);
        let jobs = Arc::new(Mutex::new(HashMap::new()));
        let cache = Arc::new(Mutex::new(ThumbnailCache::new(cache_bytes)));
        let pending = Arc::new(AtomicUsize::new(0));
        let shutdown = Arc::new(AtomicBool::new(false));
        let wake = Arc::new((Mutex::new(false), Condvar::new()));
        let worker = Some(thread::spawn({
            let worker_jobs = Arc::clone(&jobs);
            let worker_cache = Arc::clone(&cache);
            let worker_pending = Arc::clone(&pending);
            let worker_shutdown = Arc::clone(&shutdown);
            let worker_wake = Arc::clone(&wake);
            move || {
                worker_loop(
                    visible_receiver,
                    background_receiver,
                    worker_jobs,
                    worker_cache,
                    worker_pending,
                    worker_shutdown,
                    worker_wake,
                )
            }
        }));
        Self {
            visible_sender,
            background_sender,
            jobs,
            cache,
            pending,
            capacity,
            next_id: AtomicU64::new(1),
            shutdown,
            wake,
            worker,
        }
    }

    pub fn request(
        &self,
        path: impl AsRef<Path>,
        max_dimension: u32,
        priority: ThumbnailPriority,
    ) -> Result<ThumbnailRequest, ThumbnailQueueError> {
        if max_dimension == 0 {
            return Err(ThumbnailQueueError::InvalidDimensions);
        }
        if self.shutdown.load(Ordering::Acquire) {
            return Err(ThumbnailQueueError::Closed);
        }
        let key = ThumbnailKey {
            path: path.as_ref().to_path_buf(),
            max_dimension,
        };
        let (sender, receiver) = bounded(1);
        let cancelled = Arc::new(AtomicBool::new(false));
        let request = ThumbnailRequest {
            id: self.next_id.fetch_add(1, Ordering::Relaxed),
            receiver,
            cancelled: Arc::clone(&cancelled),
            cancel_sender: sender.clone(),
        };

        if let Some(thumbnail) = self
            .cache
            .lock()
            .expect("thumbnail cache poisoned")
            .get(&key)
        {
            let _ = sender.send(Ok(thumbnail));
            return Ok(request);
        }

        let mut jobs = self.jobs.lock().expect("thumbnail jobs poisoned");
        if let Some(subscribers) = jobs.get_mut(&key) {
            subscribers.push(Subscriber { sender, cancelled });
            return Ok(request);
        }
        if !reserve_slot(&self.pending, self.capacity) {
            return Err(ThumbnailQueueError::Full);
        }
        jobs.insert(key.clone(), vec![Subscriber { sender, cancelled }]);
        let queued = QueuedThumbnail { key: key.clone() };
        let result = match priority {
            ThumbnailPriority::Visible => self.visible_sender.try_send(queued),
            ThumbnailPriority::Background => self.background_sender.try_send(queued),
        };
        if result.is_err() {
            jobs.remove(&key);
            self.pending.fetch_sub(1, Ordering::AcqRel);
            return Err(ThumbnailQueueError::Full);
        }
        drop(jobs);
        self.wake.1.notify_one();
        Ok(request)
    }

    pub fn pending_count(&self) -> usize {
        self.pending.load(Ordering::Acquire)
    }

    pub fn cache_len(&self) -> usize {
        self.cache
            .lock()
            .expect("thumbnail cache poisoned")
            .entries
            .len()
    }

    pub fn cache_bytes(&self) -> usize {
        self.cache.lock().expect("thumbnail cache poisoned").bytes
    }
}

impl Drop for ThumbnailQueue {
    fn drop(&mut self) {
        self.shutdown.store(true, Ordering::Release);
        self.wake.1.notify_one();
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum ThumbnailQueueError {
    #[error("thumbnail queue is full")]
    Full,
    #[error("thumbnail queue is closed")]
    Closed,
    #[error("thumbnail dimensions must be greater than zero")]
    InvalidDimensions,
}

fn reserve_slot(pending: &AtomicUsize, capacity: usize) -> bool {
    let mut current = pending.load(Ordering::Acquire);
    loop {
        if current >= capacity {
            return false;
        }
        match pending.compare_exchange_weak(
            current,
            current + 1,
            Ordering::AcqRel,
            Ordering::Acquire,
        ) {
            Ok(_) => return true,
            Err(next) => current = next,
        }
    }
}

fn next_task(
    visible: &Receiver<QueuedThumbnail>,
    background: &Receiver<QueuedThumbnail>,
    wake: &Arc<(Mutex<bool>, Condvar)>,
    shutdown: &AtomicBool,
) -> Option<QueuedThumbnail> {
    loop {
        if shutdown.load(Ordering::Acquire) {
            return None;
        }
        match visible.try_recv() {
            Ok(task) => return Some(task),
            Err(TryRecvError::Disconnected) => return None,
            Err(TryRecvError::Empty) => {}
        }
        match background.try_recv() {
            Ok(task) => return Some(task),
            Err(TryRecvError::Disconnected) => return None,
            Err(TryRecvError::Empty) => {}
        }
        let guard = wake.0.lock().expect("thumbnail wake poisoned");
        let _ = wake
            .1
            .wait_timeout(guard, WORKER_POLL_INTERVAL)
            .expect("thumbnail wake poisoned");
    }
}

fn worker_loop(
    visible: Receiver<QueuedThumbnail>,
    background: Receiver<QueuedThumbnail>,
    jobs: Arc<Mutex<JobMap>>,
    cache: Arc<Mutex<ThumbnailCache>>,
    pending: Arc<AtomicUsize>,
    shutdown: Arc<AtomicBool>,
    wake: Arc<(Mutex<bool>, Condvar)>,
) {
    while let Some(task) = next_task(&visible, &background, &wake, &shutdown) {
        pending.fetch_sub(1, Ordering::AcqRel);
        let has_subscribers = jobs
            .lock()
            .expect("thumbnail jobs poisoned")
            .contains_key(&task.key);
        if !has_subscribers {
            continue;
        }
        let all_cancelled = jobs
            .lock()
            .expect("thumbnail jobs poisoned")
            .get(&task.key)
            .map(|subscribers| {
                subscribers
                    .iter()
                    .all(|subscriber| subscriber.cancelled.load(Ordering::Acquire))
            })
            .unwrap_or(true);
        let result = if all_cancelled {
            Err(ThumbnailError::Cancelled)
        } else {
            decode_thumbnail(&task.key)
        };
        if let Ok(thumbnail) = &result {
            cache
                .lock()
                .expect("thumbnail cache poisoned")
                .insert(task.key.clone(), thumbnail.clone());
        }
        let subscribers = jobs
            .lock()
            .expect("thumbnail jobs poisoned")
            .remove(&task.key)
            .unwrap_or_default();
        for subscriber in subscribers {
            let value = if subscriber.cancelled.load(Ordering::Acquire) {
                Err(ThumbnailError::Cancelled)
            } else {
                result.clone()
            };
            let _ = subscriber.sender.try_send(value);
        }
    }
}

fn decode_thumbnail(key: &ThumbnailKey) -> ThumbnailResult {
    match image::open(&key.path) {
        Ok(image) => {
            let image = image
                .thumbnail(key.max_dimension, key.max_dimension)
                .to_rgba8();
            Ok(RgbaThumbnail {
                width: image.width(),
                height: image.height(),
                pixels: image.into_raw(),
            })
        }
        Err(error) => Err(ThumbnailError::Decode {
            path: key.path.clone(),
            message: error.to_string(),
        }),
    }
}
