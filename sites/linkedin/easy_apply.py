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

# Label fragments that indicate a UI control, not a real question
_UI_NOISE_LABELS = [
    "deselect", "remove resume", "submit application", "upload resume",
    "attach resume", "delete", "close modal", "dismiss",
]


def _answer_for_label(label: str, answers: dict) -> str | None:
    lbl = label.lower().strip()
    for fragment, key in _LABEL_MAP.items():
        if fragment in lbl:
            return answers.get(key, "")
    return None


def _is_ui_noise(label: str, existing: str) -> bool:
    """True if this field is a UI control, not a real application question."""
    lbl = label.lower().strip()
    # Skip if input_value() returned the label text — spurious LinkedIn behavior
    if existing.lower().strip() == lbl:
        return True
    for frag in _UI_NOISE_LABELS:
        if frag in lbl:
            return True
    return False


class LinkedInEasyApplier(Applyable):
    def apply(
        self, listing: JobListing, answers: dict, resume_path: str, mode: str = "extract"
    ) -> ApplicationResult:
        """
        mode="extract": navigate form, collect Q&A, stop at review page, save to file.
        mode="submit":  navigate form, fill answers, click submit.
        """
        driver = BrowserDriver.get_instance()
        job_id = listing.job_id
        url = listing.url
        proof_dir = _JOBLER_ROOT / "jobs" / job_id / "proof"
        app_dir = _JOBLER_ROOT / "jobs" / job_id / "application"
        proof_dir.mkdir(parents=True, exist_ok=True)
        app_dir.mkdir(parents=True, exist_ok=True)

        def _do(ctx, drv) -> dict:
            screenshots: list[str] = []
            page = ctx.new_page()
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                drv.solve_captcha_if_present(page)

                try:
                    page.wait_for_selector(
                        "a[aria-label*='Easy Apply'], button[aria-label*='Easy Apply'], button:has-text('Continue as')",
                        timeout=10000,
                    )
                except Exception:
                    pass

                if _is_auth_required(page):
                    if not _dismiss_auth_popup(page):
                        return {"success": False, "screenshots": screenshots, "error": "auth_required", "pending_review": False}
                    page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    try:
                        page.wait_for_selector(
                            "a[aria-label*='Easy Apply'], button[aria-label*='Easy Apply']",
                            timeout=10000,
                        )
                    except Exception:
                        pass

                btn = _find_easy_apply_button(page)
                if not btn:
                    return {"success": False, "screenshots": screenshots, "error": "no_easy_apply_button", "pending_review": False}

                btn.click()
                page.wait_for_selector(
                    "div[data-test-modal-id='easy-apply-modal']",
                    timeout=10000,
                )

                ss = drv.screenshot(page, str(proof_dir / "01_easy_apply_opened.png"))
                screenshots.append(ss)

                if "linkedin.com" not in page.url:
                    return {"success": False, "screenshots": screenshots, "error": "redirected_to_external_site", "pending_review": False}

                all_qa: list[dict] = []
                page_num = 2
                prev_page_text = ""

                while page_num <= 15:
                    fill_answers = _load_saved_answers(app_dir) if mode == "submit" else answers
                    qa = _fill_page(page, fill_answers, resume_path, overwrite=(mode == "submit"))
                    all_qa.extend(qa)

                    ss = drv.screenshot(page, str(proof_dir / f"{page_num:02d}_form_page.png"))
                    screenshots.append(ss)

                    # Check if we're at review page (submit button visible)
                    if _is_review_page(page):
                        if mode == "extract":
                            # Save Q&A and stop — don't submit
                            _save_qa(app_dir, all_qa)
                            ss = drv.screenshot(page, str(proof_dir / f"{page_num:02d}_review_page.png"))
                            screenshots.append(ss)
                            return {"success": True, "screenshots": screenshots, "error": None, "pending_review": True}
                        else:
                            # Submit mode — click submit
                            submit_btn = page.query_selector("button[data-live-test-easy-apply-submit-button]") \
                                or page.query_selector("button[aria-label='Submit application']")
                            if submit_btn and submit_btn.is_visible():
                                submit_btn.click()
                                time.sleep(2)
                                ss = drv.screenshot(page, str(proof_dir / "final_confirmation.png"))
                                screenshots.append(ss)
                                return {"success": True, "screenshots": screenshots, "error": None, "pending_review": False}
                            return {"success": False, "screenshots": screenshots, "error": "submit_button_not_found", "pending_review": False}

                    nav = _click_next_or_review(page)
                    if nav == "error":
                        return {"success": False, "screenshots": screenshots, "error": "form_navigation_failed", "pending_review": False}

                    try:
                        page.wait_for_selector(
                            "div[data-test-modal-id='easy-apply-modal']",
                            timeout=5000,
                        )
                    except Exception:
                        pass

                    # Detect stuck form: if page text hasn't changed after Next, a validation
                    # error is blocking progress — save what we have and bail
                    current_text = ""
                    try:
                        modal_el = page.query_selector("div[data-test-modal-id='easy-apply-modal']")
                        current_text = (modal_el.inner_text() if modal_el else "").strip()
                    except Exception:
                        pass
                    if current_text and current_text == prev_page_text:
                        # Form didn't advance — likely a required field we couldn't fill
                        if mode == "extract":
                            _save_qa(app_dir, all_qa)
                            return {"success": True, "screenshots": screenshots, "error": None, "pending_review": True}
                        return {"success": False, "screenshots": screenshots, "error": "form_stuck_validation_error", "pending_review": False}
                    prev_page_text = current_text
                    page_num += 1

                return {"success": False, "screenshots": screenshots, "error": "form_exceeded_max_pages", "pending_review": False}

            except Exception as e:
                try:
                    ss = drv.screenshot(page, str(proof_dir / "error.png"))
                    screenshots.append(ss)
                except Exception:
                    pass
                return {"success": False, "screenshots": screenshots, "error": str(e), "pending_review": False}
            finally:
                page.close()

        result = driver.run(_do, timeout=600)
        return ApplicationResult(
            success=result["success"],
            screenshots=result["screenshots"],
            error_reason=result["error"],
            pending_review=result["pending_review"],
        )


def _is_review_page(page) -> bool:
    btn = page.query_selector("button[data-live-test-easy-apply-submit-button]")
    return bool(btn and btn.is_visible())


def _save_qa(app_dir: Path, qa: list[dict]) -> None:
    # Deduplicate: keep last occurrence of each question
    seen: dict[str, str] = {}
    for item in qa:
        q = item.get("question", "").strip()
        a = item.get("answer", "").strip()
        if q:
            seen[q] = a
    lines = ["# Application Questions & Answers\n"]
    for q, a in seen.items():
        lines.append(f"## {q}\n{a}\n")
    (app_dir / "questions_answered.md").write_text("\n".join(lines), encoding="utf-8")


def _load_saved_answers(app_dir: Path) -> dict:
    qa_file = app_dir / "questions_answered.md"
    if not qa_file.exists():
        return {}
    answers = {}
    current_q = None
    for line in qa_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current_q = line[3:].strip()
        elif current_q and line.strip():
            answers[current_q.lower()] = line.strip()
            current_q = None
    return answers


def _find_easy_apply_button(page):
    for sel in [
        "a[aria-label*='Easy Apply']",
        "button[aria-label*='Easy Apply']",
        "button.jobs-apply-button[aria-label*='Easy Apply']",
        "button.jobs-apply-button",
    ]:
        btn = page.query_selector(sel)
        if btn and btn.is_visible():
            return btn
    for tag in ["a", "button"]:
        for btn in page.query_selector_all(tag):
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


def _get_radio_group_question(radio_el) -> str:
    """Get the question text for a radio group from the nearest fieldset legend or heading."""
    try:
        return radio_el.evaluate("""el => {
            const fs = el.closest('fieldset');
            if (fs) {
                const legend = fs.querySelector('legend');
                if (legend && legend.innerText.trim()) return legend.innerText.trim();
            }
            const form_el = el.closest('.fb-dash-form-element, .jobs-easy-apply-form-element');
            if (form_el) {
                const h = form_el.querySelector('h3, h4, label, span.t-bold');
                if (h && h.innerText.trim()) return h.innerText.trim();
            }
            return el.getAttribute('name') || '';
        }""")
    except Exception:
        return ""


def _fill_page(page, answers: dict, resume_path: str, overwrite: bool = False) -> list[dict]:
    """Fill all fields on the current modal page. Returns list of {question, answer} dicts.
    overwrite=True (submit mode): always fill fields even if pre-filled, using saved answers.
    """
    qa: list[dict] = []
    modal = (
        page.query_selector("div[data-test-modal-id='easy-apply-modal']")
        or page.query_selector("div[role='dialog']")
        or page
    )

    # Resume upload — only in extract mode; in submit mode resume is already attached
    if not overwrite:
        resume_abs = str(Path(resume_path).resolve())
        if Path(resume_abs).exists():
            for fi in page.query_selector_all("input[type='file']"):
                try:
                    fi.set_input_files(resume_abs)
                    time.sleep(1)
                    qa.append({"question": "Resume", "answer": Path(resume_path).name})
                    break
                except Exception:
                    pass

    # Text / tel / number inputs
    for inp in modal.query_selector_all("input[type='text'], input[type='tel'], input[type='number']"):
        try:
            if not inp.is_visible() or inp.is_disabled():
                continue
            label = _get_label(page, inp)
            if not label or _is_ui_noise(label, ""):
                continue
            existing = (inp.input_value() or "").strip()
            # Sanitise: take only first non-empty line (some LinkedIn fields return multiline)
            existing = existing.splitlines()[0].strip() if existing else ""

            ans = _answer_for_label(label, answers) or answers.get(label.lower(), "")

            if overwrite and ans:
                # Submit mode: always write saved answer
                inp.triple_click()
                inp.fill(str(ans))
                qa.append({"question": label, "answer": str(ans)})
            elif existing:
                if not _is_ui_noise(label, existing):
                    qa.append({"question": label, "answer": existing})
            elif ans:
                inp.fill(str(ans))
                qa.append({"question": label, "answer": str(ans)})
            else:
                qa.append({"question": label, "answer": ""})
        except Exception as e:
            logger.debug("Input fill error: %s", e)

    # Textareas
    for ta in modal.query_selector_all("textarea"):
        try:
            if not ta.is_visible() or ta.is_disabled():
                continue
            label = _get_label(page, ta)
            if not label or _is_ui_noise(label, ""):
                continue
            existing = (ta.input_value() or "").strip()
            ans = _answer_for_label(label, answers) or answers.get(label.lower(), "")

            if overwrite and ans:
                ta.triple_click()
                ta.fill(str(ans))
                qa.append({"question": label, "answer": str(ans)})
            elif existing:
                if not _is_ui_noise(label, existing):
                    qa.append({"question": label, "answer": existing})
            elif ans:
                ta.fill(str(ans))
                qa.append({"question": label, "answer": str(ans)})
            else:
                qa.append({"question": label, "answer": ""})
        except Exception as e:
            logger.debug("Textarea fill error: %s", e)

    # Selects
    for sel_el in modal.query_selector_all("select"):
        try:
            if not sel_el.is_visible():
                continue
            label = _get_label(page, sel_el)
            opts = sel_el.query_selector_all("option")
            saved_ans = answers.get(label.lower(), "")
            if saved_ans:
                for opt in opts:
                    opt_text = (opt.inner_text() or "").strip().lower()
                    if saved_ans.lower() in opt_text or opt_text in saved_ans.lower():
                        val = opt.get_attribute("value")
                        if val:
                            sel_el.select_option(value=val)
                            qa.append({"question": label, "answer": opt.inner_text().strip()})
                            break
            else:
                for opt in opts[1:]:
                    val = opt.get_attribute("value")
                    if val:
                        sel_el.select_option(value=val)
                        qa.append({"question": label, "answer": opt.inner_text().strip()})
                        break
        except Exception as e:
            logger.debug("Select fill error: %s", e)

    # Radio buttons
    radio_groups: dict[str, list] = {}
    for radio in modal.query_selector_all("input[type='radio']"):
        try:
            name = radio.get_attribute("name") or ""
            radio_groups.setdefault(name, []).append(radio)
        except Exception:
            pass

    for name, group in radio_groups.items():
        try:
            question_text = _get_radio_group_question(group[0]) or name
            saved_ans = answers.get(question_text.lower(), "")

            if saved_ans:
                # Find radio option matching saved answer
                matched = None
                for r in group:
                    opt_label = _get_label(page, r).lower().strip()
                    if saved_ans.lower().strip() in opt_label or opt_label in saved_ans.lower().strip():
                        matched = r
                        break
                target = matched or next((r for r in group if r.is_checked()), None)
                if target and not target.is_checked():
                    target.check()
                if target:
                    qa.append({"question": question_text, "answer": _get_label(page, target)})
            elif any(r.is_checked() for r in group):
                checked = next(r for r in group if r.is_checked())
                qa.append({"question": question_text, "answer": _get_label(page, checked)})
            else:
                # No saved answer, nothing checked — default to Yes or first option
                yes_radio = next(
                    (r for r in group if _get_label(page, r).lower() in ("yes", "true")), None
                )
                target = yes_radio or group[0]
                target.check()
                qa.append({"question": question_text, "answer": _get_label(page, target)})
        except Exception as e:
            logger.debug("Radio fill error: %s", e)

    return qa


def _click_next_or_review(page) -> str:
    """Click Review or Next button. Submit is handled separately via _is_review_page."""
    for sel in [
        "button[data-live-test-easy-apply-review-button]",
        "button[aria-label='Review your application']",
    ]:
        btn = page.query_selector(sel)
        if btn and btn.is_visible():
            try:
                btn.click()
                return "next"
            except Exception:
                return "error"

    for sel in [
        "button[data-easy-apply-next-button]",
        "button[aria-label='Continue to next step']",
    ]:
        btn = page.query_selector(sel)
        if btn and btn.is_visible():
            try:
                btn.click()
                return "next"
            except Exception:
                return "error"

    return "error"
