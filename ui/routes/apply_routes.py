from flask import Blueprint, render_template, request, redirect, url_for, jsonify, current_app, flash

apply_bp = Blueprint("apply", __name__)


def _orch():
    return current_app.orchestrator


@apply_bp.route("/approve", methods=["POST"])
def approve():
    job_ids = request.form.getlist("job_ids")
    if not job_ids:
        flash("No jobs selected.", "info")
        return redirect(url_for("search.jobs_page"))
    _orch().approve_jobs(job_ids)
    flash(f"Approved {len(job_ids)} job(s).", "success")
    return redirect(url_for("search.jobs_page"))


@apply_bp.route("/reject", methods=["POST"])
def reject():
    job_ids = request.form.getlist("job_ids")
    if not job_ids:
        flash("No jobs selected.", "info")
        return redirect(url_for("search.jobs_page"))
    _orch().reject_jobs(job_ids)
    flash(f"Rejected {len(job_ids)} job(s).", "success")
    return redirect(url_for("search.jobs_page"))


@apply_bp.route("/apply", methods=["POST"])
def start_apply():
    orch = _orch()
    approved = orch._repo.get_by_status("approved_exploring_job_form")
    if not approved:
        flash("No approved jobs to apply to.", "info")
        return redirect(url_for("search.jobs_page"))
    started = orch.start_apply()
    if not started:
        flash("Apply already running.", "info")
    return redirect(url_for("search.jobs_page"))


@apply_bp.route("/retry-errors", methods=["POST"])
def retry_errors():
    count = _orch().retry_errors()
    flash(f"Reset {count} errored job(s) for retry.", "info")
    return redirect(url_for("search.jobs_page"))


@apply_bp.route("/status/<job_id>", methods=["GET"])
def job_status(job_id: str):
    orch = _orch()
    job = orch._repo.get_by_id(job_id)
    if not job:
        return "Job not found", 404
    errors = orch._repo.get_errors(job_id)
    proof = orch._file_manager.proof_paths(job_id)
    return render_template("status.html", job=job, errors=errors, proof=proof)


@apply_bp.route("/review/<job_id>", methods=["GET"])
def review_answers(job_id: str):
    from pathlib import Path
    orch = _orch()
    job = orch._repo.get_by_id(job_id)
    if not job:
        return "Job not found", 404
    qa_file = Path(orch._config["_base_dir"]) / "jobs" / job_id / "application" / "questions_answered.md"
    qa_pairs = _parse_qa_file(qa_file)
    return render_template("review_answers.html", job=job, qa_pairs=qa_pairs)


@apply_bp.route("/review/<job_id>/save", methods=["POST"])
def save_answers(job_id: str):
    from pathlib import Path
    orch = _orch()
    qa_file = Path(orch._config["_base_dir"]) / "jobs" / job_id / "application" / "questions_answered.md"
    questions = request.form.getlist("question")
    answers = request.form.getlist("answer")
    lines = ["# Application Questions & Answers\n"]
    for q, a in zip(questions, answers):
        if q.strip():
            lines.append(f"## {q.strip()}\n{a.strip()}\n")
    qa_file.write_text("\n".join(lines), encoding="utf-8")
    flash("Answers saved.", "success")
    return redirect(url_for("apply.review_answers", job_id=job_id))


def _parse_qa_file(qa_file) -> list[dict]:
    if not qa_file.exists():
        return []
    pairs = []
    current_q = None
    for line in qa_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current_q = line[3:].strip()
        elif current_q is not None:
            if line.strip():
                pairs.append({"question": current_q, "answer": line.strip()})
                current_q = None
    if current_q:
        pairs.append({"question": current_q, "answer": ""})
    return pairs


@apply_bp.route("/submit/<job_id>", methods=["POST"])
def submit_answers(job_id: str):
    success = _orch().submit_job(job_id)
    if success:
        flash("Application submitted successfully.", "success")
    else:
        flash("Submission failed — check status for details.", "danger")
    return redirect(url_for("search.jobs_page"))


@apply_bp.route("/reject-answers/<job_id>", methods=["POST"])
def reject_answers(job_id: str):
    _orch().reject_answers(job_id)
    flash("Answers rejected — job reset for re-extraction.", "info")
    return redirect(url_for("search.jobs_page"))
