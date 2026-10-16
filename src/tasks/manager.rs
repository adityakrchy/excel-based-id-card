//! Application-wide task coordination.
//!
//! The manager deliberately owns coordination rather than domain work. A
//! caller supplies a cooperative worker closure, receives a typed handle for
//! cancellation, and drains progress from one bounded event channel. Event
//! sends use a timeout so dropping the manager can wake workers that are
//! waiting behind a full channel before joining them.

use std::{
    collections::HashMap,
    fmt,
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc, Mutex,
    },
    thread::{self, JoinHandle},
    time::Duration,
};

use crossbeam_channel::{bounded, Receiver, SendTimeoutError, Sender, TryRecvError};

const EVENT_SEND_WAIT: Duration = Duration::from_millis(25);

/// Stable, typed identity for one submitted task.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct TaskId(u64);

impl TaskId {
    pub fn as_u64(self) -> u64 {
        self.0
    }
}

impl fmt::Display for TaskId {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "task-{}", self.0)
    }
}

/// Work categories understood by the application task surface.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum TaskKind {
    Import,
    PhotoIndex,
    Thumbnail,
    Preview,
    Generation,
    Export,
}

/// Lifecycle state retained by the manager for status queries.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TaskStatus {
    Queued,
    Running,
    Completed,
    Failed(String),
    Cancelled,
}

impl TaskStatus {
    pub fn is_terminal(&self) -> bool {
        matches!(self, Self::Completed | Self::Failed(_) | Self::Cancelled)
    }
}

/// A task's progress snapshot.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TaskProgress {
    pub completed: usize,
    pub total: Option<usize>,
    pub message: Option<String>,
}

/// Events emitted by workers through the manager's bounded channel.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TaskEvent {
    Started {
        id: TaskId,
        kind: TaskKind,
    },
    Progress {
        id: TaskId,
        kind: TaskKind,
        progress: TaskProgress,
    },
    Completed {
        id: TaskId,
        kind: TaskKind,
    },
    Failed {
        id: TaskId,
        kind: TaskKind,
        error: String,
    },
    Cancelled {
        id: TaskId,
        kind: TaskKind,
    },
}

impl TaskEvent {
    pub fn id(&self) -> TaskId {
        match self {
            Self::Started { id, .. }
            | Self::Progress { id, .. }
            | Self::Completed { id, .. }
            | Self::Failed { id, .. }
            | Self::Cancelled { id, .. } => *id,
        }
    }

    pub fn kind(&self) -> TaskKind {
        match self {
            Self::Started { kind, .. }
            | Self::Progress { kind, .. }
            | Self::Completed { kind, .. }
            | Self::Failed { kind, .. }
            | Self::Cancelled { kind, .. } => *kind,
        }
    }
}

/// A cooperative cancellation flag shared by a task and its worker.
#[derive(Clone, Debug, Default)]
pub struct TaskCancellationToken(Arc<AtomicBool>);

impl TaskCancellationToken {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn cancel(&self) {
        self.0.store(true, Ordering::Release);
    }

    pub fn is_cancelled(&self) -> bool {
        self.0.load(Ordering::Acquire)
    }
}

/// Short alias for callers that use the manager as their task abstraction.
pub type CancellationToken = TaskCancellationToken;

/// Context passed to each worker closure.
#[derive(Clone, Debug)]
pub struct TaskContext {
    id: TaskId,
    kind: TaskKind,
    token: TaskCancellationToken,
    reporter: TaskReporter,
}

impl TaskContext {
    pub fn id(&self) -> TaskId {
        self.id
    }

    pub fn kind(&self) -> TaskKind {
        self.kind
    }

    pub fn cancellation_token(&self) -> &TaskCancellationToken {
        &self.token
    }

    pub fn is_cancelled(&self) -> bool {
        self.token.is_cancelled()
    }

    pub fn is_shutdown_requested(&self) -> bool {
        self.reporter.shutdown.load(Ordering::Acquire)
    }

    /// Report progress. Returns `false` when cancellation or shutdown has
    /// started, or when the consumer has disconnected.
    pub fn report_progress(&self, completed: usize, total: Option<usize>) -> bool {
        self.report_progress_with_message(completed, total, None)
    }

    pub fn report_progress_with_message(
        &self,
        completed: usize,
        total: Option<usize>,
        message: Option<String>,
    ) -> bool {
        if self.is_cancelled() {
            return false;
        }
        self.reporter.emit_for_task(
            TaskEvent::Progress {
                id: self.id,
                kind: self.kind,
                progress: TaskProgress {
                    completed,
                    total,
                    message,
                },
            },
            &self.token,
        )
    }
}

#[derive(Clone, Debug)]
struct TaskReporter {
    sender: Sender<TaskEvent>,
    shutdown: Arc<AtomicBool>,
}

impl TaskReporter {
    fn emit(&self, mut event: TaskEvent) -> bool {
        loop {
            if self.shutdown.load(Ordering::Acquire) {
                return false;
            }
            match self.sender.send_timeout(event, EVENT_SEND_WAIT) {
                Ok(()) => return true,
                Err(SendTimeoutError::Timeout(returned)) => event = returned,
                Err(SendTimeoutError::Disconnected(_)) => return false,
            }
        }
    }

    fn emit_for_task(&self, mut event: TaskEvent, token: &TaskCancellationToken) -> bool {
        loop {
            if self.shutdown.load(Ordering::Acquire) || token.is_cancelled() {
                return false;
            }
            match self.sender.send_timeout(event, EVENT_SEND_WAIT) {
                Ok(()) => return true,
                Err(SendTimeoutError::Timeout(returned)) => event = returned,
                Err(SendTimeoutError::Disconnected(_)) => return false,
            }
        }
    }

    fn emit_terminal(&self, event: TaskEvent, token: &TaskCancellationToken) -> bool {
        // Once cancellation wins, terminal delivery is best effort. A cancelled
        // worker must not remain blocked by a full event queue while shutdown
        // waits to join it. Normal completion and failure retain backpressure.
        if token.is_cancelled() {
            return self.sender.try_send(event).is_ok();
        }
        self.emit(event)
    }
}

/// Handle for cancelling and identifying one submitted task.
#[derive(Clone, Debug)]
pub struct TaskHandle {
    id: TaskId,
    token: TaskCancellationToken,
}

impl TaskHandle {
    pub fn id(&self) -> TaskId {
        self.id
    }

    pub fn cancel(&self) {
        self.token.cancel();
    }

    pub fn is_cancelled(&self) -> bool {
        self.token.is_cancelled()
    }
}

#[derive(Debug, thiserror::Error, Clone, PartialEq, Eq)]
pub enum TaskManagerError {
    #[error("task manager is shut down")]
    Closed,
}

type TaskWorker = Box<dyn FnOnce(TaskContext) -> Result<(), String> + Send + 'static>;

/// Reusable task coordinator with a bounded event channel.
pub struct TaskManager {
    events: Receiver<TaskEvent>,
    reporter: TaskReporter,
    next_id: AtomicU64,
    shutdown: Arc<AtomicBool>,
    statuses: Arc<Mutex<HashMap<TaskId, TaskStatus>>>,
    tokens: Arc<Mutex<HashMap<TaskId, TaskCancellationToken>>>,
    workers: Mutex<Vec<JoinHandle<()>>>,
}

impl TaskManager {
    /// Create a manager whose event queue can hold at most `event_capacity`
    /// events. A zero capacity is normalized to one to keep delivery usable.
    pub fn new(event_capacity: usize) -> Self {
        let (sender, events) = bounded(event_capacity.max(1));
        let shutdown = Arc::new(AtomicBool::new(false));
        Self {
            events,
            reporter: TaskReporter {
                sender,
                shutdown: Arc::clone(&shutdown),
            },
            next_id: AtomicU64::new(1),
            shutdown,
            statuses: Arc::new(Mutex::new(HashMap::new())),
            tokens: Arc::new(Mutex::new(HashMap::new())),
            workers: Mutex::new(Vec::new()),
        }
    }

    pub fn spawn<F>(&self, kind: TaskKind, worker: F) -> Result<TaskHandle, TaskManagerError>
    where
        F: FnOnce(TaskContext) -> Result<(), String> + Send + 'static,
    {
        self.spawn_boxed(kind, Box::new(worker))
    }

    fn spawn_boxed(
        &self,
        kind: TaskKind,
        worker: TaskWorker,
    ) -> Result<TaskHandle, TaskManagerError> {
        if self.shutdown.load(Ordering::Acquire) {
            return Err(TaskManagerError::Closed);
        }
        let id = TaskId(self.next_id.fetch_add(1, Ordering::Relaxed));
        let token = TaskCancellationToken::new();
        self.statuses
            .lock()
            .expect("task statuses poisoned")
            .insert(id, TaskStatus::Queued);
        self.tokens
            .lock()
            .expect("task tokens poisoned")
            .insert(id, token.clone());

        let context = TaskContext {
            id,
            kind,
            token: token.clone(),
            reporter: self.reporter.clone(),
        };
        let statuses = Arc::clone(&self.statuses);
        let reporter = self.reporter.clone();
        let shutdown = Arc::clone(&self.shutdown);
        let worker_token = token.clone();
        let join = thread::spawn(move || {
            statuses
                .lock()
                .expect("task statuses poisoned")
                .insert(id, TaskStatus::Running);
            reporter.emit(TaskEvent::Started { id, kind });

            let outcome = if worker_token.is_cancelled() || shutdown.load(Ordering::Acquire) {
                Err("cancelled before task started".to_owned())
            } else {
                std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| worker(context)))
                    .unwrap_or_else(|_| Err("task worker panicked".to_owned()))
            };

            let (status, event) = match outcome {
                Ok(()) if worker_token.is_cancelled() => {
                    (TaskStatus::Cancelled, TaskEvent::Cancelled { id, kind })
                }
                Ok(()) => (TaskStatus::Completed, TaskEvent::Completed { id, kind }),
                Err(error)
                    if worker_token.is_cancelled() || error == "cancelled before task started" =>
                {
                    (TaskStatus::Cancelled, TaskEvent::Cancelled { id, kind })
                }
                Err(error) => (
                    TaskStatus::Failed(error.clone()),
                    TaskEvent::Failed { id, kind, error },
                ),
            };
            statuses
                .lock()
                .expect("task statuses poisoned")
                .insert(id, status);
            reporter.emit_terminal(event, &worker_token);
        });
        self.workers
            .lock()
            .expect("task workers poisoned")
            .push(join);
        Ok(TaskHandle { id, token })
    }

    pub fn cancel(&self, id: TaskId) -> bool {
        let Some(token) = self
            .tokens
            .lock()
            .expect("task tokens poisoned")
            .get(&id)
            .cloned()
        else {
            return false;
        };
        token.cancel();
        true
    }

    pub fn status(&self, id: TaskId) -> Option<TaskStatus> {
        self.statuses
            .lock()
            .expect("task statuses poisoned")
            .get(&id)
            .cloned()
    }

    pub fn event_receiver(&self) -> Receiver<TaskEvent> {
        self.events.clone()
    }

    pub fn try_recv(&self) -> Result<TaskEvent, TryRecvError> {
        self.events.try_recv()
    }

    pub fn pending_worker_count(&self) -> usize {
        self.workers
            .lock()
            .expect("task workers poisoned")
            .iter()
            .filter(|worker| !worker.is_finished())
            .count()
    }
}

impl Drop for TaskManager {
    fn drop(&mut self) {
        self.shutdown.store(true, Ordering::Release);
        for token in self.tokens.lock().expect("task tokens poisoned").values() {
            token.cancel();
        }
        let workers = std::mem::take(self.workers.get_mut().expect("task workers poisoned"));
        for worker in workers {
            let _ = worker.join();
        }
    }
}
