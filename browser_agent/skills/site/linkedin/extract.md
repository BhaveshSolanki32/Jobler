# LinkedIn Easy Apply — EXTRACT mode

Goal: navigate every page of the Easy Apply form, collect all field labels, do NOT submit.

## Before opening the form — check these first

1. If page shows "Application submitted" or "Applied" anywhere near the job title: call done with success=false and reason="already applied"
2. If page shows "No longer accepting applications" or "Job closed" or "This job is no longer available": call done with success=false and reason="job expired"
3. If no Easy Apply button exists (only "Apply on company website"): call done with success=false and reason="no Easy Apply button"

## Opening the Easy Apply modal

Do NOT use search_page or find_elements to find the Easy Apply button. Use evaluate directly:
```js
(function(){var b=document.querySelector('[aria-label*="Easy Apply"]');if(b){b.click();return 'clicked';}return 'not found';})()
```
If evaluate returns "not found": call done with success=false and reason="no Easy Apply button"

## Element identification

**Modal:** `role=dialog` — stay inside it
**Progress:** `aria-label="Your job application progress is at X percent."`
**Next button:** `aria-label="Continue to next step"`
**Review button:** `aria-label="Review your application"`
**Dismiss button:** `aria-label="Dismiss"`

## Page sequence

**0% — Contact info**
- save_item: Email address, Phone country code, Mobile phone number
- Select email dropdown, select country code dropdown, type phone number
- Click `aria-label="Continue to next step"`

**33% — Resume**
- Do NOT save_item anything
- Click `aria-label="Continue to next step"` immediately

**67% — Additional questions**
- save_item every question label
- Fill every field (see field types below)
- Click `aria-label="Review your application"`

**100% — Review page**
- Call done with success=true — do NOT submit

## CRITICAL — Do ALL actions in ONE step per page
On each page: save_item + fill fields + click Next all in the same step. Do not split across steps.

## Field types

Shadow DOM dropdown — `|SHADOW(open)|[N]<select .../>`:
Use `select_dropdown(index=N, text="option")`

Shadow DOM text input — `|SHADOW(open)|[N]<input type=text />`:
Use `input_text(index=N, text="value")` — the index works despite shadow DOM

Radio group — single `[N]<div>` with option text, no sub-indices:
Use `click(index=N)` — selects first option (Yes)
For other options use evaluate:
```js
(function(){var d=document.querySelector('[role=dialog]');var els=Array.from(d.querySelectorAll('label,span'));var t=els.find(function(e){return e.textContent.trim()==='No';});if(t){t.click();return 'clicked';}return 'not found';})()
```

## Number fields
Enter integers only if field says "Enter a whole number". Round down (2.5 → 2).

## Recovery
- If Next/Review doesn't advance: re-read browser_state, find unfilled Required field, fix it, try once more
- If 3+ steps with no change: call done with success=false and reason
