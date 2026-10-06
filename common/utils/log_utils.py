import logging
import logging.handlers
from pathlib import Path
from typing import Optional


def init(log_level: Optional[str] = None, log_file: Optional[str] = None) -> None:
    format_string = "{asctime} {levelname:<5.5} {filename: <32.32} {lineno:>4}: [{process}] {message}"
    log_format = logging.Formatter(format_string, style="{")
    log_level = "INFO" if log_level is None else log_level.upper()
    logger = logging.getLogger()
    logger.setLevel(log_level)
    # Reduce noisy Azure SDK HTTP request/response logs by default.
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("azure.core").setLevel(logging.WARNING)
    logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(
        logging.WARNING
    )
    if logger.handlers:
        for handler in logger.handlers:
            handler.setFormatter(log_format)
    else:
        # Avoid binding directly to stdout. The Functions host already captures
        # worker logs, and attaching an extra stdout handler can cause garbled
        # stream output in Azure Log Stream.
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_format)
        logger.addHandler(console_handler)
    if log_file:
        log_file_path = Path(log_file).parent
        log_file_path.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=100 * 1024 * 1024, backupCount=100
        )
        file_handler.setFormatter(log_format)
        logger.addHandler(file_handler)
