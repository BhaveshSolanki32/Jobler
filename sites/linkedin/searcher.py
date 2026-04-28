import time
import logging
from pathlib import Path
from urllib.parse import quote, urlencode
from slugify import slugify

from browser.driver import BrowserDriver
from sites.base import JobListing, Searchable

logger = logging.getLogger(__name__)


def _is_auth_required(page) -> bool:
    """Auth popup visible (URL may not change — LinkedIn uses an overlay modal)."""
    try:
        return page.locator("button:has-text('Continue as')").first.is_visible(timeout=800)
    except Exception:
        pass
    return any(m in page.url for m in ["/login", "/checkpoint", "/authwall"])


def _dismiss_auth_popup(page) -> bool:
    """Click Continue As button and poll until Google OAuth completes."""
    if not _is_auth_required(page):
        return True
    try:
        page.locator("button:has-text('Continue as')").first.click(timeout=3000)
    except Exception:
        return False
    for _ in range(20):
        time.sleep(1)
        if not _is_auth_required(page):
            return True
    return False


def _recover_session(page, ctx, config: dict) -> bool:
    """Click the 'Continue as [Name]' Google OAuth button to re-authenticate."""
    logger.warning("LinkedIn auth popup detected — clicking Continue As")
    try:
        btn = page.locator("button:has-text('Continue as')").first
        btn.click(timeout=5000)
        time.sleep(4)
        if not _is_auth_required(page):
            _save_session(ctx, config)
            logger.info("LinkedIn session recovered")
            return True
    except Exception as e:
        logger.warning("Recovery click failed: %s", e)
    logger.error("LinkedIn recovery failed — please reconnect manually via /connect")
    return False


def _save_session(ctx, config: dict) -> None:
    session_dir = Path(config.get("browser", {}).get("session_dir", ".sessions"))
    session_dir.mkdir(exist_ok=True)
    ctx.storage_state(path=str(session_dir / "linkedin.json"))
    logger.info("Session saved to disk")


_SEARCH_BASE = "https://www.linkedin.com/jobs/search/"

# Confirmed from saved authenticated LinkedIn HTML (April 2026)
_CARD_SELECTORS = [
    "li.scaffold-layout__list-item",
    "li.jobs-search-results__list-item",
]
_WORK_TYPE_SUFFIXES = ("(on-site)", "(hybrid)", "(remote)", "(contract)", "(part-time)", "(full-time)")


def _build_search_url(keywords: str, location: str, start: int, linkedin_cfg: dict) -> str:
    params: dict = {"keywords": keywords, "location": location, "start": start}
    if linkedin_cfg.get("easy_apply_only", False):
        params["f_AL"] = "true"
    levels = linkedin_cfg.get("experience_levels", [])
    if levels:
        params["f_E"] = "%2C".join(str(l) for l in levels)
    sort_by = linkedin_cfg.get("sort_by", "")
    if sort_by:
        params["sortBy"] = sort_by
    return _SEARCH_BASE + "?" + urlencode(params, safe="%")


def _strip_work_type(text: str) -> str:
    t = text.strip()
    lower = t.lower()
    for suffix in _WORK_TYPE_SUFFIXES:
        if lower.endswith(suffix):
            return t[: -len(suffix)].strip().rstrip(",").strip()
    return t


class LinkedInSearcher(Searchable):
    def search(self, terms: list[str], config: dict) -> list[JobListing]:
        driver = BrowserDriver.get_instance()

        def _do(ctx, drv):
            search_cfg = config.get("search", {})
            location = search_cfg.get("location", "India")
            max_per_term = search_cfg.get("max_results_per_term", 25)
            linkedin_cfg = search_cfg.get("linkedin", {})
            page_size = 25
            seen_ids: set[str] = set()
            results: list[dict] = []

            page = ctx.new_page()
            try:
                for term in terms:
                    logger.info("Searching LinkedIn: '%s' in %s (want %d)", term, location, max_per_term)
                    term_new = 0
                    start = 0

                    while term_new < max_per_term:
                        url = _build_search_url(term, location, start, linkedin_cfg)
                        try:
                            page.goto(url, timeout=30000, wait_until="domcontentloaded")
                            drv.solve_captcha_if_present(page)
                            time.sleep(1.5)

                            _scroll_to_load(page)

                            if _is_auth_required(page):
                                if not _recover_session(page, ctx, config):
                                    raise RuntimeError("LinkedIn auth recovery failed. Please reconnect via /connect.")
                                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                                time.sleep(1.5)
                                _scroll_to_load(page)
                        except Exception as e:
                            logger.warning("Page load failed start=%d term='%s': %s", start, term, e)
                            break

                        cards = _find_cards(page)
                        if not cards:
                            logger.info("No cards at start=%d for '%s'", start, term)
                            break

                        batch_new = 0
                        for card in cards:
                            if term_new >= max_per_term:
                                break
                            try:
                                data = _parse_card(card)
                                if not data:
                                    continue
                                if data["job_id"] not in seen_ids:
                                    seen_ids.add(data["job_id"])
                                    results.append(data)
                                    term_new += 1
                                    batch_new += 1
                            except Exception as e:
                                logger.debug("Card parse error: %s", e)

                        logger.info("start=%d: %d/%d new for '%s'", start, batch_new, len(cards), term)

                        if batch_new == 0 or len(cards) < page_size or batch_new < 2:
                            break

                        start += page_size

            finally:
                page.close()

            logger.info("Total unique listings collected: %d", len(results))
            return results

        raw = driver.run(_do, timeout=3600)
        return [
            JobListing(
                job_id=r["job_id"], url=r["url"], site="linkedin",
                title=r["title"], company=r["company"],
                location=r["location"], posted_date=r["posted_date"],
            )
            for r in raw
        ]


def _scroll_to_load(page, max_scrolls: int = 3) -> None:
    for _ in range(max_scrolls):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
        if _is_auth_required(page):
            return
        try:
            btn = page.query_selector("button[aria-label='See more jobs']")
            if btn:
                btn.click()
                time.sleep(1.5)
        except Exception:
            pass


def _find_cards(page) -> list:
    for sel in _CARD_SELECTORS:
        cards = page.query_selector_all(sel)
        if cards:
            return cards
    return []


def _make_job_id(title: str, company: str, location: str) -> str:
    return slugify(f"{title}_{company}_{location}", max_length=120, separator="_")


def _parse_card(card) -> dict | None:
    # Title link — a.job-card-list__title--link (confirmed from saved HTML)
    title_el = card.query_selector("a.job-card-list__title--link")
    if not title_el:
        return None

    href = title_el.get_attribute("href") or ""
    url = href.split("?")[0]
    if not url:
        return None
    if url.startswith("/"):
        url = "https://www.linkedin.com" + url

    # Title — <strong> inside the link (avoids duplicate text from aria-hidden spans)
    strong = title_el.query_selector("strong")
    title = strong.inner_text().strip() if strong else title_el.inner_text().split("\n")[0].strip()
    if not title:
        return None

    # Company — div.artdeco-entity-lockup__subtitle (confirmed from saved HTML)
    company = ""
    co_el = card.query_selector("div.artdeco-entity-lockup__subtitle")
    if co_el:
        company = co_el.inner_text().strip()

    # Location — div.artdeco-entity-lockup__caption li span (confirmed from saved HTML)
    location = ""
    loc_el = card.query_selector("div.artdeco-entity-lockup__caption li span")
    if loc_el:
        location = _strip_work_type(loc_el.inner_text().strip())

    posted = ""
    time_el = card.query_selector("time")
    if time_el:
        posted = time_el.get_attribute("datetime") or time_el.inner_text().strip()

    return {
        "job_id": _make_job_id(title, company, location),
        "url": url,
        "title": title,
        "company": company,
        "location": location,
        "posted_date": posted,
    }
