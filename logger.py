# logger.py

import os
import sys

from loguru import logger

# Create a directory for logs if it doesn't exist
log_dir = "logs"

if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Set up log rotation (rotate logs after 10 MB, keeping 3 backups)
log_file = os.path.join(log_dir, "app.log")
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
log_to_stdout = os.getenv("LOG_TO_STDOUT", "true").lower() == "true"


def _inject_request_id(record):
    try:
        from services.request_context import get_request_id

        record["extra"]["request_id"] = get_request_id() or "-"
    except Exception:
        record["extra"]["request_id"] = "-"


logger.remove()
logger.configure(patcher=_inject_request_id)

logger.add(
    log_file,
    rotation="10 MB",
    retention="3 days",
    compression="zip",
    level=log_level,
    enqueue=True,
    backtrace=False,
    diagnose=False,
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | rid={extra[request_id]} | {name}:{function}:{line} | {message}",
)

if log_to_stdout:
    logger.add(
        sys.stdout,
        level=log_level,
        enqueue=True,
        backtrace=False,
        diagnose=False,
        format="{time:HH:mm:ss} | {level} | rid={extra[request_id]} | {message}",
    )

# Optionally, add additional handlers for other logging destinations
# logger.add(
#     "some_other_log.log",
#     level="ERROR"
# )  # Example: Log errors to a separate file

# You can now import and use this logger in any other part of your FastAPI app
