"""Basic logging configuration for the backend."""
import logging
import sys
from datetime import datetime
from pathlib import Path

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: str = "INFO",
    log_file: Path | None = None,
    format: str = LOG_FORMAT,
    date_format: str = LOG_DATE_FORMAT,
) -> None:
    """Configure basic logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file
        format: Custom log format string
        date_format: Custom date format string
    """
    # Create formatter
    formatter = logging.Formatter(format, date_format)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())

    # Clear existing handlers
    root_logger.handlers.clear()

    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level.upper())
    root_logger.addHandler(console_handler)

    # Add file handler if log file specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level.upper())
        root_logger.addHandler(file_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel("WARNING")
    logging.getLogger("httpcore").setLevel("WARNING")
    logging.getLogger("uvicorn").setLevel("INFO")


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    Args:
        name: Name for the logger (typically __name__ from the calling module)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)