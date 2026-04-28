from flask import Blueprint, render_template, request, redirect, url_for, jsonify, current_app, flash

search_bp = Blueprint("search", __name__)


def _orch():
    return current_app.orchestrator


@search_bp.route("/", methods=["GET"])
def index():
    orch = _orch()
    if not orch.browser_ready():
        return redirect(url_for("search.connect_page"))
    return redirect(url_for("search.jobs_page"))


@search_bp.route("/connect", methods=["GET"])
def connect_page():
    orch = _orch()
    already_ready = orch.browser_ready()
    return render_template("connect.html", already_ready=already_ready)


@search_bp.route("/connect-linkedin", methods=["POST"])
def connect_linkedin():
    orch = _orch()
    try:
        orch.launch_browser_for_login()
        # browser is now open and on the LinkedIn login page
        return render_template("connect.html", browser_open=True, already_ready=False)
    except Exception as e:
        flash(f"Failed to open browser: {e}", "error")
        return render_template("connect.html", browser_open=False, already_ready=False)


@search_bp.route("/save-session", methods=["POST"])
def save_session():
    orch = _orch()
    try:
        orch.save_linkedin_session()
        return redirect(url_for("search.jobs_page"))
    except Exception as e:
        flash(f"Failed to save session: {e}", "error")
        return render_template("connect.html", browser_open=True, already_ready=False)


@search_bp.route("/jobs", methods=["GET"])
def jobs_page():
    orch = _orch()
    cfg = orch._config
    top_n = cfg.get("display", {}).get("top_n_jobs", 20)
    all_jobs = orch._repo.get_all()
    display_jobs = [j for j in all_jobs if j["status"] not in ("rejected", "filter_rejected")][:top_n]
    state = orch.state.snapshot()
    return render_template("jobs.html", jobs=display_jobs, state=state)


@search_bp.route("/search", methods=["POST"])
def trigger_search():
    orch = _orch()
    if not orch.browser_ready():
        return redirect(url_for("search.connect_page"))
    started = orch.start_search()
    if not started:
        flash("Search is already running.", "info")
    return redirect(url_for("search.jobs_page"))


@search_bp.route("/api/pipeline-state", methods=["GET"])
def pipeline_state():
    return jsonify(_orch().state.snapshot())


@search_bp.route("/api/jobs", methods=["GET"])
def api_jobs():
    return jsonify(_orch()._repo.get_all())


@search_bp.route("/debug/card-html", methods=["GET"])
def debug_card_html():
    """Dump raw HTML of first job card on LinkedIn search. Used to fix selectors."""
    orch = _orch()
    if not orch.browser_ready():
        return "Browser not ready", 400

    def _do(ctx, drv):
        page = ctx.new_page()
        try:
            from urllib.parse import quote
            from sites.linkedin.searcher import _is_auth_required, _dismiss_auth_popup
            import time
            url = f"https://www.linkedin.com/jobs/search/?keywords={quote('ai engineer')}&location={quote('India')}"
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            # Wait for React to render — network idle means JS has settled
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            time.sleep(2)

            if _is_auth_required(page):
                if not _dismiss_auth_popup(page):
                    return f"Auth popup not dismissed. URL: {page.url}"
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                time.sleep(2)

            # Try to wait for any job list element
            card_selectors = [
                "li.jobs-search-results__list-item",
                "li.scaffold-layout__list-item",
                "div.job-card-container",
            ]
            for sel in card_selectors:
                try:
                    page.wait_for_selector(sel, timeout=8000)
                except Exception:
                    pass
                cards = page.query_selector_all(sel)
                if cards:
                    html = cards[0].inner_html()
                    return f"selector={sel}   total_cards={len(cards)}\n\n{html}"

            # Still no cards — dump title + URL + first 8000 chars of HTML
            title = page.title()
            return f"URL: {page.url}\nTitle: {title}\n\nNo cards found. HTML:\n" + page.content()[:8000]
        finally:
            page.close()

    try:
        orch._driver.launch()
        html = orch._driver.run(_do, timeout=60)
        return f"<pre style='white-space:pre-wrap;font-size:12px'>{html}</pre>"
    except Exception as e:
        return f"Error: {e}", 500
