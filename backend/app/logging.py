import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict


class StructuredJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Include custom fields if present in extra
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            for key, val in record.extra.items():
                if key not in log_data:
                    log_data[key] = val

        # Include exception details if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def setup_logging(log_level: str = "INFO") -> None:
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Avoid duplicate handlers
    if logger.handlers:
        for handler in logger.handlers:
            logger.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(StructuredJsonFormatter())
    logger.addHandler(handler)

    # Configure specific sub-loggers if needed
    for uvicorn_logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        uv_logger = logging.getLogger(uvicorn_logger_name)
        uv_logger.handlers = []
        uv_logger.propagate = True
