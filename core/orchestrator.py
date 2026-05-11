import threading
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from config import get_config
from db.repository import JobRepository
from db.schema import init_db
from core.job_manager import JobManager
from core.file_manager import FileManager
from filters.engine import FilterEngine
from llm.client import LLMClient
from browser.driver import BrowserDriver
from sites.base import JobListing
import sites.linkedin  # registers LinkedIn in SiteSkillRegistry

logger = logging.getLogger(__name__)


@dataclass
class PipelineState:
    status: str = "idle"          # idle | searching | filtering | done | error | applying
    message: str = ""
    progress: int = 0             # 0-100
    found: int = 0
    passed_filter: int = 0
    applied: int = 0
    error: Optional[str] = None
    lock: threading.Lock = field(default_factory=threading.Lock, compare=False, repr=False)

    def update(self, **kwargs) -> None:
        with self.lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "status": self.status,
                "message": self.message,
                "progress": self.progress,
                "found": self.found,
                "passed_filter": self.passed_filter,
                "applied": self.applied,
                "error": self.error,
            }


class Orchestrator:
    def __init__(self):
        init_db()
        self._config = get_config()
        base_dir = self._config["_base_dir"]
        self._repo = JobRepository()
        self._job_manager = JobManager(self._repo)
        self._file_manager = FileManager(str(Path(base_dir) / "jobs"))
        self._filter_engine = FilterEngine()
        self._llm = LLMClient(self._config)
        self._driver = BrowserDriver.init_driver(self._config)
        self.state = PipelineState()
        self._search_thread: Optional[threading.Thread] = None
        self._apply_thread: Optional[threading.Thread] = None

    def reload_config(self) -> None:
        self._config = get_config()
        self._llm = LLMClient(self._config)

    # ── Browser session ────────────────────────────────────────────────

    def launch_browser_for_login(self) -> None:
        """Open browser so user can log in to LinkedIn manually."""
        self._driver.open_login_page("https://www.linkedin.com/login")
        # Page stays open — user logs in. They click "Save Session" in UI afterwards.

    def save_linkedin_session(self) -> None:
        self._driver.save_session("linkedin")

    def browser_ready(self) -> bool:
        return self._driver.has_session("linkedin")

    # ── Search pipeline ────────────────────────────────────────────────

    def start_search(self) -> bool:
        """Kick off search in background thread. Returns False if already running."""
        if self._search_thread and self._search_thread.is_alive():
            return False
        self._search_thread = threading.Thread(
            target=self._run_search, daemon=True
        )
        self._search_thread.start()
        return True

    def _run_search(self) -> None:
        self.state.update(status="searching", message="Starting browser...", progress=5, error=None)
        try:
            self._driver.launch()  # no-op if already running; submits to browser thread

            from sites.linkedin import LinkedInSkill
            skill = LinkedInSkill()

            terms = self._config["search"]["terms"]
            self.state.update(message=f"Searching {len(terms)} terms on LinkedIn...", progress=10)

            raw_listings = skill.search(terms, self._config)
            self.state.update(found=len(raw_listings), message=f"Found {len(raw_listings)} listings. Pre-filtering...", progress=25)

            # Only skip jobs the USER explicitly rejected
            user_rejected_ids = self._repo.get_user_rejected_ids()
            new_listings = [j for j in raw_listings if j.job_id not in user_rejected_ids]
            logger.info("%d listings after dedup (%d skipped as user-rejected)",
                        len(new_listings), len(raw_listings) - len(new_listings))

            # Stage 1 filter — job-level fields only (title, location).
            # SLM fields are all null so source="slm" rules pass via null_passes.
            pre_result = self._filter_engine.run(new_listings, self._config)
            for job, reason in pre_result.rejected:
                self._repo.save({**job.to_db_dict(), "status": "filter_rejected", "rejection_reason": reason})
                logger.info("Pre-filter rejected '%s': %s", job.title, reason)

            to_extract = pre_result.passing
            self.state.update(
                message=f"{len(to_extract)} listings passed pre-filter. Extracting details...",
                progress=30,
            )

            total_new = len(to_extract)
            enriched: list[JobListing] = []
            for i, listing in enumerate(to_extract):
                # Step 1: extract JD text from LinkedIn
                self.state.update(
                    message=f"Extracting JD {i+1}/{total_new}: {listing.title}",
                    progress=30 + int(25 * (i + 1) / max(total_new, 1)),
                )
                listing = skill.extract(listing)

                # Step 2: LLM extracts structured filter fields (the SLM response)
                self.state.update(
                    message=f"Analysing {i+1}/{total_new}: {listing.title}",
                    progress=55 + int(15 * (i + 1) / max(total_new, 1)),
                )
                listing.slm_response = self._llm.extract_jd_fields(listing.jd_text, listing.title)
                logger.info(
                    "SLM for '%s': %s", listing.title, listing.slm_response
                )
                enriched.append(listing)

            self.state.update(message="Filtering and ranking...", progress=72)
            result = self._filter_engine.run(enriched, self._config)

            # Save filter-rejected — distinct from user-rejected so re-runs can re-evaluate
            for job, reason in result.rejected:
                self._repo.save({**job.to_db_dict(), "status": "filter_rejected", "rejection_reason": reason})
                logger.info("Filtered out '%s': %s | slm=%s", job.title, reason, job.slm_response)

            # Save passing jobs and write files
            for job in result.passing:
                self._repo.save(job.to_db_dict())
                self._file_manager.create_job_folder(job.to_db_dict())
                self._file_manager.write_jd(job.job_id, job.jd_text)
                self._file_manager.write_company_info(job.job_id, job.company_info)

            # Generate summaries for passing jobs
            self.state.update(message="Generating summaries...", progress=85)
            for job in result.passing:
                summary = self._llm.summarize_job(job.jd_text, job.title, job.company)
                self._repo.update_summary(job.job_id, summary)
                self._repo.update_score(job.job_id, job.keyword_score)

            self.state.update(
                status="done",
                message=f"Search complete. {len(result.passing)} jobs ready for review.",
                progress=100,
                passed_filter=len(result.passing),
            )

        except Exception as e:
            logger.exception("Search pipeline failed")
            self.state.update(status="error", message="Search failed.", error=str(e))

    # ── User approval ─────────────────────────────────────────────────

    def approve_jobs(self, job_ids: list[str]) -> None:
        for job_id in job_ids:
            self._job_manager.safe_transition(job_id, "approved_exploring_job_form")

    def reject_jobs(self, job_ids: list[str]) -> None:
        for job_id in job_ids:
            self._repo.mark_rejected(job_id, "user_rejected")
            self._file_manager.delete_job_folder(job_id)

    # ── Apply pipeline ─────────────────────────────────────────────────

    def start_apply(self) -> bool:
        if self._apply_thread and self._apply_thread.is_alive():
            return False
        self._apply_thread = threading.Thread(
            target=self._run_apply, daemon=True
        )
        self._apply_thread.start()
        return True

    def _run_apply(self) -> None:
        self.state.update(status="applying", message="Starting applications...", progress=0, error=None)
        try:
            self._driver.launch()

            import browser_agent.agent as agent

            approved = self._repo.get_by_status("approved_exploring_job_form")
            total = len(approved)
            if total == 0:
                self.state.update(status="done", message="No approved jobs to apply to.", progress=100)
                return

            session_dir = Path(self._config["_base_dir"]) / self._config.get("browser", {}).get("session_dir", ".sessions")

            for i, job_dict in enumerate(approved):
                job_id = job_dict["job_id"]
                url = job_dict["url"]
                self.state.update(
                    message=f"Extracting form {i+1}/{total}: {job_dict['title']} at {job_dict['company']}",
                    progress=int(100 * i / total),
                )
                self._job_manager.safe_transition(job_id, "filling_out_answers")

                cfg = {**self._config}
                session_file = agent.resolve_session(url, session_dir)
                if session_file:
                    cfg['_session_file'] = str(session_file)

                skill = agent.resolve_skill(url, 'EXTRACT')
                task = agent.extract_task(url)
                result = agent.run(task, skill, cfg)

                if result.success:
                    app_dir = Path(self._config["_base_dir"]) / "jobs" / job_id / "application"
                    app_dir.mkdir(parents=True, exist_ok=True)
                    if result.collected:
                        lines = ['# Application Questions\n']
                        for q in dict.fromkeys(result.collected):
                            lines.append(f'## {q}\n\n')
                        (app_dir / 'questions.md').write_text('\n'.join(lines), encoding='utf-8')
                        logger.info("Saved %d questions for %s", len(result.collected), job_id)
                    self._job_manager.safe_transition(job_id, "answers_pending_approval")
                    logger.info("Extracted form for %s — awaiting user review", job_id)
                else:
                    self._repo.log_error(job_id, "extract", result.error or "unknown")
                    self._repo.update_status(job_id, "error")
                    logger.warning("Extract failed for %s: %s", job_id, result.error)

            self.state.update(
                status="done",
                message=f"Form extraction done. {total} job(s) processed.",
                progress=100,
            )

        except Exception as e:
            logger.exception("Apply pipeline failed")
            self.state.update(status="error", message="Apply failed.", error=str(e))

    # ── Submit approved answers ────────────────────────────────────────

    def submit_job(self, job_id: str) -> bool:
        job_dict = self._repo.get_by_id(job_id)
        if not job_dict:
            return False
        self._driver.launch()

        import browser_agent.agent as agent

        url = job_dict["url"]
        session_dir = Path(self._config["_base_dir"]) / self._config.get("browser", {}).get("session_dir", ".sessions")
        qa_file = Path(self._config["_base_dir"]) / "jobs" / job_id / "application" / "questions_answered.md"

        if not qa_file.exists() or not qa_file.read_text(encoding='utf-8').strip():
            self._repo.log_error(job_id, "submit", "questions_answered.md missing")
            return False

        cfg = {**self._config}
        session_file = agent.resolve_session(url, session_dir)
        if session_file:
            cfg['_session_file'] = str(session_file)

        skill = agent.resolve_skill(url, 'SUBMIT')
        task = agent.submit_task(url, qa_file.read_text(encoding='utf-8'))
        result = agent.run(task, skill, cfg)

        if result.success:
            self._job_manager.safe_transition(job_id, "submitting")
            self._job_manager.safe_transition(job_id, "done")
            logger.info("Submitted %s", job_id)
            return True
        else:
            self._repo.log_error(job_id, "submit", result.error or "unknown")
            self._repo.update_status(job_id, "error")
            logger.warning("Submit failed for %s: %s", job_id, result.error)
            return False

    def reject_answers(self, job_id: str) -> None:
        self._repo.update_status(job_id, "approved_exploring_job_form")

    # ── Retry errored jobs ─────────────────────────────────────────────

    def retry_errors(self) -> int:
        candidates = self._repo.get_retry_candidates()
        for job in candidates:
            self._repo.update_status(job["job_id"], "approved_exploring_job_form")
        return len(candidates)
