import logging
import sys
import structlog
from pathlib import Path


class _TeeStream:
    """Forwards writes to two streams — used to tee stdout/stderr into the log file."""
    def __init__(self, primary, secondary):
        self._primary = primary
        self._secondary = secondary

    def write(self, data):
        self._primary.write(data)
        self._secondary.write(data)

    def flush(self):
        self._primary.flush()
        self._secondary.flush()

    def fileno(self):
        return self._primary.fileno()

    def isatty(self):
        return self._primary.isatty()


def setup_logging(log_dir: str = "logs", log_file: str = "voicenode.log") -> Path:
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    full_log_path = log_path / log_file

    fmt = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    datefmt = "%H:%M:%S"

    file_handler = logging.FileHandler(full_log_path)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    console_handler = logging.StreamHandler(sys.__stdout__)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # Tee stdout/stderr so print() calls also land in the log file.
    _log_fh = open(full_log_path, "a", buffering=1)
    sys.stdout = _TeeStream(sys.__stdout__, _log_fh)
    sys.stderr = _TeeStream(sys.__stderr__, _log_fh)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="%H:%M:%S", utc=False),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    return full_log_path


def get_log_path() -> Path:
    return Path("logs") / "voicenode.log"
