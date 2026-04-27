#!/usr/bin/env python3
"""
Run script for AI Teacher application
"""

import asyncio
import sys
from pathlib import Path

import uvicorn

if __name__ == "__main__":
    # Ensure logs directory exists
    Path("logs").mkdir(exist_ok=True)

    # Avoid noisy Proactor connection-reset callbacks on Windows dev machines.
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Run the application
    uvicorn.run("main:app", host="0.0.0.0", port=8001, log_level="info")
