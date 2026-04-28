import time
import logging
from pathlib import Path

from browser.driver import BrowserDriver
from sites.base import JobListing, Applyable, ApplicationResult
from sites.linkedin.searcher import _is_auth_required, _dismiss_auth_popup

logger = logging.getLogger(__name__)

_JOBLER_ROOT = Path(__file__).resolve().parent.parent.parent

_LABEL_MAP = {
    "phone": "phone",
    "mobile": "phone",
    "years of experience": "years_of_experience",
    "year of experience": "years_of_experience",
    "experience": "years_of_experience",
    "current ctc": "current_ctc",
    "current salary": "current_ctc",
    "expected ctc": "expected_ctc",
    "expected salary": "expected_ctc",
    "notice period": "notice_period",
    "current location": "current_location",
    "location": "current_location",
    "city": "current_location",
}


def _answer_for_label(label: str, answers: dict) -> str | None:
    lbl = label.lower().strip()
    for fragment, key in _LABEL_MAP.items():
        if fragment in lbl:
            return answers.get(key, "")
    return None


class LinkedInEasyApplier(Applyable):
    def apply(
        self, listing: JobListing, answers: dict, resume_path: str
    ) -> ApplicationResult:
        driver = BrowserDriver.get_instance()
        job_id = listing.job_id
        url = listing.url
        proof_dir = _JOBLER_ROOT / "jobs" / job_id / "proof"
        proof_dir.mkdir(parents=True, exist_ok=True)

        def _do(ctx, drv) -> dict:
            screenshots: list[str] = []
            page = ctx.new_page()
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                drv.solve_captcha_if_present(page)
                time.sleep(2)

                if _is_auth_required(page):
                    if not _dismiss_auth_popup(page):
                        return {"success": False, "screenshots": screenshots, "error": "auth_required"}
                    page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    time.sleep(2)

                btn = _find_easy_apply_button(page)
                if not btn:
                    return {"success": False, "screenshots": screenshots, "error": "no_easy_apply_button"}

                btn.click()
                time.sleep(2)

                ss = drv.screenshot(page, str(proof_dir / "01_easy_apply_opened.png"))
                screenshots.append(ss)

                if "linkedin.com" not in page.url:
                    return {"success": False, "screenshots": screenshots, "error": "redirected_to_external_site"}

                page_num = 2
                while page_num <= 12:
                    _fill_page(page, answers, resume_path)
                    time.sleep(1)
                    ss = drv.screenshot(page, str(proof_dir / f"{page_num:02d}_form_page.png"))
                    screenshots.append(ss)
                    nav = _click_next_or_submit(page)
                    if nav == "submitted":
                        break
                    elif nav == "error":
                        return {"success": False, "screenshots": screenshots, "error": "form_navigation_failed"}
                    page_num += 1
                    time.sleep(1.5)

                time.sleep(2)
                ss = drv.screenshot(page, str(proof_dir / "final_confirmation.png"))
                screenshots.append(ss)
                return {"success": True, "screenshots": screenshots, "error": None}

            except Exception as e:
                try:
                    ss = drv.screenshot(page, str(proof_dir / "error.png"))
                    screenshots.append(ss)
                except Exception:
                    pass
                return {"success": False, "screenshots": screenshots, "error": str(e)}
            finally:
                page.close()

        result = driver.run(_do, timeout=600)
        return ApplicationResult(
            success=result["success"],
            screenshots=result["screenshots"],
            error_reason=result["error"],
        )


def _find_easy_apply_button(page):
    for sel in [
        "button.jobs-apply-button[aria-label*='Easy Apply']",
        "button[aria-label*='Easy Apply']",
        "button.jobs-apply-button",
    ]:
        btn = page.query_selector(sel)
        if btn and btn.is_visible():
            return btn
    for btn in page.query_selector_all("button"):
        try:
            if "easy apply" in (btn.inner_text() or "").lower() and btn.is_visible():
                return btn
        except Exception:
            pass
    return None


def _get_label(page, element) -> str:
    try:
        el_id = element.get_attribute("id")
        if el_id:
            lbl = page.query_selector(f"label[for='{el_id}']")
            if lbl:
                return lbl.inner_text().strip()
        aria = element.get_attribute("aria-label") or ""
        if aria:
            return aria
        return element.get_attribute("placeholder") or ""
    except Exception:
        return ""


def _fill_page(page, answers: dict, resume_path: str) -> None:
    modal = (
        page.query_selector("div[role='dialog']")
        or page.query_selector("div.jobs-easy-apply-content")
        or page
    )

    # Resume upload
    resume_abs = str(Path(resume_path).resolve())
    if Path(resume_abs).exists():
        for fi in page.query_selector_all("input[type='file']"):
            try:
                fi.set_input_files(resume_abs)
                time.sleep(1)
                break
            except Exception:
                pass

    # Text / tel / number inputs
    for inp in modal.query_selector_all("input[type='text'], input[type='tel'], input[type='number']"):
        try:
            if not inp.is_visible() or inp.is_disabled():
                continue
            if (inp.input_value() or "").strip():
                continue
            label = _get_label(page, inp)
            ans = _answer_for_label(label, answers)
            if ans:
                inp.fill(str(ans))
        except Exception as e:
            logger.debug("Input fill error: %s", e)

    # Textareas
    for ta in modal.query_selector_all("textarea"):
        try:
            if not ta.is_visible() or ta.is_disabled():
                continue
            if (ta.input_value() or "").strip():
                continue
            label = _get_label(page, ta)
            ans = _answer_for_label(label, answers)
            if ans:
                ta.fill(str(ans))
        except Exception as e:
            logger.debug("Textarea fill error: %s", e)

    # Selects — pick first non-empty option
    for sel_el in modal.query_selector_all("select"):
        try:
            if not sel_el.is_visible():
                continue
            opts = sel_el.query_selector_all("option")
            for opt in opts[1:]:
                val = opt.get_attribute("value")
                if val:
                    sel_el.select_option(value=val)
                    break
        except Exception as e:
            logger.debug("Select fill error: %s", e)

    # Radio buttons — prefer "Yes" for compliance questions
    radio_groups: dict[str, list] = {}
    for radio in modal.query_selector_all("input[type='radio']"):
        try:
            name = radio.get_attribute("name") or ""
            radio_groups.setdefault(name, []).append(radio)
        except Exception:
            pass
    for group in radio_groups.values():
        if any(r.is_checked() for r in group):
            continue
        yes_radio = next(
            (r for r in group if _get_label(page, r).lower() in ("yes", "true")),
            None,
        )
        target = yes_radio or (group[0] if group else None)
        if target:
            try:
                target.check()
            except Exception:
                pass


def _click_next_or_submit(page) -> str:
    for sel in ["button[aria-label='Submit application']", "button[aria-label*='Submit']"]:
        btn = page.query_selector(sel)
        if btn and btn.is_visible():
            try:
                btn.click()
                time.sleep(2)
                return "submitted"
            except Exception:
                return "error"

    for sel in [
        "button[aria-label='Continue to next step']",
        "button[aria-label*='Next']",
        "button[aria-label*='Review']",
    ]:
        btn = page.query_selector(sel)
        if btn and btn.is_visible():
            try:
                btn.click()
                return "next"
            except Exception:
                return "error"

    for btn in page.query_selector_all("button"):
        try:
            text = (btn.inner_text() or "").lower().strip()
            if not btn.is_visible():
                continue
            if text in ("submit application", "submit"):
                btn.click()
                time.sleep(2)
                return "submitted"
            if text in ("next", "continue", "review"):
                btn.click()
                return "next"
        except Exception:
            pass

    return "error"
