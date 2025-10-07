#!/usr/bin/env python3
"""
Run script for AI Teacher application
"""

from pathlib import Path

import uvicorn

if __name__ == "__main__":
    # Ensure logs directory exists
    Path("logs").mkdir(exist_ok=True)

    # Run the application
    uvicorn.run("main:app", host="0.0.0.0", port=8001, log_level="info")
