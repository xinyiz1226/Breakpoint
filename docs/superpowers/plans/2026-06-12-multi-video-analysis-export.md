# Multi-Video Analysis and Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a desktop batch workspace that analyzes multiple videos sequentially, merges successful rallies into one queue, previews each rally from its source video, and exports selected rallies from multiple videos into one MP4.

**Architecture:** Convert the renderer from a single `videoPath + segments` model to an in-memory batch workspace with explicit `videos[]`, source-aware `rallies[]`, `activeVideoId`, and `selectedRallyId`. Keep analysis sequential because the main-process bridge currently owns one active analysis process, and change export IPC to accept `{ videoPath, start, end }[]` clips for multi-source ffmpeg concat.

**Tech Stack:** React 18, TypeScript, Electron IPC, Vite, Node-based renderer flow tests, ffmpeg.

---

## File structure

- Create: `desktop/src/renderer/batchFlow.ts` — pure helpers for video record creation, report-to-rally conversion, queue ordering, active-video segment filtering, and export clip preparation.
- Create: `desktop/src/renderer/components/BatchVideoList.tsx` — small source-video status/retry list for the batch workspace.
- Modify: `desktop/src/renderer/state/AppState.tsx` — replace single-video state with batch workspace state and source-aware reducer actions.
- Modify: `desktop/src/renderer/viewModels/flowCopy.ts` — make review summaries and rally titles work with source-aware rallies without losing existing behavior.
- Modify: `desktop/src/renderer/i18n/copy.ts` — add localized batch import, status, source-label, retry, and progress copy.
- Modify: `desktop/src/renderer/App.tsx` — orchestrate multi-video import, sequential analysis, retry, active video switching, source-aware export, and cleanup.
- Modify: `desktop/src/renderer/components/WelcomeScreen.tsx` — support multi-select import and multi-file drop.
- Modify: `desktop/src/renderer/components/AnalysisScreen.tsx` — accept batch progress metadata and pass it to the progress panel.
- Modify: `desktop/src/renderer/components/AnalysisProgressPanel.tsx` — show batch-level progress plus current-video analysis progress.
- Modify: `desktop/src/renderer/components/MatchMap.tsx` — show the active video's rallies and duration only.
- Modify: `desktop/src/renderer/components/RallyQueue.tsx` — render the global source-aware queue, source labels, and source-aware trim/selection actions.
- Modify: `desktop/src/renderer/components/VideoPlayer.tsx` — reset playback state when the source video changes.
- Modify: `desktop/src/main/main.ts` — allow multi-select open-file dialog and recent-project updates for selected videos.
- Modify: `desktop/src/main/preload.ts` — expose multi-file import and multi-source export signatures.
- Modify: `desktop/src/main/ffmpegBridge.ts` — accept source-aware export clips and concatenate clips from multiple input videos.
- Modify: `desktop/src/renderer/types.d.ts` — update renderer API types.
- Modify: `desktop/scripts/renderer-flow.test.mjs` — add reducer, helper, source-check, and API contract tests.

## Task 1: Add pure batch helpers

**Files:**
- Create: `desktop/src/renderer/batchFlow.ts`
- Test: `desktop/scripts/renderer-flow.test.mjs`

- [ ] **Step 1: Write failing tests for batch helpers**

Add this import after the existing `analysisFlow.ts` import:

```js
const {
  createVideoRecords,
  createRalliesForVideo,
  getSortedRallies,
  getRalliesForVideo,
  getExportClips,
  getVideoDisplayName,
} = loadTsModule(path.join('src', 'renderer', 'batchFlow.ts'))
```

Add these assertions after `const plain = ...`:

```js
const batchVideos = createVideoRecords([
  'D:\\match\\first.mp4',
  'D:\\match\\second.mov',
])
assert.equal(batchVideos.length, 2)
assert.equal(batchVideos[0].id, 'video-1')
assert.equal(batchVideos[0].path, 'D:\\match\\first.mp4')
assert.equal(batchVideos[0].displayName, 'first.mp4')
assert.equal(batchVideos[0].order, 0)
assert.equal(batchVideos[0].status, 'pending')
assert.equal(batchVideos[1].id, 'video-2')
assert.equal(batchVideos[1].displayName, 'second.mov')
assert.equal(getVideoDisplayName('C:\\clips\\demo.avi'), 'demo.avi')

const firstVideoRallies = createRalliesForVideo(batchVideos[0], [
  { index: 2, start: 30, end: 38, score: 1.8, features: { hit_count: 7 } },
  { index: 1, start: 10, end: 22, score: 2.5, features: { hit_count: 16 } },
])
const secondVideoRallies = createRalliesForVideo(batchVideos[1], [
  { index: 0, start: 5, end: 12, score: 2.1, features: {} },
])
assert.deepEqual(firstVideoRallies.map((r) => r.id), ['video-1-rally-2', 'video-1-rally-1'])
assert.equal(firstVideoRallies[0].videoId, 'video-1')
assert.equal(firstVideoRallies[0].sourceIndex, 2)
assert.equal(firstVideoRallies[0].included, true)
assert.equal(firstVideoRallies[1].included, true)

const sortedRallies = getSortedRallies([
  secondVideoRallies[0],
  firstVideoRallies[0],
  firstVideoRallies[1],
], batchVideos)
assert.deepEqual(sortedRallies.map((r) => r.id), ['video-1-rally-1', 'video-1-rally-2', 'video-2-rally-0'])
assert.deepEqual(getRalliesForVideo(sortedRallies, 'video-1').map((r) => r.id), ['video-1-rally-1', 'video-1-rally-2'])
assert.deepEqual(getExportClips(sortedRallies, batchVideos), [
  { videoPath: 'D:\\match\\first.mp4', start: 10, end: 22 },
  { videoPath: 'D:\\match\\first.mp4', start: 30, end: 38 },
  { videoPath: 'D:\\match\\second.mov', start: 5, end: 12 },
])
assert.deepEqual(getExportClips([
  { ...firstVideoRallies[1], startAdjusted: 11, endAdjusted: 20 },
  { ...secondVideoRallies[0], included: false },
], batchVideos), [
  { videoPath: 'D:\\match\\first.mp4', start: 11, end: 20 },
])
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: fail with a module-not-found error for `src\renderer\batchFlow.ts`.

- [ ] **Step 3: Create batch helper implementation**

Create `desktop/src/renderer/batchFlow.ts`:

```ts
import type { RallySegment, VideoRecord } from './state/AppState'

const AUTO_INCLUDE_THRESHOLD = 1.7

interface AnalysisSegment {
  index: number
  start: number
  end: number
  score: number
  features: Record<string, number>
}

export interface ExportClip {
  videoPath: string
  start: number
  end: number
}

export function getVideoDisplayName(path: string): string {
  return path.split(/[\\/]/).pop() || path
}

export function createVideoRecords(paths: string[]): VideoRecord[] {
  return paths.map((path, order) => ({
    id: `video-${order + 1}`,
    path,
    displayName: getVideoDisplayName(path),
    order,
    status: 'pending',
    errorMessage: null,
    currentStep: null,
    duration: 0,
    rallyCount: 0,
  }))
}

export function createRalliesForVideo(video: VideoRecord, segments: AnalysisSegment[]): RallySegment[] {
  return segments.map((segment) => ({
    id: `${video.id}-rally-${segment.index}`,
    videoId: video.id,
    sourceIndex: segment.index,
    index: segment.index,
    start: segment.start,
    end: segment.end,
    score: segment.score,
    features: segment.features,
    included: segment.score > AUTO_INCLUDE_THRESHOLD,
  }))
}

export function getSortedRallies(rallies: RallySegment[], videos: VideoRecord[]): RallySegment[] {
  const orderByVideo = new Map(videos.map((video) => [video.id, video.order]))
  return [...rallies].sort((a, b) => {
    const videoDelta = (orderByVideo.get(a.videoId) ?? Number.MAX_SAFE_INTEGER) - (orderByVideo.get(b.videoId) ?? Number.MAX_SAFE_INTEGER)
    if (videoDelta !== 0) return videoDelta
    return a.start - b.start
  })
}

export function getRalliesForVideo(rallies: RallySegment[], videoId: string): RallySegment[] {
  return rallies.filter((rally) => rally.videoId === videoId)
}

export function getExportClips(rallies: RallySegment[], videos: VideoRecord[]): ExportClip[] {
  const pathByVideo = new Map(videos.map((video) => [video.id, video.path]))
  return getSortedRallies(rallies.filter((rally) => rally.included), videos)
    .map((rally) => {
      const videoPath = pathByVideo.get(rally.videoId)
      if (!videoPath) return null
      return {
        videoPath,
        start: rally.startAdjusted ?? rally.start,
        end: rally.endAdjusted ?? rally.end,
      }
    })
    .filter((clip): clip is ExportClip => clip !== null && clip.end > clip.start)
}
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: helper tests pass. The type-only imports are erased by the renderer-flow test transpiler and will become valid TypeScript exports in Task 2.

- [ ] **Step 5: Commit**

```powershell
git add desktop\src\renderer\batchFlow.ts desktop\scripts\renderer-flow.test.mjs
git commit -m "test: add batch flow helper coverage" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 2: Convert renderer state to a batch workspace

**Files:**
- Modify: `desktop/src/renderer/state/AppState.tsx`
- Test: `desktop/scripts/renderer-flow.test.mjs`

- [ ] **Step 1: Write failing reducer tests**

Replace the old `reducerClampState` block with source-aware state assertions:

```js
const reducerBatchState = {
  videos: [
    { id: 'video-1', path: 'D:\\match\\first.mp4', displayName: 'first.mp4', order: 0, status: 'done', errorMessage: null, currentStep: null, duration: 100, rallyCount: 2 },
    { id: 'video-2', path: 'D:\\match\\second.mp4', displayName: 'second.mp4', order: 1, status: 'error', errorMessage: 'bad input', currentStep: null, duration: 0, rallyCount: 0 },
  ],
  activeVideoId: 'video-1',
  selectedRallyId: null,
  analysisStatus: 'done',
  currentStep: null,
  errorMessage: null,
  rallies: [
    { id: 'video-1-rally-0', videoId: 'video-1', sourceIndex: 0, index: 0, start: 10, end: 12, score: 2, included: true, features: {} },
    { id: 'video-1-rally-1', videoId: 'video-1', sourceIndex: 1, index: 1, start: 20, end: 24, score: 2, included: true, features: {}, startAdjusted: 21, endAdjusted: 23 },
  ],
}
assert.deepEqual(plain(reducer(reducerBatchState, { type: 'ADJUST_RALLY', id: 'video-1-rally-0', start: 11.8 }).rallies[0]), {
  id: 'video-1-rally-0',
  videoId: 'video-1',
  sourceIndex: 0,
  index: 0,
  start: 10,
  end: 12,
  score: 2,
  included: true,
  features: {},
  startAdjusted: 11.5,
})
assert.deepEqual(plain(reducer(reducerBatchState, { type: 'ADJUST_RALLY', id: 'video-1-rally-1', end: 21.2 }).rallies[1]), {
  id: 'video-1-rally-1',
  videoId: 'video-1',
  sourceIndex: 1,
  index: 1,
  start: 20,
  end: 24,
  score: 2,
  included: true,
  features: {},
  startAdjusted: 21,
  endAdjusted: 21.5,
})
assert.equal(reducer(reducerBatchState, { type: 'SELECT_RALLY', id: 'video-1-rally-1' }).selectedRallyId, 'video-1-rally-1')
assert.equal(reducer(reducerBatchState, { type: 'SET_ACTIVE_VIDEO', id: 'video-2' }).activeVideoId, 'video-2')
assert.equal(reducer(reducerBatchState, { type: 'VIDEO_ANALYSIS_RETRY', videoId: 'video-2' }).videos[1].status, 'running')
assert.equal(reducer(reducerBatchState, { type: 'VIDEO_ANALYSIS_ERROR', videoId: 'video-2', message: 'still bad' }).videos[1].errorMessage, 'still bad')
assert.deepEqual(plain(reducer(reducerBatchState, { type: 'RESTORE_RECOMMENDED' }).rallies[1]), {
  id: 'video-1-rally-1',
  videoId: 'video-1',
  sourceIndex: 1,
  index: 1,
  start: 20,
  end: 24,
  score: 2,
  included: true,
  features: {},
  startAdjusted: 21,
  endAdjusted: 23,
})
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: fail because reducer actions such as `ADJUST_RALLY`, `SELECT_RALLY`, and batch state fields do not exist.

- [ ] **Step 3: Replace `AppState.tsx` with batch state**

Update `desktop/src/renderer/state/AppState.tsx` so the exported types and reducer are:

```ts
import { createContext, useContext, useReducer, ReactNode } from 'react'

const INCLUDE_THRESHOLD = 1.7
const MIN_SEGMENT_DURATION = 0.5

type VideoAnalysisStatus = 'pending' | 'running' | 'done' | 'error'

interface ProgressStep {
  step: number
  total: number
  label: string
  elapsed?: number
  subCurrent?: number
  subTotal?: number
}

interface VideoRecord {
  id: string
  path: string
  displayName: string
  order: number
  status: VideoAnalysisStatus
  errorMessage: string | null
  currentStep: ProgressStep | null
  duration: number
  rallyCount: number
}

interface RallySegment {
  id: string
  videoId: string
  sourceIndex: number
  index: number
  start: number
  end: number
  score: number
  features: Record<string, number>
  included: boolean
  startAdjusted?: number
  endAdjusted?: number
}

interface AppState {
  videos: VideoRecord[]
  activeVideoId: string | null
  selectedRallyId: string | null
  analysisStatus: 'idle' | 'running' | 'done' | 'error'
  currentStep: ProgressStep | null
  errorMessage: string | null
  rallies: RallySegment[]
}

type Action =
  | { type: 'CREATE_BATCH'; videos: VideoRecord[] }
  | { type: 'CLOSE_BATCH' }
  | { type: 'BATCH_ANALYSIS_START' }
  | { type: 'BATCH_ANALYSIS_DONE' }
  | { type: 'BATCH_ANALYSIS_ERROR'; message: string }
  | { type: 'VIDEO_ANALYSIS_START'; videoId: string }
  | { type: 'VIDEO_ANALYSIS_RETRY'; videoId: string }
  | { type: 'VIDEO_ANALYSIS_STEP'; videoId: string; step: ProgressStep }
  | { type: 'VIDEO_ANALYSIS_SUB_PROGRESS'; videoId: string; current: number; total: number }
  | { type: 'VIDEO_ANALYSIS_DONE'; videoId: string; rallies: RallySegment[] }
  | { type: 'VIDEO_ANALYSIS_ERROR'; videoId: string; message: string }
  | { type: 'SET_VIDEO_DURATION'; videoId: string; duration: number }
  | { type: 'SET_ACTIVE_VIDEO'; id: string | null }
  | { type: 'SELECT_RALLY'; id: string | null }
  | { type: 'TOGGLE_INCLUDE'; id: string }
  | { type: 'INCLUDE_ALL' }
  | { type: 'EXCLUDE_ALL' }
  | { type: 'RESTORE_RECOMMENDED' }
  | { type: 'ADJUST_RALLY'; id: string; start?: number | undefined; end?: number | undefined }

function applyAutoInclude(rallies: RallySegment[]): RallySegment[] {
  return rallies.map((rally) => ({ ...rally, included: rally.score > INCLUDE_THRESHOLD }))
}

function hasActionValue(action: Extract<Action, { type: 'ADJUST_RALLY' }>, key: 'start' | 'end'): boolean {
  return Object.prototype.hasOwnProperty.call(action, key)
}

function applyRallyAdjustment(rally: RallySegment, action: Extract<Action, { type: 'ADJUST_RALLY' }>): RallySegment {
  const hasStart = hasActionValue(action, 'start')
  const hasEnd = hasActionValue(action, 'end')
  let startAdjusted = hasStart ? action.start : rally.startAdjusted
  let endAdjusted = hasEnd ? action.end : rally.endAdjusted
  const effectiveStart = startAdjusted ?? rally.start
  const effectiveEnd = endAdjusted ?? rally.end

  if (effectiveEnd - effectiveStart < MIN_SEGMENT_DURATION) {
    if (hasStart && !hasEnd) {
      startAdjusted = effectiveEnd - MIN_SEGMENT_DURATION
    } else {
      endAdjusted = effectiveStart + MIN_SEGMENT_DURATION
    }
  }

  return { ...rally, startAdjusted, endAdjusted }
}

const initialState: AppState = {
  videos: [],
  activeVideoId: null,
  selectedRallyId: null,
  analysisStatus: 'idle',
  currentStep: null,
  errorMessage: null,
  rallies: [],
}

function updateVideo(state: AppState, videoId: string, updater: (video: VideoRecord) => VideoRecord): AppState {
  return {
    ...state,
    videos: state.videos.map((video) => video.id === videoId ? updater(video) : video),
  }
}

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'CREATE_BATCH':
      return { ...initialState, videos: action.videos, activeVideoId: action.videos[0]?.id ?? null }
    case 'CLOSE_BATCH':
      return initialState
    case 'BATCH_ANALYSIS_START':
      return { ...state, analysisStatus: 'running', currentStep: null, errorMessage: null }
    case 'BATCH_ANALYSIS_DONE':
      return { ...state, analysisStatus: 'done', currentStep: null }
    case 'BATCH_ANALYSIS_ERROR':
      return { ...state, analysisStatus: 'error', errorMessage: action.message, currentStep: null }
    case 'VIDEO_ANALYSIS_START':
    case 'VIDEO_ANALYSIS_RETRY':
      return updateVideo({ ...state, analysisStatus: 'running', errorMessage: null }, action.videoId, (video) => ({
        ...video,
        status: 'running',
        errorMessage: null,
        currentStep: null,
      }))
    case 'VIDEO_ANALYSIS_STEP':
      return updateVideo({ ...state, currentStep: action.step }, action.videoId, (video) => ({
        ...video,
        currentStep: { ...action.step, subCurrent: undefined, subTotal: undefined },
      }))
    case 'VIDEO_ANALYSIS_SUB_PROGRESS':
      return updateVideo(state, action.videoId, (video) => {
        const currentStep = video.currentStep
          ? { ...video.currentStep, subCurrent: action.current, subTotal: action.total }
          : null
        return { ...video, currentStep }
      })
    case 'VIDEO_ANALYSIS_DONE':
      return updateVideo(
        {
          ...state,
          rallies: [
            ...state.rallies.filter((rally) => rally.videoId !== action.videoId),
            ...action.rallies,
          ],
        },
        action.videoId,
        (video) => ({ ...video, status: 'done', errorMessage: null, currentStep: null, rallyCount: action.rallies.length }),
      )
    case 'VIDEO_ANALYSIS_ERROR':
      return updateVideo(state, action.videoId, (video) => ({
        ...video,
        status: 'error',
        errorMessage: action.message,
        currentStep: null,
      }))
    case 'SET_VIDEO_DURATION':
      return updateVideo(state, action.videoId, (video) => ({ ...video, duration: action.duration }))
    case 'SET_ACTIVE_VIDEO':
      return { ...state, activeVideoId: action.id }
    case 'SELECT_RALLY':
      return { ...state, selectedRallyId: action.id }
    case 'TOGGLE_INCLUDE':
      return { ...state, rallies: state.rallies.map((rally) => rally.id === action.id ? { ...rally, included: !rally.included } : rally) }
    case 'INCLUDE_ALL':
      return { ...state, rallies: state.rallies.map((rally) => ({ ...rally, included: true })) }
    case 'EXCLUDE_ALL':
      return { ...state, rallies: state.rallies.map((rally) => ({ ...rally, included: false })) }
    case 'RESTORE_RECOMMENDED':
      return { ...state, rallies: state.rallies.map((rally) => ({ ...rally, included: rally.score > INCLUDE_THRESHOLD })) }
    case 'ADJUST_RALLY':
      return { ...state, rallies: state.rallies.map((rally) => rally.id === action.id ? applyRallyAdjustment(rally, action) : rally) }
    default:
      return state
  }
}

const AppContext = createContext<{ state: AppState; dispatch: React.Dispatch<Action> } | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState)
  return <AppContext.Provider value={{ state, dispatch }}>{children}</AppContext.Provider>
}

export function useAppState() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useAppState must be used within AppProvider')
  return ctx
}

export { INCLUDE_THRESHOLD, MIN_SEGMENT_DURATION, applyAutoInclude, reducer }
export type { Action, AppState, ProgressStep, RallySegment, VideoAnalysisStatus, VideoRecord }
```

- [ ] **Step 4: Run reducer tests**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: batch helper and reducer tests pass; source checks for app/components may now fail until later tasks update those files.

- [ ] **Step 5: Commit**

```powershell
git add desktop\src\renderer\state\AppState.tsx desktop\scripts\renderer-flow.test.mjs
git commit -m "feat: add batch workspace state" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 3: Add multi-video import IPC contracts

**Files:**
- Modify: `desktop/src/main/main.ts`
- Modify: `desktop/src/main/preload.ts`
- Modify: `desktop/src/renderer/types.d.ts`
- Test: `desktop/scripts/renderer-flow.test.mjs`

- [ ] **Step 1: Write failing source contract tests**

Add these assertions near the existing `appSource`/source checks:

```js
const mainSource = fs.readFileSync(path.join(root, 'src', 'main', 'main.ts'), 'utf8')
const preloadSource = fs.readFileSync(path.join(root, 'src', 'main', 'preload.ts'), 'utf8')
const typesSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'types.d.ts'), 'utf8')
assert.match(mainSource, /properties: \['openFile', 'multiSelections'\]/)
assert.match(mainSource, /return filePaths/)
assert.match(preloadSource, /openFileDialog: \(\) => ipcRenderer\.invoke\('open-file-dialog'\) as Promise<string\[] \| null>/)
assert.match(typesSource, /openFileDialog: \(\) => Promise<string\[] \| null>/)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: fail because `main.ts`, `preload.ts`, and `types.d.ts` still expose a single file path.

- [ ] **Step 3: Update the main-process file dialog**

In `desktop/src/main/main.ts`, replace the `open-file-dialog` handler with:

```ts
ipcMain.handle('open-file-dialog', async (event) => {
  const parentWin = BrowserWindow.fromWebContents(event.sender)
  const result = await dialog.showOpenDialog(parentWin!, {
    properties: ['openFile', 'multiSelections'],
    filters: [
      { name: 'Video', extensions: ['mp4', 'mkv', 'avi', 'mov'] },
    ],
  })
  if (result.canceled || result.filePaths.length === 0) return null
  const filePaths = result.filePaths

  const recent = store.get('recentProjects')
  const updated = [
    ...filePaths,
    ...recent.filter((p) => !filePaths.includes(p)),
  ].slice(0, 10)
  store.set('recentProjects', updated)

  return filePaths
})
```

- [ ] **Step 4: Update preload and renderer API types**

In `desktop/src/main/preload.ts`, change:

```ts
openFileDialog: () => ipcRenderer.invoke('open-file-dialog') as Promise<string[] | null>,
```

In `desktop/src/renderer/types.d.ts`, change:

```ts
openFileDialog: () => Promise<string[] | null>
```

- [ ] **Step 5: Run contract tests**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: multi-select IPC source checks pass.

- [ ] **Step 6: Commit**

```powershell
git add desktop\src\main\main.ts desktop\src\main\preload.ts desktop\src\renderer\types.d.ts desktop\scripts\renderer-flow.test.mjs
git commit -m "feat: support multi-video file selection" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 4: Add multi-source export IPC and ffmpeg bridge

**Files:**
- Modify: `desktop/src/main/ffmpegBridge.ts`
- Modify: `desktop/src/main/preload.ts`
- Modify: `desktop/src/renderer/types.d.ts`
- Test: `desktop/scripts/renderer-flow.test.mjs`

- [ ] **Step 1: Write failing export source checks**

Add these assertions near the main/preload source checks:

```js
const ffmpegSource = fs.readFileSync(path.join(root, 'src', 'main', 'ffmpegBridge.ts'), 'utf8')
assert.match(ffmpegSource, /interface ExportClip/)
assert.match(ffmpegSource, /videoPath: string/)
assert.match(ffmpegSource, /const sorted = \[\.\.\.clips\]/)
assert.match(ffmpegSource, /inputs\.push\('-ss', String\(clip\.start\), '-t', String\(clip\.end - clip\.start\), '-i', clip\.videoPath\)/)
assert.match(preloadSource, /exportHighlights: \(clips: \{ videoPath: string; start: number; end: number \}\[\]\)/)
assert.match(typesSource, /exportHighlights: \(clips: \{ videoPath: string; start: number; end: number \}\[\]\)/)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: fail because export still accepts one `videoPath` and source-less segments.

- [ ] **Step 3: Update ffmpeg bridge signature and implementation**

In `desktop/src/main/ffmpegBridge.ts`, replace `ExportSegment` with:

```ts
interface ExportClip {
  videoPath: string
  start: number
  end: number
}
```

Replace the handler header and default path logic with:

```ts
ipcMain.handle('export-highlights', async (event, clips: ExportClip[]) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  const firstClip = clips[0]
  if (!firstClip) return { error: 'No clips selected for export' }

  const result = await dialog.showSaveDialog({
    defaultPath: path.join(
      path.dirname(firstClip.videoPath),
      `${path.basename(firstClip.videoPath, path.extname(firstClip.videoPath))}_highlights.mp4`,
    ),
    filters: [{ name: 'MP4', extensions: ['mp4'] }],
  })
```

Replace sorting and ffmpeg input construction with:

```ts
const sorted = [...clips].filter((clip) => clip.end > clip.start)
if (sorted.length === 0) return { error: 'No valid clips selected for export' }

const inputs: string[] = []
const filterParts: string[] = []
for (let i = 0; i < sorted.length; i++) {
  const clip = sorted[i]
  inputs.push('-ss', String(clip.start), '-t', String(clip.end - clip.start), '-i', clip.videoPath)
  filterParts.push(`[${i}:v][${i}:a]`)
}
```

- [ ] **Step 4: Update preload and renderer API types**

In `desktop/src/main/preload.ts`, change export to:

```ts
exportHighlights: (clips: { videoPath: string; start: number; end: number }[]) =>
  ipcRenderer.invoke('export-highlights', clips),
```

In `desktop/src/renderer/types.d.ts`, change export to:

```ts
exportHighlights: (clips: { videoPath: string; start: number; end: number }[]) =>
  Promise<{ error?: string; cancelled?: boolean; outputPath?: string }>
```

- [ ] **Step 5: Run export contract tests**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: multi-source export source checks pass.

- [ ] **Step 6: Commit**

```powershell
git add desktop\src\main\ffmpegBridge.ts desktop\src\main\preload.ts desktop\src\renderer\types.d.ts desktop\scripts\renderer-flow.test.mjs
git commit -m "feat: export highlights from multiple videos" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 5: Add localized batch copy

**Files:**
- Modify: `desktop/src/renderer/i18n/copy.ts`
- Test: `desktop/scripts/renderer-flow.test.mjs`

- [ ] **Step 1: Write failing copy tests**

Add these assertions after existing `COPY` assertions:

```js
assert.equal(COPY.en.welcome.importTitle, 'Import videos')
assert.equal(COPY.zh.welcome.importTitle, '导入多个视频')
assert.equal(COPY.en.batch.videoProgress(2, 5), 'Video 2 / 5')
assert.equal(COPY.zh.batch.videoProgress(2, 5), '第 2 / 5 个视频')
assert.equal(COPY.en.batch.retryVideo, 'Retry')
assert.equal(COPY.zh.batch.retryVideo, '重试')
assert.equal(COPY.en.rallyQueue.sourceLabel('Video 1'), 'Source: Video 1')
assert.equal(COPY.zh.rallyQueue.sourceLabel('Video 1'), '来源：Video 1')
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: fail because `batch` copy and `rallyQueue.sourceLabel` do not exist.

- [ ] **Step 3: Extend copy types**

In `desktop/src/renderer/i18n/copy.ts`, add to `Copy`:

```ts
  batch: {
    title: string
    videoProgress: (current: number, total: number) => string
    pending: string
    running: string
    done: string
    failed: string
    retryVideo: string
    successfulVideos: (done: number, total: number) => string
  }
```

Add to `rallyQueue`:

```ts
    sourceLabel: (source: string) => string
```

- [ ] **Step 4: Update English and Chinese dictionaries**

Change English welcome copy:

```ts
importTitle: 'Import videos',
importDetail: 'Choose one or more match or practice videos. Breakpoint analyzes them as a batch.',
dropHint: 'Or drop video files here',
```

Add English batch copy:

```ts
batch: {
  title: 'Batch videos',
  videoProgress: (current: number, total: number) => `Video ${current} / ${total}`,
  pending: 'Pending',
  running: 'Analyzing',
  done: 'Ready',
  failed: 'Failed',
  retryVideo: 'Retry',
  successfulVideos: (done: number, total: number) => `${done} / ${total} videos ready`,
},
```

Add English source label:

```ts
sourceLabel: (source: string) => `Source: ${source}`,
```

Change Chinese welcome copy:

```ts
importTitle: '导入多个视频',
importDetail: '选择一个或多个比赛/训练视频，Breakpoint 会按批次逐个分析。',
dropHint: '或把多个视频文件拖到这里',
```

Add Chinese batch copy:

```ts
batch: {
  title: '批次视频',
  videoProgress: (current: number, total: number) => `第 ${current} / ${total} 个视频`,
  pending: '等待中',
  running: '分析中',
  done: '已完成',
  failed: '失败',
  retryVideo: '重试',
  successfulVideos: (done: number, total: number) => `${done} / ${total} 个视频已就绪`,
},
```

Add Chinese source label:

```ts
sourceLabel: (source: string) => `来源：${source}`,
```

- [ ] **Step 5: Run copy tests**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: copy tests pass.

- [ ] **Step 6: Commit**

```powershell
git add desktop\src\renderer\i18n\copy.ts desktop\scripts\renderer-flow.test.mjs
git commit -m "feat: add batch workspace copy" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 6: Update welcome screen for multi-video batch creation

**Files:**
- Modify: `desktop/src/renderer/components/WelcomeScreen.tsx`
- Test: `desktop/scripts/renderer-flow.test.mjs`

- [ ] **Step 1: Write failing source checks**

Update the welcome source checks:

```js
assert.match(welcomeSource, /onVideosSelected: \(paths: string\[\]\) => void/)
assert.match(welcomeSource, /const paths = await window\.api\.openFileDialog\(\)/)
assert.match(welcomeSource, /if \(paths && paths\.length > 0\) onVideosSelected\(paths\)/)
assert.match(welcomeSource, /Array\.from\(e\.dataTransfer\.files\)/)
assert.match(welcomeSource, /onVideosSelected\(paths\)/)
assert.doesNotMatch(welcomeSource, /onVideoSelected/)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: fail because `WelcomeScreen` still accepts one path.

- [ ] **Step 3: Update props and open handler**

In `desktop/src/renderer/components/WelcomeScreen.tsx`, change props:

```ts
interface Props {
  onVideosSelected: (paths: string[]) => void
  languageSwitch: ReactNode
}
```

Change component signature:

```ts
export default function WelcomeScreen({ onVideosSelected, languageSwitch }: Props) {
```

Change `handleOpen`:

```ts
const handleOpen = async () => {
  const paths = await window.api.openFileDialog()
  if (paths && paths.length > 0) onVideosSelected(paths)
}
```

- [ ] **Step 4: Update drag-and-drop and recent item behavior**

Replace `handleDrop`:

```ts
const handleDrop = (e: React.DragEvent) => {
  e.preventDefault()
  setDragOver(false)
  const paths = Array.from(e.dataTransfer.files)
    .map((file) => (file as File & { path?: string }).path)
    .filter((path): path is string => Boolean(path))
  if (paths.length > 0) onVideosSelected(paths)
}
```

Change recent click:

```tsx
onClick={() => onVideosSelected([p])}
```

- [ ] **Step 5: Run welcome source checks**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: welcome multi-video checks pass.

- [ ] **Step 6: Commit**

```powershell
git add desktop\src\renderer\components\WelcomeScreen.tsx desktop\scripts\renderer-flow.test.mjs
git commit -m "feat: create batches from welcome screen" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 7: Add batch video list component

**Files:**
- Create: `desktop/src/renderer/components/BatchVideoList.tsx`
- Test: `desktop/scripts/renderer-flow.test.mjs`

- [ ] **Step 1: Write failing component source checks**

Add:

```js
const batchVideoListSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'components', 'BatchVideoList.tsx'), 'utf8')
assert.match(batchVideoListSource, /export default function BatchVideoList/)
assert.match(batchVideoListSource, /videos: VideoRecord\[\]/)
assert.match(batchVideoListSource, /onRetry: \(videoId: string\) => void/)
assert.match(batchVideoListSource, /copy\.batch\.retryVideo/)
assert.match(batchVideoListSource, /copy\.batch\.successfulVideos/)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: fail because `BatchVideoList.tsx` does not exist.

- [ ] **Step 3: Create `BatchVideoList.tsx`**

Create `desktop/src/renderer/components/BatchVideoList.tsx`:

```tsx
import type { CSSProperties } from 'react'
import type { VideoRecord } from '../state/AppState'
import { useCopy } from '../i18n'

interface Props {
  videos: VideoRecord[]
  activeVideoId: string | null
  onSelect: (videoId: string) => void
  onRetry: (videoId: string) => void
}

export default function BatchVideoList({ videos, activeVideoId, onSelect, onRetry }: Props) {
  const copy = useCopy()
  const readyCount = videos.filter((video) => video.status === 'done').length

  return (
    <aside style={shellStyle}>
      <div style={headerStyle}>
        <strong>{copy.batch.title}</strong>
        <span>{copy.batch.successfulVideos(readyCount, videos.length)}</span>
      </div>
      <div style={listStyle}>
        {videos.map((video) => {
          const active = video.id === activeVideoId
          const statusText = video.status === 'pending'
            ? copy.batch.pending
            : video.status === 'running'
              ? copy.batch.running
              : video.status === 'done'
                ? copy.batch.done
                : copy.batch.failed

          return (
            <button
              key={video.id}
              onClick={() => onSelect(video.id)}
              style={{
                ...itemStyle,
                borderColor: active ? 'var(--color-accent)' : 'var(--color-border)',
                background: active ? '#fff7ef' : 'var(--color-surface)',
              }}
            >
              <span style={nameStyle}>{video.displayName}</span>
              <span style={metaStyle}>{statusText} · {video.rallyCount}</span>
              {video.errorMessage && <span style={errorStyle}>{video.errorMessage}</span>}
              {video.status === 'error' && (
                <span
                  onClick={(event) => {
                    event.stopPropagation()
                    onRetry(video.id)
                  }}
                  style={retryStyle}
                >
                  {copy.batch.retryVideo}
                </span>
              )}
            </button>
          )
        })}
      </div>
    </aside>
  )
}

const shellStyle: CSSProperties = { borderRight: '1px solid var(--color-border)', background: 'rgba(250,247,242,0.92)', padding: 12, overflowY: 'auto', minWidth: 220 }
const headerStyle: CSSProperties = { display: 'flex', justifyContent: 'space-between', gap: 8, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-text-secondary)', marginBottom: 10 }
const listStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 8 }
const itemStyle: CSSProperties = { border: '1px solid var(--color-border)', borderRadius: 8, padding: 10, textAlign: 'left', display: 'grid', gap: 5, cursor: 'pointer' }
const nameStyle: CSSProperties = { fontFamily: 'var(--font-display)', fontWeight: 800, color: 'var(--color-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }
const metaStyle: CSSProperties = { fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-secondary)' }
const errorStyle: CSSProperties = { fontSize: 11, color: 'var(--color-danger)', lineHeight: 1.35 }
const retryStyle: CSSProperties = { justifySelf: 'start', fontFamily: 'var(--font-display)', fontWeight: 900, color: 'var(--color-accent)' }
```

- [ ] **Step 4: Run component source checks**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: component source checks pass.

- [ ] **Step 5: Commit**

```powershell
git add desktop\src\renderer\components\BatchVideoList.tsx desktop\scripts\renderer-flow.test.mjs
git commit -m "feat: add batch video list" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 8: Update review queue and match map for source-aware rallies

**Files:**
- Modify: `desktop/src/renderer/components/RallyQueue.tsx`
- Modify: `desktop/src/renderer/components/MatchMap.tsx`
- Modify: `desktop/src/renderer/viewModels/flowCopy.ts`
- Test: `desktop/scripts/renderer-flow.test.mjs`

- [ ] **Step 1: Write failing source-aware queue tests**

Update source checks:

```js
assert.match(rallyQueueSource, /videosById: Map<string, VideoRecord>/)
assert.match(rallyQueueSource, /copy\.rallyQueue\.sourceLabel/)
assert.match(rallyQueueSource, /dispatch\(\{ type: 'SELECT_RALLY', id: segment\.id \}\)/)
assert.match(rallyQueueSource, /dispatch\(\{ type: 'SET_ACTIVE_VIDEO', id: segment\.videoId \}\)/)
assert.match(rallyQueueSource, /dispatch\(\{ type: 'TOGGLE_INCLUDE', id: segment\.id \}\)/)
assert.match(rallyQueueSource, /dispatch\(\{ type: 'ADJUST_RALLY', id: segment\.id/)
assert.match(matchMapSource, /getRalliesForVideo/)
assert.match(matchMapSource, /activeVideoId/)
assert.match(matchMapSource, /selectedRallyId/)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: fail because queue and map still use numeric segment indexes.

- [ ] **Step 3: Update `flowCopy.ts` type imports**

Change import:

```ts
import type { ProgressStep, RallySegment } from '../state/AppState'
```

Change `getReviewTaskSummary` and `getRallyTitle` parameter types from `Segment` to `RallySegment` picks:

```ts
segments: Pick<RallySegment, 'included' | 'start' | 'end' | 'startAdjusted' | 'endAdjusted'>[],
```

```ts
segment: Pick<RallySegment, 'sourceIndex' | 'start' | 'end' | 'score' | 'features'>,
```

Update `formatSegmentNumber` and title usage:

```ts
function formatSegmentNumber(sourceIndex: number): string {
  return `#${String(sourceIndex + 1).padStart(2, '0')}`
}
```

Use `segment.sourceIndex` in `getRallyTitle`.

- [ ] **Step 4: Update `RallyQueue.tsx` props and source labels**

Change imports:

```ts
import { useAppState, type RallySegment, type VideoRecord } from '../state/AppState'
import { getSortedRallies } from '../batchFlow'
```

Inside component:

```ts
const { videos, rallies, selectedRallyId } = state
const segments = getSortedRallies(rallies, videos)
const videosById = new Map(videos.map((video) => [video.id, video]))
```

Change selection:

```tsx
const isSelected = segment.id === selectedRallyId
```

Change card actions:

```tsx
onSelect={() => {
  dispatch({ type: 'SELECT_RALLY', id: segment.id })
  dispatch({ type: 'SET_ACTIVE_VIDEO', id: segment.videoId })
  onSeekAndPlay(segment.startAdjusted ?? segment.start)
}}
onToggle={() => dispatch({ type: 'TOGGLE_INCLUDE', id: segment.id })}
sourceLabel={copy.rallyQueue.sourceLabel(videosById.get(segment.videoId)?.displayName ?? segment.videoId)}
```

Change `RallyCard` props to use `RallySegment` and render the source label under the title:

```tsx
<div style={sourceStyle}>{sourceLabel}</div>
```

Change `TrimEditor` action dispatches:

```ts
dispatch({ type: 'ADJUST_RALLY', id: segment.id, start: next })
dispatch({ type: 'ADJUST_RALLY', id: segment.id, end: next })
```

- [ ] **Step 5: Update `MatchMap.tsx` for active video**

Import helper:

```ts
import { getRalliesForVideo } from '../batchFlow'
```

Inside component:

```ts
const { rallies, selectedRallyId, activeVideoId, videos } = state
const activeVideo = videos.find((video) => video.id === activeVideoId)
const segments = activeVideoId ? getRalliesForVideo(rallies, activeVideoId) : []
const videoDuration = activeVideo?.duration ?? 0
```

Change selected check and click:

```tsx
const isSelected = segment.id === selectedRallyId
dispatch({ type: 'SELECT_RALLY', id: segment.id })
dispatch({ type: 'SET_ACTIVE_VIDEO', id: segment.videoId })
```

- [ ] **Step 6: Run source-aware queue tests**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: queue and match map source checks pass.

- [ ] **Step 7: Commit**

```powershell
git add desktop\src\renderer\components\RallyQueue.tsx desktop\src\renderer\components\MatchMap.tsx desktop\src\renderer\viewModels\flowCopy.ts desktop\scripts\renderer-flow.test.mjs
git commit -m "feat: review source-aware rally queue" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 9: Orchestrate sequential batch analysis in App

**Files:**
- Modify: `desktop/src/renderer/App.tsx`
- Modify: `desktop/src/renderer/components/AnalysisScreen.tsx`
- Modify: `desktop/src/renderer/components/AnalysisProgressPanel.tsx`
- Test: `desktop/scripts/renderer-flow.test.mjs`

- [ ] **Step 1: Write failing app orchestration source checks**

Update `appSource` and analysis screen checks:

```js
assert.match(appSource, /createVideoRecords/)
assert.match(appSource, /createRalliesForVideo/)
assert.match(appSource, /getExportClips/)
assert.match(appSource, /const analyzeVideo = useCallback/)
assert.match(appSource, /const startBatchAnalysis = useCallback/)
assert.match(appSource, /for \(const video of videosToAnalyze\)/)
assert.match(appSource, /dispatch\(\{ type: 'CREATE_BATCH', videos \}\)/)
assert.match(appSource, /dispatch\(\{ type: 'VIDEO_ANALYSIS_DONE', videoId: video\.id, rallies \}\)/)
assert.match(appSource, /window\.api\.exportHighlights\(clips\)/)
assert.match(appSource, /<BatchVideoList/)
assert.match(analysisScreenSource, /batchLabel\?: string/)
assert.match(analysisPanelSource, /batchLabel/)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: fail because `App.tsx` still orchestrates one video.

- [ ] **Step 3: Add analysis screen batch label prop**

In `AnalysisScreen.tsx`, add prop:

```ts
batchLabel?: string
```

Pass it to `AnalysisProgressPanel`:

```tsx
<AnalysisProgressPanel
  step={step}
  errorMessage={errorMessage}
  onCancel={onCancel}
  onReturnWelcome={onReturnWelcome}
  onRetry={onRetry}
  batchLabel={batchLabel}
/>
```

In `AnalysisProgressPanel.tsx`, add prop:

```ts
batchLabel?: string
```

Render it above the stage label:

```tsx
{batchLabel && <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-text-secondary)', marginBottom: 10 }}>{batchLabel}</div>}
```

- [ ] **Step 4: Update `App.tsx` imports**

Add:

```ts
import BatchVideoList from './components/BatchVideoList'
import { createRalliesForVideo, createVideoRecords, getExportClips, getSortedRallies } from './batchFlow'
import type { VideoRecord } from './state/AppState'
```

- [ ] **Step 5: Add `analyzeVideo` helper in `AppInner`**

Replace single-video `startAnalysis` with:

```ts
const analyzeVideo = useCallback(async (video: VideoRecord) => {
  dispatch({ type: 'VIDEO_ANALYSIS_START', videoId: video.id })

  const existing = await window.api.loadReport(video.path)
  if (hasReusableAnalysisReport(existing)) {
    const rallies = createRalliesForVideo(video, existing)
    dispatch({ type: 'VIDEO_ANALYSIS_DONE', videoId: video.id, rallies })
    return true
  }

  const cleanup = window.api.onAnalysisProgress((event) => {
    if (event.type === 'step') {
      dispatch({
        type: 'VIDEO_ANALYSIS_STEP',
        videoId: video.id,
        step: { step: event.step!, total: event.total!, label: event.label! },
      })
    } else if (event.type === 'step_done') {
      dispatch({
        type: 'VIDEO_ANALYSIS_STEP',
        videoId: video.id,
        step: {
          step: event.step!,
          total: event.total ?? 4,
          label: event.label ?? '',
          elapsed: event.elapsed,
        },
      })
    } else if (event.type === 'progress') {
      dispatch({ type: 'VIDEO_ANALYSIS_SUB_PROGRESS', videoId: video.id, current: event.current!, total: event.sub_total! })
    } else if (event.type === 'complete') {
      cleanup()
    } else if (event.type === 'error') {
      cleanup()
      dispatch({ type: 'VIDEO_ANALYSIS_ERROR', videoId: video.id, message: event.message ?? copy.app.unknownError })
    }
  })

  const result = await window.api.runAnalysis(video.path)
  cleanup()
  if (result.error) {
    dispatch({ type: 'VIDEO_ANALYSIS_ERROR', videoId: video.id, message: result.error })
    return false
  }

  const report = await window.api.loadReport(video.path)
  if (!hasReusableAnalysisReport(report)) {
    dispatch({ type: 'VIDEO_ANALYSIS_ERROR', videoId: video.id, message: copy.app.reportMissing })
    return false
  }

  const rallies = createRalliesForVideo(video, report)
  dispatch({ type: 'VIDEO_ANALYSIS_DONE', videoId: video.id, rallies })
  return true
}, [copy.app.reportMissing, copy.app.unknownError, dispatch])
```

- [ ] **Step 6: Add batch start and retry handlers**

Add:

```ts
const startBatchAnalysis = useCallback(async (videosToAnalyze: VideoRecord[]) => {
  dispatch({ type: 'BATCH_ANALYSIS_START' })
  for (const video of videosToAnalyze) {
    await analyzeVideo(video)
  }
  dispatch({ type: 'BATCH_ANALYSIS_DONE' })
}, [analyzeVideo, dispatch])

const handleVideosSelected = useCallback((paths: string[]) => {
  const videos = createVideoRecords(paths)
  dispatch({ type: 'CREATE_BATCH', videos })
  setExportResult(null)
  startBatchAnalysis(videos)
}, [dispatch, startBatchAnalysis])

const handleRetryVideo = useCallback((videoId: string) => {
  const video = state.videos.find((item) => item.id === videoId)
  if (!video) {
    setExportResult({ status: 'error', message: `${copy.app.exportFailedPrefix}${copy.app.unknownError}` })
    return
  }
  dispatch({ type: 'VIDEO_ANALYSIS_RETRY', videoId })
  startBatchAnalysis([video])
}, [copy.app.exportFailedPrefix, copy.app.unknownError, dispatch, startBatchAnalysis, state.videos])
```

- [ ] **Step 7: Update rendering and export**

Use active video:

```ts
const activeVideo = state.videos.find((video) => video.id === state.activeVideoId) ?? null
const selectedRally = state.selectedRallyId ? state.rallies.find((rally) => rally.id === state.selectedRallyId) : null
```

Welcome:

```tsx
if (state.videos.length === 0) {
  return <WelcomeScreen onVideosSelected={handleVideosSelected} languageSwitch={languageSwitch} />
}
```

Analysis screen batch label:

```tsx
const runningVideoIndex = state.videos.findIndex((video) => video.status === 'running')
const batchLabel = runningVideoIndex >= 0 ? copy.batch.videoProgress(runningVideoIndex + 1, state.videos.length) : undefined
```

Export:

```ts
const clips = getExportClips(state.rallies, state.videos)
if (clips.length === 0) {
  setExportResult({ status: 'error', message: getExportActionCopy(0, false, copy) })
  return
}
const totalDuration = clips.reduce((sum, clip) => sum + (clip.end - clip.start), 0)
const result = await window.api.exportHighlights(clips)
```

Review layout should include:

```tsx
<BatchVideoList
  videos={state.videos}
  activeVideoId={state.activeVideoId}
  onSelect={(videoId) => dispatch({ type: 'SET_ACTIVE_VIDEO', id: videoId })}
  onRetry={handleRetryVideo}
/>
```

Player should use:

```tsx
{activeVideo && (
  <VideoPlayer
    videoPath={activeVideo.path}
    ...
    pauseAt={selectedRally ? selectedRally.endAdjusted ?? selectedRally.end : null}
    onDurationChange={(duration) => dispatch({ type: 'SET_VIDEO_DURATION', videoId: activeVideo.id, duration })}
  />
)}
```

- [ ] **Step 8: Run app orchestration source checks**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: app orchestration source checks pass.

- [ ] **Step 9: Commit**

```powershell
git add desktop\src\renderer\App.tsx desktop\src\renderer\components\AnalysisScreen.tsx desktop\src\renderer\components\AnalysisProgressPanel.tsx desktop\scripts\renderer-flow.test.mjs
git commit -m "feat: orchestrate sequential batch analysis" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 10: Reset player state when switching source videos

**Files:**
- Modify: `desktop/src/renderer/components/VideoPlayer.tsx`
- Test: `desktop/scripts/renderer-flow.test.mjs`

- [ ] **Step 1: Write failing source check**

Add:

```js
assert.match(videoPlayerSource, /useEffect\(\(\) => \{\s*setPlaying\(false\)\s*setCurrentTime\(0\)\s*setDuration\(0\)\s*pauseFiredRef\.current = false\s*\}, \[videoPath\]\)/)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: fail because player state does not reset on `videoPath` changes.

- [ ] **Step 3: Add player reset effect**

In `VideoPlayer.tsx`, after refs/state are declared, add:

```ts
useEffect(() => {
  setPlaying(false)
  setCurrentTime(0)
  setDuration(0)
  pauseFiredRef.current = false
}, [videoPath])
```

If `pauseFiredRef` is declared lower in the file, move its declaration above this effect.

- [ ] **Step 4: Run player source check**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: player reset source check passes.

- [ ] **Step 5: Commit**

```powershell
git add desktop\src\renderer\components\VideoPlayer.tsx desktop\scripts\renderer-flow.test.mjs
git commit -m "fix: reset video player on source switch" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 11: Final integration checks and build

**Files:**
- Modify: any file reported by `npm run build` with stale single-video names, then re-run verification before committing.

- [ ] **Step 1: Run renderer flow tests**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: all renderer flow tests pass.

- [ ] **Step 2: Run TypeScript/Vite build**

Run:

```powershell
Set-Location .\desktop
npm run build
```

Expected: `tsc && vite build` completes with exit code 0.

- [ ] **Step 3: Fix any type or build failures**

If `npm run build` reports stale names from the single-video model, update the failing file to use the batch names defined in this plan:

```ts
state.videos
state.rallies
state.activeVideoId
state.selectedRallyId
dispatch({ type: 'SELECT_RALLY', id })
dispatch({ type: 'SET_ACTIVE_VIDEO', id })
dispatch({ type: 'ADJUST_RALLY', id, start })
dispatch({ type: 'ADJUST_RALLY', id, end })
```

Run `npm run build` again after each fix until it exits 0.

- [ ] **Step 4: Verify repository status**

Run:

```powershell
git --no-pager status --short
```

Expected: only intentional source changes are present before the final commit.

- [ ] **Step 5: Commit final fixes**

```powershell
git add desktop
git commit -m "feat: complete multi-video desktop batch workflow" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
