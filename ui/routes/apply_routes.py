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
