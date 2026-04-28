import time
import logging

from browser.driver import BrowserDriver
from sites.base import JobListing, Extractable
from sites.linkedin.searcher import _is_auth_required, _dismiss_auth_popup

logger = logging.getLogger(__name__)

_JD_SELECTORS = [
    ".show-more-less-html__markup",
    ".description__text",
    "div.jobs-description__content",
    "div.jobs-description-content__text",
    "article.jobs-description__container",
    "div#job-details",
]
_COMPANY_SELECTORS = [
    ".jobs-company__box",
    ".about-the-company",
    "[data-test-id='about-the-company']",
    "section.jobs-company",
    "div.job-details-jobs-unified-top-card__company-name",
]


class LinkedInExtractor(Extractable):
    def extract(self, listing: JobListing) -> JobListing:
        driver = BrowserDriver.get_instance()
        url = listing.url

        def _do(ctx, drv):
            page = ctx.new_page()
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                drv.solve_captcha_if_present(page)
                time.sleep(2)

                if _is_auth_required(page):
                    if not _dismiss_auth_popup(page):
                        logger.warning("Auth popup not dismissed for %s", url)
                        return "", ""
                    page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    time.sleep(2)

                jd = _extract_jd(page)
                company = _extract_company(page)
                return jd, company
            except Exception as e:
                logger.warning("Extract failed for %s: %s", url, e)
                return "", ""
            finally:
                page.close()

        jd_text, company_info = driver.run(_do)
        listing.jd_text = jd_text
        listing.company_info = company_info
        return listing


def _extract_jd(page) -> str:
    # JS click to expand "see more" — same approach as research script, bypasses overlay interception
    try:
        page.evaluate("""() => {
            const btn = document.querySelector(
                'button.show-more-less-html__button--more, button[aria-label="Click to see more description"], button.jobs-description__footer-button'
            );
            if (btn) btn.click();
        }""")
        time.sleep(0.5)
    except Exception:
        pass

    # CSS selectors
    for sel in _JD_SELECTORS:
        el = page.query_selector(sel)
        if el:
            text = el.inner_text().strip()
            if len(text) > 100:
                return text

    # JS fallback — grab any element with substantial text inside main
    try:
        return page.evaluate("""() => {
            const candidates = document.querySelectorAll(
                '.show-more-less-html__markup, .description__text, .jobs-description-content__text, main'
            );
            for (const el of candidates) {
                const t = (el.innerText || '').trim();
                if (t.length > 200) return t;
            }
            return '';
        }""") or ""
    except Exception:
        return ""


def _extract_company(page) -> str:
    for sel in _COMPANY_SELECTORS:
        el = page.query_selector(sel)
        if el:
            text = el.inner_text().strip()
            if text:
                return text

    # JS fallback — find any section with "about" heading (from research script)
    try:
        return page.evaluate("""() => {
            const sections = document.querySelectorAll('section, div[class*="company"]');
            for (const s of sections) {
                const heading = s.querySelector('h2, h3');
                if (heading && heading.innerText.toLowerCase().includes('about')) {
                    const t = s.innerText.trim();
                    if (t.length > 10) return t;
                }
            }
            return '';
        }""") or ""
    except Exception:
        return ""
