#!/usr/bin/env python3
"""
Migration runner for AITeacherAssistant.

Tracks applied migrations in a `schema_migrations` table and runs any
SQL files in the `migrations/` folder that haven't been applied yet,
in filename order.

Usage:
    python scripts/run_migrations.py

Requires SUPABASE_DB_URL in your .env or environment:
    SUPABASE_DB_URL=postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres

Get the URL from: Supabase Dashboard > Project Settings > Database >
                  Connection string > URI  (use "Session" mode, port 5432)
"""

import sys
from pathlib import Path

# Allow running from repo root or scripts/ directory
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
from settings import settings
from logger import logger

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"

CREATE_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   TEXT        PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def get_connection():
    db_url = settings.SUPABASE_DB_URL
    if not db_url:
        raise RuntimeError(
            "SUPABASE_DB_URL is not set.\n"
            "Get it from: Supabase Dashboard > Project Settings > Database > "
            "Connection string > URI (Session mode, port 5432)\n"
            "Then add it to your .env file:\n"
            "  SUPABASE_DB_URL=postgresql://postgres:[password]@db.[ref].supabase.co:5432/postgres"
        )
    return psycopg2.connect(db_url)


def run_migrations():
    conn = get_connection()
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            # Ensure tracking table exists
            cur.execute(CREATE_TRACKING_TABLE)
            conn.commit()

            # Fetch already-applied migrations
            cur.execute("SELECT filename FROM schema_migrations ORDER BY filename")
            applied = {row[0] for row in cur.fetchall()}

            # Collect SQL files sorted by name (numeric prefix keeps order)
            sql_files = sorted(
                f for f in MIGRATIONS_DIR.glob("*.sql")
                if f.name not in applied
            )

            if not sql_files:
                logger.info("All migrations are up to date.")
                return

            for sql_file in sql_files:
                logger.info(f"Applying migration: {sql_file.name}")
                sql = sql_file.read_text(encoding="utf-8")
                try:
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (filename) VALUES (%s)",
                        (sql_file.name,),
                    )
                    conn.commit()
                    logger.info(f"  OK: {sql_file.name}")
                except Exception as exc:
                    conn.rollback()
                    logger.error(f"  FAILED: {sql_file.name} — {exc}")
                    raise

        logger.info(f"Migrations complete. Applied {len(sql_files)} file(s).")

    finally:
        conn.close()


if __name__ == "__main__":
    run_migrations()
