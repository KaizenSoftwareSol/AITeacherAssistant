# utils/datetime_helpers.py
"""
Utility functions for parsing datetime strings from Supabase.

Supabase returns timestamps with variable-length microseconds (1-6 digits),
which can cause issues with Python's fromisoformat(). This module provides
robust parsing functions that handle these edge cases.
"""

from datetime import datetime
from typing import Optional


def parse_datetime_safe(dt_val: Optional[str | datetime]) -> datetime:
    """
    Safely parse datetime string from Supabase, handling various formats.
    
    Handles:
    - Variable-length microseconds (1-6 digits)
    - Timezone indicators (Z, +00:00, -05:00)
    - Missing timezone (assumes UTC)
    - Already-parsed datetime objects
    
    Args:
        dt_val: Datetime string, datetime object, or None
        
    Returns:
        Parsed datetime object, or current UTC time if parsing fails
    """
    if dt_val is None:
        return datetime.utcnow()
    if isinstance(dt_val, datetime):
        return dt_val
    if not isinstance(dt_val, str):
        return datetime.utcnow()
    
    try:
        # Normalize the string: handle timezone
        normalized = dt_val.replace("Z", "+00:00")
        
        # Handle microseconds - Supabase may return variable length (1-6 digits)
        # Python's fromisoformat expects exactly 6 digits or no microseconds
        if "." in normalized:
            # Split into date/time and timezone parts
            # Find timezone indicator (last + or - before timezone)
            tz_idx = -1
            if "+" in normalized:
                tz_idx = normalized.rfind("+")
            elif normalized.count("-") >= 3:
                # Check if last - is part of timezone (e.g., -05:00)
                # Format: YYYY-MM-DDTHH:MM:SS.micro-TZ:MM
                last_dash = normalized.rfind("-")
                if last_dash > 10 and ":" in normalized[last_dash:]:
                    tz_idx = last_dash
            
            if tz_idx > 0:
                # Has timezone
                main_part = normalized[:tz_idx]
                tz_part = normalized[tz_idx:]
            else:
                # No timezone
                main_part = normalized
                tz_part = ""
            
            # Normalize microseconds in main_part
            if "." in main_part:
                date_time, micro = main_part.split(".", 1)
                # Extract only digits from microseconds
                micro_digits = "".join(c for c in micro if c.isdigit())
                # Pad or truncate to 6 digits
                micro_normalized = micro_digits[:6].ljust(6, "0")
                normalized = f"{date_time}.{micro_normalized}{tz_part}"
        
        return datetime.fromisoformat(normalized)
    except (ValueError, AttributeError) as e:
        # Fallback: try parsing with dateutil if available, or use current time
        try:
            from dateutil import parser
            return parser.parse(dt_val)
        except (ImportError, ValueError):
            # If dateutil not available or still fails, use current time
            from logger import logger
            logger.warning(f"Failed to parse datetime '{dt_val}': {e}. Using current time.")
            return datetime.utcnow()
