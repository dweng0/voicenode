import logging
import structlog
from pathlib import Path


def setup_logging(log_dir: str = "logs", log_file: str = "voicenode.log") -> Path:
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    full_log_path = log_path / log_file
    
    file_handler = logging.FileHandler(full_log_path, delay=True)
    file_handler.setLevel(logging.INFO)
    
    logging.basicConfig(
        handlers=[file_handler],
        level=logging.INFO,
        format=""
    )
    
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    return full_log_path


def get_log_path() -> Path:
    return Path("logs") / "voicenode.log"