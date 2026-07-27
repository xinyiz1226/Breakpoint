# Docs Language Screenshots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `docs/index.html` show English screenshots in English mode and Chinese screenshots in Chinese mode.

**Architecture:** Keep the existing background-image and tab-class model. English is the default CSS mapping; `body.zh` overrides the same tab classes with Chinese image files.

**Tech Stack:** Static HTML/CSS/JavaScript in `docs/index.html`.

---

## File structure

- Modify: `docs/index.html` — update screenshot background-image CSS rules only.

### Task 1: Update language-specific screenshot CSS

**Files:**
- Modify: `docs/index.html`

- [ ] **Step 1: Write the failing mapping check**

Run this PowerShell check from the repository root:

```powershell
$html = Get-Content .\docs\index.html -Raw
if ($html -notmatch "background-image: url\('Images/Welcome_English\.jpg'\)") { throw "Missing default English welcome screenshot" }
if ($html -notmatch "background-image: url\('Images/VideoAnalysis_English\.jpg'\)") { throw "Missing default English analysis screenshot" }
if ($html -notmatch "background-image: url\('Images/Edit_English\.jpg'\)") { throw "Missing default English editor screenshot" }
if ($html -notmatch "body\.zh \.screenshot-placeholder\.with-image[\s\S]*Images/Welcome_Chinese\.jpg") { throw "Missing Chinese welcome override" }
if ($html -notmatch "body\.zh \.screenshot-placeholder\.with-image\.analysis-image[\s\S]*Images/VideoAnalysis_Chinese\.jpg") { throw "Missing Chinese analysis override" }
if ($html -notmatch "body\.zh \.screenshot-placeholder\.with-image\.editor-image[\s\S]*Images/Edit_Chinese\.jpg") { throw "Missing Chinese editor override" }
```

Expected: FAIL before implementation because the default rules currently point to Chinese screenshots.

- [ ] **Step 2: Update CSS mappings**

In `docs/index.html`, update the screenshot CSS near `.screenshot-placeholder.with-image` to this mapping:

```css
.screenshot-placeholder.with-image {
  background-image: url('Images/Welcome_English.jpg');
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
}
.screenshot-placeholder.with-image.analysis-image {
  background-image: url('Images/VideoAnalysis_English.jpg');
}
.screenshot-placeholder.with-image.editor-image {
  background-image: url('Images/Edit_English.jpg');
}
body.zh .screenshot-placeholder.with-image {
  background-image: url('Images/Welcome_Chinese.jpg');
}
body.zh .screenshot-placeholder.with-image.analysis-image {
  background-image: url('Images/VideoAnalysis_Chinese.jpg');
}
body.zh .screenshot-placeholder.with-image.editor-image {
  background-image: url('Images/Edit_Chinese.jpg');
}
```

- [ ] **Step 3: Run mapping check**

Run the same PowerShell check from Step 1.

Expected: PASS.

- [ ] **Step 4: Verify referenced files exist**

Run:

```powershell
$files = @(
  ".\docs\Images\Welcome_English.jpg",
  ".\docs\Images\VideoAnalysis_English.jpg",
  ".\docs\Images\Edit_English.jpg",
  ".\docs\Images\Welcome_Chinese.jpg",
  ".\docs\Images\VideoAnalysis_Chinese.jpg",
  ".\docs\Images\Edit_Chinese.jpg"
)
foreach ($file in $files) {
  if (-not (Test-Path $file)) { throw "Missing $file" }
}
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add docs\index.html
git commit -m "docs: map screenshots by language"
```

## Self-review notes

- Spec coverage: The plan updates all six screenshot mappings and leaves tab JavaScript unchanged.
- Placeholder scan: No placeholders or deferred work.
- Type consistency: Not applicable; this is static HTML/CSS.
