import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id          TEXT PRIMARY KEY,
    url             TEXT NOT NULL,
    site            TEXT NOT NULL DEFAULT 'linkedin',
    title           TEXT,
    company         TEXT,
    location        TEXT,
    posted_date     TEXT,
    jd_text         TEXT,
    company_info    TEXT,
    keyword_score   REAL DEFAULT 0.0,
    summary         TEXT,
    slm_response    TEXT,
    status          TEXT NOT NULL DEFAULT 'pending_initial_approval',
    rejection_reason TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS errors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT NOT NULL REFERENCES jobs(job_id),
    step            TEXT NOT NULL,
    reason          TEXT,
    retry_count     INTEGER DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER IF NOT EXISTS jobs_updated_at
AFTER UPDATE ON jobs
FOR EACH ROW
BEGIN
    UPDATE jobs SET updated_at = CURRENT_TIMESTAMP WHERE job_id = OLD.job_id;
END;
"""

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.close()
