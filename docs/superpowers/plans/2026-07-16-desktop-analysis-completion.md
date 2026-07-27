# Desktop Analysis Completion Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop packaged desktop analysis from compiling a highlight video before review, and display the installed package version on the analysis screen.

**Architecture:** Keep the standalone engine wrapper unchanged and make the Electron bridge opt out of compilation with its existing `--no-compile` flag. Reuse the existing `getAppVersion()` renderer API in `AnalysisScreen`, matching the established `WelcomeScreen` pattern.

**Tech Stack:** Electron, React, TypeScript, Node.js source-level regression tests, Vite

---

## File Structure

- Modify `desktop/src/main/pythonBridge.ts`: pass the desktop-only analysis flag that separates analysis from export.
- Modify `desktop/src/renderer/components/AnalysisScreen.tsx`: load and render the package version.
- Modify `desktop/scripts/renderer-flow.test.mjs`: add focused regression assertions for both fixes.

### Task 1: Prevent Pre-Review Highlight Compilation

**Files:**
- Modify: `desktop/scripts/renderer-flow.test.mjs:338-350`
- Modify: `desktop/src/main/pythonBridge.ts:37-39`

- [ ] **Step 1: Write the failing bridge regression test**

Append this source assertion near the existing component source assertions in
`desktop/scripts/renderer-flow.test.mjs`:

```javascript
const pythonBridgeSource = fs.readFileSync(path.join(root, 'src', 'main', 'pythonBridge.ts'), 'utf8')
assert.match(
  pythonBridgeSource,
  /const fullArgs = \[\.\.\.args, videoPath, '--json-progress', '--no-compile'\]/,
)
```

- [ ] **Step 2: Run the renderer flow test and verify it fails**

Run:

```powershell
Set-Location D:\Codes\Breakpoint\desktop
npm run test:renderer-flow
```

Expected: FAIL because `pythonBridge.ts` does not yet include
`'--no-compile'` in `fullArgs`.

- [ ] **Step 3: Add the desktop-only no-compile argument**

Change the argument construction in `desktop/src/main/pythonBridge.ts` to:

```typescript
const fullArgs = [...args, videoPath, '--json-progress', '--no-compile']
```

Do not change `TennisHighlightAnalysis.py`; standalone invocations must retain
their existing default compilation behavior.

- [ ] **Step 4: Run the renderer flow test and verify it passes**

Run:

```powershell
Set-Location D:\Codes\Breakpoint\desktop
npm run test:renderer-flow
```

Expected: PASS with no assertion errors.

- [ ] **Step 5: Commit the analysis/export separation**

```powershell
Set-Location D:\Codes\Breakpoint
git add desktop\src\main\pythonBridge.ts desktop\scripts\renderer-flow.test.mjs
git commit -m "fix: skip export during desktop analysis" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>" -m "Copilot-Session: 859fb719-da8a-4ded-9fcc-40810a3f05ff"
```

### Task 2: Display the Installed Version During Analysis

**Files:**
- Modify: `desktop/scripts/renderer-flow.test.mjs:338-350`
- Modify: `desktop/src/renderer/components/AnalysisScreen.tsx:1-20,41-44`

- [ ] **Step 1: Write the failing analysis-screen regression test**

Add these assertions beside the other source-level component checks in
`desktop/scripts/renderer-flow.test.mjs`:

```javascript
const analysisScreenSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'components', 'AnalysisScreen.tsx'), 'utf8')
assert.doesNotMatch(analysisScreenSource, /v0\.1\.6/)
assert.match(analysisScreenSource, /window\.api\.getAppVersion\(\)\.then\(setAppVersion\)/)
assert.match(analysisScreenSource, /v\{appVersion \|\| '0\.0\.0'\}/)
```

- [ ] **Step 2: Run the renderer flow test and verify it fails**

Run:

```powershell
Set-Location D:\Codes\Breakpoint\desktop
npm run test:renderer-flow
```

Expected: FAIL because `AnalysisScreen.tsx` still contains `v0.1.6` and does
not load the application version.

- [ ] **Step 3: Load and render the package version**

Update the React import in `desktop/src/renderer/components/AnalysisScreen.tsx`:

```typescript
import { useEffect, useState, type CSSProperties, type ReactNode } from 'react'
```

Add state and the existing application-version API call inside
`AnalysisScreen`:

```typescript
const copy = useCopy()
const [appVersion, setAppVersion] = useState('')

useEffect(() => {
  window.api.getAppVersion().then(setAppVersion)
}, [])
```

Replace the hard-coded version span with:

```tsx
<span>v{appVersion || '0.0.0'}</span>
```

- [ ] **Step 4: Run the renderer flow test and verify it passes**

Run:

```powershell
Set-Location D:\Codes\Breakpoint\desktop
npm run test:renderer-flow
```

Expected: PASS with no assertion errors.

- [ ] **Step 5: Commit the dynamic analysis-screen version**

```powershell
Set-Location D:\Codes\Breakpoint
git add desktop\src\renderer\components\AnalysisScreen.tsx desktop\scripts\renderer-flow.test.mjs
git commit -m "fix: show package version during analysis" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>" -m "Copilot-Session: 859fb719-da8a-4ded-9fcc-40810a3f05ff"
```

### Task 3: Verify the Complete Desktop Fix

**Files:**
- Verify: `desktop/src/main/pythonBridge.ts`
- Verify: `desktop/src/renderer/components/AnalysisScreen.tsx`
- Verify: `desktop/scripts/renderer-flow.test.mjs`

- [ ] **Step 1: Run the focused renderer regression suite**

```powershell
Set-Location D:\Codes\Breakpoint\desktop
npm run test:renderer-flow
```

Expected: PASS.

- [ ] **Step 2: Run the production desktop build**

```powershell
Set-Location D:\Codes\Breakpoint\desktop
npm run build
```

Expected: TypeScript and Vite complete successfully with exit code 0.

- [ ] **Step 3: Inspect the final diff**

```powershell
Set-Location D:\Codes\Breakpoint
git --no-pager diff main~2..HEAD -- desktop\src\main\pythonBridge.ts desktop\src\renderer\components\AnalysisScreen.tsx desktop\scripts\renderer-flow.test.mjs
git status --short
```

Expected: the bridge includes `--no-compile`, the analysis screen uses
`getAppVersion()`, regression assertions cover both behaviors, and the
worktree is clean.
