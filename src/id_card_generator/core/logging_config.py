"""Application logging configuration with rotating file handler and diagnostics export."""

import logging
from logging.handlers import RotatingFileHandler
import shutil
from pathlib import Path
from id_card_generator.resources.resource_loader import get_log_dir

LOG_FILE_NAME = "app.log"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 5


def setup_logging(level: int = logging.INFO) -> Path:
    """Configure root logger with console and rotating file handlers."""
    log_dir = get_log_dir()
    log_file = log_dir / LOG_FILE_NAME

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] (%(name)s:%(lineno)d): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    if not root_logger.handlers:
        # File handler
        file_handler = RotatingFileHandler(
            filename=str(log_file),
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root_logger.addHandler(file_handler)

        # Stream / Console handler
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(level)
        root_logger.addHandler(stream_handler)

    logging.info("Logging initialized. Log file: %s", log_file)
    return log_file


def get_current_log_path() -> Path:
    """Return path to current log file."""
    return get_log_dir() / LOG_FILE_NAME


def export_diagnostic_logs(target_path: Path) -> None:
    """Copy current log file to a user-selected destination."""
    src = get_current_log_path()
    if src.exists():
        shutil.copy2(src, target_path)
    else:
        target_path.write_text("No logs recorded yet.", encoding="utf-8")
