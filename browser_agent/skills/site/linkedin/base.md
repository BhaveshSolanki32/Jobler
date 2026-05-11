# Skill: LinkedIn Easy Apply

## Applies when
URL contains `linkedin.com` and the job has an Easy Apply button.

---

## How to identify elements

**Easy Apply button** — on the job listing page, before the modal opens:
```
<a aria-label="Easy Apply to this job" />
```
or a button with text "Easy Apply". Do NOT click "Apply on company website".

**Modal container** — appears after clicking Easy Apply:
```
<div role="dialog" />
```
Everything inside this is the application form. Stay inside it.

**Progress indicator** — tells you which page of the form you are on:
```
<div aria-label="Your job application progress is at X percent." role="region" />
```
- 0% → Contact info page
- 33% → Resume page
- 67% → Additional questions page
- 100% → Review page

**Navigation buttons** — identified by aria-label, NOT by text or index:
```
aria-label="Continue to next step"   → Next button
aria-label="Review your application" → Review button (last questions page)
aria-label="Submit application"      → Submit button (review page only)
aria-label="Back to previous step"   → Back button
aria-label="Dismiss"                 → Dismiss/close button
```

**Form field types:**

Shadow DOM dropdown (email, country code):
```
|SHADOW(open)|<select id="text-entity-list-form-component-formElement-..." />
  compound_components: (name=Options, role=listbox, options=A|B|C)
```
Use: `select_option` with the element index.

Shadow DOM text input (phone, years of experience, text questions):
```
|SHADOW(open)|<input id="single-line-text-form-component-formElement-..." type=text />
```
Use: `input_text` with the element index. The index works despite shadow DOM.
If the value does not appear after filling, use evaluate to trigger React events:
```js
(function(){var d=document.querySelector('[role=dialog]');var inputs=Array.from(d.querySelectorAll('input[type=text]'));var i=inputs[0];if(!i)return 'not found';var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;s.call(i,'VALUE');i.dispatchEvent(new Event('input',{bubbles:true}));i.dispatchEvent(new Event('change',{bubbles:true}));return 'done';})()
```
Replace `VALUE` with the actual value and `inputs[0]` with the correct input by position.

Radio button group — options appear as plain text inside a container, no individual indices:
```
[N]<div />
    Question text here
    Required
    Yes
    No
```
Use: `click(index=N)` on the container div — this selects the first option (Yes).
If you need a different option, use evaluate:
```js
(function(){
  var d=document.querySelector('[role=dialog]');
  var labels=Array.from(d.querySelectorAll('label,span'));
  var t=labels.find(function(e){return e.textContent.trim()==='No';});
  if(t){t.click();return 'clicked';}return 'not found';
})()
```

Resume container — identified by aria-label, not index:
```
<div aria-label="Selected" />          → resume already selected
<div aria-label="Select this resume"/> → available but not selected
```

---

## EXTRACT mode
Goal: navigate every page, collect all field labels, do NOT submit.

### Step 1 — Dismiss "Continue as" popup
If you see a popup with "Continue as [name]", click `aria-label="Dismiss"` button.

### Step 2 — Detect login wall
If the page shows a login form instead of the job listing, call done with success=false and reason="login wall".

### Step 3 — Open the Easy Apply modal
Find the button with `aria-label` containing "Easy Apply" and click it.
Do NOT wait. Read the next browser_state directly.

### Step 4 — On each modal page, do ALL of this in ONE step:
1. Call save_item for each visible field label or question
2. Fill every field
3. Click the navigation button to proceed

**0% — Contact info page:**
- save_item for Email address, Phone country code, Mobile phone number
- Select email from shadow DOM dropdown
- Select country code from shadow DOM dropdown
- Type mobile number into shadow DOM text input
- Click button with `aria-label="Continue to next step"`

**33% — Resume page:**
- No fields to extract — do NOT call save_item
- A resume with `aria-label="Selected"` is already chosen — do nothing to it
- Click button with `aria-label="Continue to next step"` immediately

**67% — Additional questions page:**
- save_item for every question label visible
- Fill each field using the correct interaction (see element types above)
- Click button with `aria-label="Review your application"`

**100% — Review page:**
- Do NOT click submit
- Call done with success=true

### Step 5 — Repeat Step 4 for every page until done.

---

## SUBMIT mode
Goal: fill every page and submit.

Same navigation as EXTRACT, but on the review page:
- IMPORTANT: Shadow DOM field values do NOT appear in browser_state text on the review page — this is normal, they ARE filled
- Do NOT go back to re-fill fields just because they look empty on review
- Click button with `aria-label="Submit application"` immediately
- Call done with success=true

---

## Number fields
- If a field shows "Enter a whole number", enter an integer only (no decimals)
- If you see an error indicator after filling, fix the value before clicking Next/Review

---

## Recovery rules

**If Next/Review does not advance the form:**
- Do NOT click it again
- Read browser_state for any "Required" field with no value, or any error indicator
- Fix the field, then click the navigation button once more

**If on the review page (100%) and fields look empty:**
- This is a shadow DOM rendering limitation — values ARE saved
- Do NOT go back — click Submit directly

**If 3+ consecutive steps produce no change in browser_state:**
- Stop repeating — try a completely different approach
- If still blocked: call done with success=false and describe what is blocking you

**If a field type is unfamiliar:**
- Read its tag, role, and surrounding text in browser_state
- Try: click for buttons/checkboxes, input_text for text, select_option for dropdowns
- If first attempt fails: try one alternative
- If second attempt fails: skip and move on

**If the modal closes unexpectedly:** call done with success=false and reason="modal closed unexpectedly"
**If you see a CAPTCHA:** call done with success=false and reason="captcha"
