# LinkedIn Easy Apply — SUBMIT mode

Goal: navigate every page of the Easy Apply form, fill all fields using provided answers, and submit.

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
**Submit button:** `aria-label="Submit application"`
**Dismiss button:** `aria-label="Dismiss"`

## Page sequence

**0% — Contact info**
- Select email from shadow DOM dropdown
- Select country code from shadow DOM dropdown
- Type phone number into shadow DOM text input
- Click `aria-label="Continue to next step"`

**33% — Resume**
- Resume already selected — click `aria-label="Continue to next step"` immediately

**67% — Additional questions**
- Fill every field using provided answers (see Field types below)
- After filling ALL fields, verify each field shows a value before clicking Review
- Click `aria-label="Review your application"`

**100% — Review page**
- IMPORTANT: Shadow DOM field values do NOT appear in browser_state text on the review page — this is normal, they ARE filled
- Do NOT go back to re-fill fields just because they look empty on review
- Click `aria-label="Submit application"` immediately
- Call done with success=true

## CRITICAL — Do ALL actions in ONE step per page
Fill all fields on the page AND click Next in the same step. Do not split across steps.

## Field types

Shadow DOM dropdown — `|SHADOW(open)|[N]<select .../>`:
Use `select_dropdown(index=N, text="option")`

Shadow DOM text input — `|SHADOW(open)|[N]<input type=text />`:
First try `input_text(index=N, text="value")`.
If the value does not appear after filling (field still shows empty), use evaluate to trigger React events:
```js
(function(){var d=document.querySelector('[role=dialog]');var inputs=Array.from(d.querySelectorAll('input[type=text]'));var i=inputs[0];if(!i)return 'not found';var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;s.call(i,'VALUE');i.dispatchEvent(new Event('input',{bubbles:true}));i.dispatchEvent(new Event('change',{bubbles:true}));return 'done';})()
```
Replace `VALUE` with the actual value and `inputs[0]` with the correct input by position.

Radio group — single `[N]<div>` with option text, no sub-indices:
Use `click(index=N)` — selects first option (Yes)
For "No" or other options use evaluate:
```js
(function(){var d=document.querySelector('[role=dialog]');var els=Array.from(d.querySelectorAll('label,span'));var t=els.find(function(e){return e.textContent.trim()==='No';});if(t){t.click();return 'clicked';}return 'not found';})()
```

## Number fields
Enter integers only if field says "Enter a whole number". Round down (2.5 → 2).
After typing, if browser_state shows a validation error near the field, fix the value before clicking Review.

## Recovery
- If Easy Apply button not found or not clickable after 2 attempts: call done with success=false and reason="no Easy Apply button"
- If Submit fails with a visible error: read the error, fix the field, click Submit once more
- If 3+ steps with no change: call done with success=false and describe what is blocking
- NEVER loop back from the review page to re-fill fields just because shadow DOM values look empty — they ARE there
