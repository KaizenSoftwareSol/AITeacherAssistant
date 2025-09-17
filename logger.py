# logger.py

import os

from loguru import logger

# Create a directory for logs if it doesn't exist
log_dir = "logs"

if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Set up log rotation (rotate logs after 10 MB, keeping 3 backups)
log_file = os.path.join(log_dir, "app.log")

logger.add(
    log_file, rotation="10 MB", retention="3 days", compression="zip", level="DEBUG"
)
# logger.add(sys.stdout, level="INFO")  # Log to console with INFO level for stdout

# Optionally, add additional handlers for other logging destinations
# logger.add(
#     "some_other_log.log",
#     level="ERROR"
# )  # Example: Log errors to a separate file

# You can now import and use this logger in any other part of your FastAPI app

