import json
import threading
from typing import Optional
from db.schema import get_connection


def _deserialize_row(row) -> dict:
    d = dict(row)
    if d.get("slm_response") and isinstance(d["slm_response"], str):
        try:
            d["slm_response"] = json.loads(d["slm_response"])
        except Exception:
            d["slm_response"] = None
    return d


class JobRepository:
    """All SQLite ops for jobs and errors. No SQL outside this class."""

    def __init__(self):
        self._lock = threading.Lock()

    def _conn(self):
        return get_connection()

    # ── jobs ─────────────────────────────────────────────────────────────

    def save(self, job: dict) -> None:
        """
        Insert new job. If job_id already exists AND is already rejected (user or filter),
        skip it — deduplication preserves manual rejections.
        If it exists but was not yet rejected, update it (re-run scenario).
        """
        with self._lock:
            conn = self._conn()
            existing = conn.execute(
                "SELECT status FROM jobs WHERE job_id = ?", (job["job_id"],)
            ).fetchone()
            if existing:
                # User-rejected is permanent — never overwrite
                if existing["status"] == "rejected":
                    conn.close()
                    return
                # Filter-rejected can be re-evaluated on next run — fall through to UPDATE
                # Exists but not rejected — update with fresh data
                conn.execute(
                    """UPDATE jobs SET
                       jd_text=:jd_text, company_info=:company_info,
                       slm_response=:slm_response, keyword_score=:keyword_score,
                       summary=:summary, status=:status, rejection_reason=:rejection_reason
                       WHERE job_id=:job_id""",
                    {**job, "rejection_reason": job.get("rejection_reason")},
                )
            else:
                conn.execute(
                    """INSERT INTO jobs
                       (job_id, url, site, title, company, location, posted_date,
                        jd_text, company_info, keyword_score, summary, slm_response,
                        status, rejection_reason)
                       VALUES (:job_id,:url,:site,:title,:company,:location,:posted_date,
                               :jd_text,:company_info,:keyword_score,:summary,:slm_response,
                               :status,:rejection_reason)""",
                    {**job, "rejection_reason": job.get("rejection_reason")},
                )
            conn.commit()
            conn.close()

    def save_batch(self, jobs: list[dict]) -> None:
        for job in jobs:
            self.save(job)

    def get_by_id(self, job_id: str) -> Optional[dict]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        conn.close()
        return _deserialize_row(row) if row else None

    def get_by_status(self, status: str) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY keyword_score DESC",
            (status,),
        ).fetchall()
        conn.close()
        return [_deserialize_row(r) for r in rows]

    def get_all_ids(self) -> set:
        conn = self._conn()
        rows = conn.execute("SELECT job_id FROM jobs").fetchall()
        conn.close()
        return {r["job_id"] for r in rows}

    def get_user_rejected_ids(self) -> set:
        """IDs the user explicitly rejected — never re-process these."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT job_id FROM jobs WHERE status = 'rejected'"
        ).fetchall()
        conn.close()
        return {r["job_id"] for r in rows}

    def get_status(self, job_id: str) -> Optional[str]:
        conn = self._conn()
        row = conn.execute(
            "SELECT status FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        conn.close()
        return row["status"] if row else None

    def update_status(self, job_id: str, status: str) -> None:
        with self._lock:
            conn = self._conn()
            conn.execute(
                "UPDATE jobs SET status = ? WHERE job_id = ?", (status, job_id)
            )
            conn.commit()
            conn.close()

    def update_score(self, job_id: str, score: float) -> None:
        with self._lock:
            conn = self._conn()
            conn.execute(
                "UPDATE jobs SET keyword_score = ? WHERE job_id = ?", (score, job_id)
            )
            conn.commit()
            conn.close()

    def update_summary(self, job_id: str, summary: str) -> None:
        with self._lock:
            conn = self._conn()
            conn.execute(
                "UPDATE jobs SET summary = ? WHERE job_id = ?", (summary, job_id)
            )
            conn.commit()
            conn.close()

    def update_full(self, job_id: str, jd_text: str, company_info: str) -> None:
        with self._lock:
            conn = self._conn()
            conn.execute(
                "UPDATE jobs SET jd_text = ?, company_info = ? WHERE job_id = ?",
                (jd_text, company_info, job_id),
            )
            conn.commit()
            conn.close()

    def mark_rejected(self, job_id: str, reason: str = "") -> None:
        with self._lock:
            conn = self._conn()
            conn.execute(
                "UPDATE jobs SET status = 'rejected', rejection_reason = ? WHERE job_id = ?",
                (reason, job_id),
            )
            conn.commit()
            conn.close()

    def get_retry_candidates(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status IN ('error', 'filling_out_answers')"
        ).fetchall()
        conn.close()
        return [_deserialize_row(r) for r in rows]

    def get_all(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY keyword_score DESC, created_at DESC"
        ).fetchall()
        conn.close()
        return [_deserialize_row(r) for r in rows]

    # ── errors ────────────────────────────────────────────────────────────

    def log_error(self, job_id: str, step: str, reason: str) -> None:
        with self._lock:
            conn = self._conn()
            existing = conn.execute(
                "SELECT id, retry_count FROM errors WHERE job_id = ? AND step = ?",
                (job_id, step),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE errors SET retry_count = retry_count + 1, reason = ? WHERE id = ?",
                    (reason, existing["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO errors (job_id, step, reason) VALUES (?, ?, ?)",
                    (job_id, step, reason),
                )
            conn.commit()
            conn.close()

    def get_errors(self, job_id: str) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM errors WHERE job_id = ? ORDER BY created_at DESC",
            (job_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
