from db.repository import JobRepository

VALID_TRANSITIONS: dict[str, list[str]] = {
    "pending_initial_approval":     ["approved_exploring_job_form", "rejected"],
    "approved_exploring_job_form":  ["filling_out_answers", "error", "user_action_required", "session_expired"],
    "filling_out_answers":          ["answers_pending_approval", "error"],
    "answers_pending_approval":     ["submitting", "filling_out_answers"],
    "submitting":                   ["done", "error"],
    "done":                         [],
    "rejected":                     [],           # user-rejected, permanent
    "filter_rejected":              ["pending_initial_approval"],  # can be surfaced if config relaxed
    "error":                        ["submitting"],  # retry
    "user_action_required":         ["approved_exploring_job_form"],
    "session_expired":              ["approved_exploring_job_form"],
}


class InvalidTransitionError(Exception):
    pass


class JobManager:
    def __init__(self, repo: JobRepository):
        self._repo = repo

    def transition(self, job_id: str, new_status: str) -> None:
        current = self._repo.get_status(job_id)
        if current is None:
            raise ValueError(f"Job not found: {job_id}")
        allowed = VALID_TRANSITIONS.get(current, [])
        if new_status not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition {job_id} from '{current}' to '{new_status}'"
            )
        self._repo.update_status(job_id, new_status)

    def safe_transition(self, job_id: str, new_status: str) -> bool:
        """Like transition() but returns False instead of raising on invalid."""
        try:
            self.transition(job_id, new_status)
            return True
        except (InvalidTransitionError, ValueError):
            return False
