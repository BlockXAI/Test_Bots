import json
import logging
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from config import DATABASE_URL

logger = logging.getLogger(__name__)


def is_database_enabled():
    return bool(DATABASE_URL)


@contextmanager
def get_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    if not DATABASE_URL:
        logger.info("DATABASE_URL not configured, using file storage only")
        return

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS test_reports (
                        report_id TEXT PRIMARY KEY,
                        ran_at TIMESTAMPTZ NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        payload JSONB NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_test_reports_created_at
                    ON test_reports (created_at DESC)
                    """
                )
            conn.commit()
        logger.info("PostgreSQL report storage initialized")
    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL report storage: {e}")


def save_report(report_id, summary):
    if not DATABASE_URL:
        return False

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO test_reports (report_id, ran_at, payload)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (report_id)
                    DO UPDATE SET ran_at = EXCLUDED.ran_at, payload = EXCLUDED.payload
                    """,
                    (report_id, summary.get("ran_at"), Json(summary)),
                )
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to save report to PostgreSQL: {e}")
        return False


def get_report(report_id):
    if not DATABASE_URL:
        return None

    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT payload FROM test_reports WHERE report_id = %s",
                    (report_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return row["payload"]
    except Exception as e:
        logger.error(f"Failed to read report from PostgreSQL: {e}")
        return None


def list_reports(limit=20):
    if not DATABASE_URL:
        return []

    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT report_id, payload
                    FROM test_reports
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
                return [{"id": row["report_id"], "data": row["payload"]} for row in rows]
    except Exception as e:
        logger.error(f"Failed to list reports from PostgreSQL: {e}")
        return []
