# Video Fit Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent the desktop review video from visually cropping the bottom of the frame.

**Architecture:** Keep `VideoPlayer` responsible for fitting media inside its allocated section. The parent review layout remains unchanged; the player root fills the section, the video viewport flexes, and the control bar stays fixed below the contained video.

**Tech Stack:** React 18, TypeScript, Electron renderer, Vite, Node renderer-flow tests.

---

## File structure

- Modify: `desktop/src/renderer/components/VideoPlayer.tsx` — clarify root, viewport, video, and control-bar layout styles so the video frame is contained without cropping.
- Modify: `desktop/scripts/renderer-flow.test.mjs` — add source assertions that guard the contained-video layout.

### Task 1: Contain the video frame in the player

**Files:**
- Modify: `desktop/src/renderer/components/VideoPlayer.tsx`
- Modify: `desktop/scripts/renderer-flow.test.mjs`

- [ ] **Step 1: Write the failing layout source test**

In `desktop/scripts/renderer-flow.test.mjs`, add this block after the `rallyQueueSource` checks and before the `appSource` checks:

```js
const videoPlayerSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'components', 'VideoPlayer.tsx'), 'utf8')
assert.match(videoPlayerSource, /const playerRootStyle: React\.CSSProperties/)
assert.match(videoPlayerSource, /const videoViewportStyle: React\.CSSProperties/)
assert.match(videoPlayerSource, /const videoElementStyle: React\.CSSProperties/)
assert.match(videoPlayerSource, /height: '100%'/)
assert.match(videoPlayerSource, /flex: '1 1 0'/)
assert.match(videoPlayerSource, /maxHeight: '100%'/)
assert.match(videoPlayerSource, /objectFit: 'contain'/)
assert.match(videoPlayerSource, /flexShrink: 0/)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
Set-Location .\desktop
npm.cmd run test:renderer-flow
```

Expected: FAIL because `VideoPlayer.tsx` still uses inline layout styles and does not define the named style constants.

- [ ] **Step 3: Update `VideoPlayer` layout styles**

In `desktop/src/renderer/components/VideoPlayer.tsx`, replace the root, video viewport, video element, and control bar inline styles with named constants:

```tsx
return (
  <div style={playerRootStyle}>
    <div style={videoViewportStyle}>
      <video
        ref={videoRef}
        src={src}
        style={videoElementStyle}
```

Replace the control bar opening style with:

```tsx
<div style={controlBarStyle}>
```

Add these constants near the existing `controlBtn` constant:

```ts
const playerRootStyle: React.CSSProperties = {
  height: '100%',
  minHeight: 0,
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
  background: '#000',
}

const videoViewportStyle: React.CSSProperties = {
  flex: '1 1 0',
  minHeight: 0,
  minWidth: 0,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
}

const videoElementStyle: React.CSSProperties = {
  display: 'block',
  width: '100%',
  height: '100%',
  maxWidth: '100%',
  maxHeight: '100%',
  objectFit: 'contain',
}

const controlBarStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '8px 16px',
  background: 'rgba(0,0,0,0.85)',
  flexShrink: 0,
}
```

- [ ] **Step 4: Run renderer-flow tests**

Run:

```powershell
Set-Location .\desktop
npm.cmd run test:renderer-flow
```

Expected: PASS.

- [ ] **Step 5: Run production build**

Run:

```powershell
Set-Location .\desktop
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 6: Commit the fix**

Run:

```powershell
git add desktop\src\renderer\components\VideoPlayer.tsx desktop\scripts\renderer-flow.test.mjs
git commit -m "fix: contain review video frame"
```

## Self-review notes

- Spec coverage: The task keeps the fix scoped to `VideoPlayer`, preserves `objectFit: 'contain'`, keeps controls visible with `flexShrink: 0`, and adds regression source checks.
- Placeholder scan: No placeholders or deferred implementation steps.
- Type consistency: All added constants are `React.CSSProperties`, matching existing file conventions.
