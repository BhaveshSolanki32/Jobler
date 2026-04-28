import json
from flask import Blueprint, render_template, request, redirect, url_for, flash
from config import get_config, save_config

config_bp = Blueprint("config", __name__)


def _extract_filters_ui(cfg: dict) -> dict:
    """Pull human-editable values out of filters.rules for the template."""
    ui = {"yoe_max": "", "location_keywords": [], "exclude_keywords": []}
    for rule in cfg.get("filters", {}).get("rules", []):
        if rule.get("type") == "range" and rule.get("field") == "yoe_min":
            ui["yoe_max"] = rule.get("max", "")
        elif rule.get("type") == "keyword" and rule.get("field") == "location":
            ui["location_keywords"] = rule.get("values", [])
        elif rule.get("type") == "keyword" and rule.get("field") == "title":
            ui["exclude_keywords"] = rule.get("values", [])
    return ui


def _patch_rule(rules: list, match_type: str, match_field: str, updates: dict) -> None:
    """Update fields on the first matching rule in-place."""
    for rule in rules:
        if rule.get("type") == match_type and rule.get("field") == match_field:
            rule.update(updates)
            return


@config_bp.route("/config", methods=["GET"])
def config_page():
    cfg = get_config()
    filters_ui = _extract_filters_ui(cfg)
    return render_template("config.html", cfg=cfg, filters_ui=filters_ui)


@config_bp.route("/config", methods=["POST"])
def save_config_route():
    cfg = get_config()
    rules = cfg.setdefault("filters", {}).setdefault("rules", [])

    # Search settings
    terms_raw = request.form.get("search_terms", "")
    cfg["search"]["terms"] = [t.strip() for t in terms_raw.splitlines() if t.strip()]
    cfg["search"]["location"] = request.form.get("location", "India")
    cfg["search"]["max_results_per_term"] = int(request.form.get("max_results", 25))

    # LinkedIn search options
    cfg["search"].setdefault("linkedin", {})
    cfg["search"]["linkedin"]["easy_apply_only"] = "li_easy_apply" in request.form
    cfg["search"]["linkedin"]["experience_levels"] = [int(v) for v in request.form.getlist("li_levels")]
    cfg["search"]["linkedin"]["sort_by"] = request.form.get("li_sort_by", "")

    # Filters — patch the relevant rules in filters.rules
    yoe_raw = request.form.get("yoe_max", "").strip()
    if yoe_raw:
        try:
            yoe_val = float(yoe_raw)
            _patch_rule(rules, "range", "yoe_min", {"max": yoe_val})
        except ValueError:
            pass

    loc_kw = [k.strip().lower() for k in request.form.get("location_keywords", "").splitlines() if k.strip()]
    _patch_rule(rules, "keyword", "location", {"values": loc_kw})

    excl_kw = [k.strip().lower() for k in request.form.get("exclude_keywords", "").splitlines() if k.strip()]
    _patch_rule(rules, "keyword", "title", {"values": excl_kw})

    # Keyword bank
    kb_raw = request.form.get("keyword_bank", "")
    cfg["keyword_bank"] = [k.strip() for k in kb_raw.splitlines() if k.strip()]

    # Application
    cfg["application"]["resume_path"] = request.form.get("resume_path", "resume/resume.pdf")
    cfg["application"]["default_answers"]["phone"] = request.form.get("phone", "")
    cfg["application"]["default_answers"]["years_of_experience"] = request.form.get("yoe_answer", "1")
    cfg["application"]["default_answers"]["notice_period"] = request.form.get("notice_period", "immediate")
    cfg["application"]["default_answers"]["current_location"] = request.form.get("current_location", "")

    # Display
    try:
        cfg["display"]["top_n_jobs"] = int(request.form.get("top_n_jobs", 20))
    except ValueError:
        cfg["display"]["top_n_jobs"] = 20

    save_config(cfg)
    flash("Config saved.", "success")
    return redirect(url_for("config.config_page"))
