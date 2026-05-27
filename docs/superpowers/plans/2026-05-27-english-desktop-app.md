# English Desktop App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a bilingual English/Chinese desktop app UI with system-derived first-run language, user switching, and persisted preference.

**Architecture:** Add a small typed renderer i18n layer and keep business state language-agnostic. Components read copy through React hooks, while view-model helpers receive a typed copy dictionary for dynamic strings and remain independently testable.

**Tech Stack:** React 18, TypeScript, Electron renderer, Vite, Node-based renderer flow tests.

---

## File structure

- Create: `desktop/src/renderer/i18n/copy.ts` — typed copy dictionaries for English and Chinese, plus `Language`, `Copy`, `COPY`, and language labels.
- Create: `desktop/src/renderer/i18n/language.ts` — pure helpers for default language detection, preference parsing, safe preference read/write.
- Create: `desktop/src/renderer/i18n/LanguageProvider.tsx` — React provider and hooks for current language and copy access.
- Create: `desktop/src/renderer/i18n/index.ts` — small barrel export for renderer imports.
- Modify: `desktop/src/renderer/viewModels/flowCopy.ts` — accept `Copy` for user-facing dynamic text.
- Modify: `desktop/src/renderer/App.tsx` — wrap app in `LanguageProvider`, localize top-level messages, pass language switch into open-video screens.
- Modify: `desktop/src/renderer/components/WelcomeScreen.tsx` — localize welcome/import UI and add main language switch.
- Modify: `desktop/src/renderer/components/AnalysisScreen.tsx` — localize analysis title and expose compact language switch.
- Modify: `desktop/src/renderer/components/AnalysisProgressPanel.tsx` — localize analysis progress and error UI.
- Modify: `desktop/src/renderer/components/MatchMap.tsx` — localize map copy and tooltips.
- Modify: `desktop/src/renderer/components/RallyQueue.tsx` — localize review queue, trim editor, export panel, tone labels, and dynamic rally copy.
- Modify: `desktop/scripts/renderer-flow.test.mjs` — add tests for language helpers and bilingual flow copy.

## Task 1: Add typed i18n copy and language helpers

**Files:**
- Create: `desktop/src/renderer/i18n/copy.ts`
- Create: `desktop/src/renderer/i18n/language.ts`
- Create: `desktop/src/renderer/i18n/index.ts`
- Test: `desktop/scripts/renderer-flow.test.mjs`

- [ ] **Step 1: Write failing language-helper tests**

Add this import block after the existing `AppState.tsx` load in `desktop/scripts/renderer-flow.test.mjs`:

```js
const {
  COPY,
  LANGUAGE_LABELS,
} = loadTsModule(path.join('src', 'renderer', 'i18n', 'copy.ts'))

const {
  detectDefaultLanguage,
  parseStoredLanguage,
  readStoredLanguage,
  writeStoredLanguage,
  LANGUAGE_STORAGE_KEY,
} = loadTsModule(path.join('src', 'renderer', 'i18n', 'language.ts'))
```

Add these assertions after `const plain = ...`:

```js
assert.equal(LANGUAGE_STORAGE_KEY, 'bp-desktop-language')
assert.equal(detectDefaultLanguage('zh-CN'), 'zh')
assert.equal(detectDefaultLanguage('zh-Hant-TW'), 'zh')
assert.equal(detectDefaultLanguage('en-US'), 'en')
assert.equal(detectDefaultLanguage('fr-FR'), 'en')
assert.equal(detectDefaultLanguage(undefined), 'en')
assert.equal(parseStoredLanguage('zh'), 'zh')
assert.equal(parseStoredLanguage('en'), 'en')
assert.equal(parseStoredLanguage('ja'), null)
assert.equal(LANGUAGE_LABELS.en, 'EN')
assert.equal(LANGUAGE_LABELS.zh, '中文')
assert.equal(COPY.en.welcome.importTitle, 'Import new video')
assert.equal(COPY.zh.welcome.importTitle, '导入新视频')

const storage = new Map()
const storageLike = {
  getItem: (key) => storage.has(key) ? storage.get(key) : null,
  setItem: (key, value) => storage.set(key, value),
}
assert.equal(readStoredLanguage(storageLike), null)
assert.equal(writeStoredLanguage(storageLike, 'zh'), true)
assert.equal(readStoredLanguage(storageLike), 'zh')
assert.equal(writeStoredLanguage({ setItem: () => { throw new Error('blocked') } }, 'en'), false)
assert.equal(readStoredLanguage({ getItem: () => { throw new Error('blocked') } }), null)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: fail with a module-not-found or unexpected import error for `src\renderer\i18n\copy.ts`.

- [ ] **Step 3: Create typed copy dictionary**

Create `desktop/src/renderer/i18n/copy.ts`:

```ts
export type Language = 'en' | 'zh'

export const LANGUAGE_LABELS: Record<Language, string> = {
  en: 'EN',
  zh: '中文',
}

export const COPY = {
  en: {
    common: {
      appName: 'Breakpoint',
      desktop: 'Desktop',
      open: 'Open',
      edited: 'edited',
      hitCountUnknown: '?',
    },
    language: {
      label: 'Language',
    },
    welcome: {
      eyebrow: 'AI-powered tennis highlight editor',
      description: 'Your best rallies, automatically surfaced. Breakpoint turns broadcast-view tennis matches and practice footage into a clean highlight reel. AI audio and vision analysis detects each rally, ranks the intensity, removes 70%-80% of dead time, and keeps the moments worth replaying.',
      startLabel: 'Start',
      importTitle: 'Import new video',
      importDetail: 'Choose a match or practice video. Analysis starts automatically after import.',
      dropHint: 'Or drop a video file here',
      recentTitle: 'Open recent videos',
      shortcutImport: 'Import video',
      shortcutQuit: 'Quit',
    },
    app: {
      resourceErrorTitle: 'Resource Error',
      missingResources: 'Installer missing bundled resources:',
      reviewTitle: 'Review rally clips',
      returnWelcome: 'Back to welcome',
      rerunAnalysis: 'Analyze again',
      exportFailedPrefix: 'Export failed:',
      exportComplete: 'Highlight reel exported',
      cancelled: 'Cancelled',
      reportMissing: 'Report file not found',
      unknownError: 'Unknown error',
    },
    analysisScreen: {
      problemTitle: 'Analysis issue',
      runningTitle: 'Analyzing video',
    },
    analysisPanel: {
      failedEyebrow: 'Processing failed',
      failedTitle: 'Analysis did not finish',
      retry: 'Analyze again',
      returnWelcome: 'Back to welcome',
      autoStart: 'Auto start',
      headline: 'AI is analyzing\\nthe full video',
      intro: 'After a new video is imported, Breakpoint reads the full match and filters it into highlight candidates worth keeping.',
      cancel: 'Cancel processing',
      subProgressTitle: 'Filtering progress',
      statusDone: 'Done',
      statusCurrent: 'In progress',
      statusNext: 'Next',
      stages: [
        { title: 'Read full video', detail: 'Quickly load the footage and prepare it for automatic trimming.' },
        { title: 'Find match segments', detail: 'Identify candidate match sections and skip obvious waiting time first.' },
        { title: 'Filter highlight moments', detail: 'The longest step. Vision processing keeps updating group progress here.' },
        { title: 'Prepare review list', detail: 'When this finishes, review the clips to keep and export.' },
      ],
    },
    matchMap: {
      title: 'Full match map',
      subtitle: 'Tall bars are suggested keeps; gray bars are removed waiting time, warmups, and breaks.',
      highlight: 'Highlight',
      keep: 'Keep',
      discarded: 'Discarded',
      intensity: 'Intensity',
      showAll: 'Show all rallies',
      recommendedOnly: 'Suggested only',
    },
    rallyQueue: {
      title: 'Rally queue',
      exportCount: (selected: number, total: number) => `${selected} / ${total} rallies will be exported`,
      includeAll: 'Select all',
      restoreRecommended: 'Recommended',
      excludeAll: 'Clear',
      empty: 'No rally clips to review.',
      exportSummary: (selected: number) => `${selected} rallies selected. Confirm the list and combine them into one highlight reel.`,
      exportDuration: (duration: string) => `Reel about ${duration}`,
      cancelExport: 'Cancel export',
      openExport: 'Open',
      toneHighlight: 'Top pick',
      toneKeep: 'Suggested keep',
      toneDiscarded: 'Discarded',
      hits: (count: number | string) => `${count} hits`,
      intensity: (score: string) => `Intensity ${score}`,
      start: 'Start',
      end: 'End',
      trimHelp: (start: string, end: string) => `Fine-tune start on the left and end on the right. Original: ${start} – ${end}`,
      reset: 'Reset',
    },
    flow: {
      stages: [
        { title: 'Reading full video', detail: 'Preparing match footage. The next step starts automatically after import.', stageLabel: 'Reading' },
        { title: 'Finding match segments', detail: 'Organizing the full video into candidate clips for review.', stageLabel: 'Finding' },
        { title: 'Filtering highlight moments', detail: 'Checking each group for shareable highlight clips. Keep this window open.', stageLabel: 'Filtering' },
        { title: 'Preparing review list', detail: 'Almost ready to review clips and export a highlight reel.', stageLabel: 'Preparing' },
      ],
      waitingTitle: 'Ready to process',
      waitingDetail: 'Analysis starts automatically after you import a video.',
      waitingStageLabel: 'Waiting',
      groupLabel: (current: number, total: number) => `${current} / ${total} groups`,
      progressLabel: (step: number, total: number, groupLabel?: string) => `${step} / ${total}${groupLabel ? ` · ${groupLabel}` : ''}`,
      visualHeadlineFiltering: 'Filtering highlight clips',
      visualHeadlineAnalyzing: 'Analyzing video',
      visualDetail: (segment: number, total: number, percent: number) => `Segment ${segment} / ${total} · ${percent}%`,
      reviewInstruction: 'Pick the video clips to keep, then export a highlight reel.',
      exportNoSelection: 'Select rallies to export',
      exportSelected: 'Export selected rallies',
      exporting: (selected: number) => `Exporting ${selected} rallies`,
      rallyTitle: {
        multiHit: 'Long',
        highIntensity: 'High-intensity',
        short: 'Short',
        suffix: 'rally',
        recommended: 'Recommended rally',
        regular: 'Regular rally',
      },
    },
  },
  zh: {
    common: {
      appName: 'Breakpoint',
      desktop: 'Desktop',
      open: '打开',
      edited: '已编辑',
      hitCountUnknown: '?',
    },
    language: {
      label: '语言',
    },
    welcome: {
      eyebrow: 'AI驱动的网球精彩集锦编辑器',
      description: '你的精彩回合，自动呈现。Breakpoint 将广播视角的网球比赛或训练录像一键转化为精彩集锦。AI 音频与视觉分析自动识别每一个回合，按激烈程度排序，剔除 70%–80% 的垃圾时间，只留下值得回看的高光时刻。',
      startLabel: '开始',
      importTitle: '导入新视频',
      importDetail: '选择比赛或练习视频，导入后自动开始处理',
      dropHint: '或把视频文件拖到这里',
      recentTitle: '打开之前的视频',
      shortcutImport: '导入视频',
      shortcutQuit: '退出',
    },
    app: {
      resourceErrorTitle: '资源错误',
      missingResources: '安装包缺少必要资源：',
      reviewTitle: '确认回合片段',
      returnWelcome: '返回欢迎页',
      rerunAnalysis: '重新处理',
      exportFailedPrefix: '导出失败：',
      exportComplete: '精彩合集已导出',
      cancelled: 'Cancelled',
      reportMissing: 'Report file not found',
      unknownError: 'Unknown error',
    },
    analysisScreen: {
      problemTitle: '分析遇到问题',
      runningTitle: '正在分析视频',
    },
    analysisPanel: {
      failedEyebrow: '处理失败',
      failedTitle: '分析没有完成',
      retry: '重新处理',
      returnWelcome: '返回欢迎页',
      autoStart: '自动开始',
      headline: '正在用 AI\\n分析整场视频',
      intro: '新视频导入后会自动开始处理。Breakpoint 会先读取整场比赛，再逐段筛选值得保留的精彩瞬间。',
      cancel: '取消处理',
      subProgressTitle: '筛选进度',
      statusDone: '完成',
      statusCurrent: '进行中',
      statusNext: '下一步',
      stages: [
        { title: '读取整场视频', detail: '快速加载视频内容，为后续自动精剪做准备。' },
        { title: '定位比赛片段', detail: '找出可能值得保留的比赛段落，先跳过明显的等待时间。' },
        { title: '筛选精彩瞬间', detail: '耗时最长的一步，视觉处理会在这里持续更新分组进度。' },
        { title: '准备确认列表', detail: '完成后进入剪辑页，确认要保留的片段并导出。' },
      ],
    },
    matchMap: {
      title: '整场比赛地图',
      subtitle: '高条是建议保留的回合，灰色是已剔除的等待、拉球和间歇片段。',
      highlight: '高光',
      keep: '可保留',
      discarded: '已剔除',
      intensity: '强度',
      showAll: '显示全部回合',
      recommendedOnly: '只看建议保留',
    },
    rallyQueue: {
      title: '回合队列',
      exportCount: (selected: number, total: number) => `${selected} / ${total} 个回合将被导出`,
      includeAll: '全选',
      restoreRecommended: '推荐',
      excludeAll: '清空',
      empty: '没有可确认的回合片段。',
      exportSummary: (selected: number) => `已选择 ${selected} 个回合。确认列表后，将它们合成为一个精彩合集。`,
      exportDuration: (duration: string) => `合集约 ${duration}`,
      cancelExport: '取消导出',
      openExport: '打开',
      toneHighlight: '高分推荐',
      toneKeep: '建议保留',
      toneDiscarded: '已剔除',
      hits: (count: number | string) => `${count} 次击球`,
      intensity: (score: string) => `强度 ${score}`,
      start: '开始',
      end: '结束',
      trimHelp: (start: string, end: string) => `左侧微调开始，右侧微调结束。原始：${start} – ${end}`,
      reset: '重置',
    },
    flow: {
      stages: [
        { title: '正在读取整场视频', detail: '正在准备比赛素材，导入后会自动进入下一步。', stageLabel: '读取中' },
        { title: '正在定位比赛片段', detail: '正在把完整视频整理成可确认的候选片段。', stageLabel: '定位中' },
        { title: '正在筛选精彩瞬间', detail: '正在逐组确认可分享的高光片段，请保持窗口打开。', stageLabel: '筛选中' },
        { title: '正在准备确认列表', detail: '即将进入剪辑页，你可以确认片段并导出合集。', stageLabel: '准备中' },
      ],
      waitingTitle: '准备开始处理',
      waitingDetail: '导入视频后会自动开始分析。',
      waitingStageLabel: '等待视频',
      groupLabel: (current: number, total: number) => `${current} / ${total} 组`,
      progressLabel: (step: number, total: number, groupLabel?: string) => `${step} / ${total}${groupLabel ? ` · ${groupLabel}` : ''}`,
      visualHeadlineFiltering: '正在筛选精彩片段',
      visualHeadlineAnalyzing: '正在分析视频',
      visualDetail: (segment: number, total: number, percent: number) => `片段 ${segment} / ${total} · 当前 ${percent}%`,
      reviewInstruction: '挑选视频片段，确认保留后导出精彩合集。',
      exportNoSelection: '选择回合后导出',
      exportSelected: '导出已选择的回合',
      exporting: (selected: number) => `正在导出 ${selected} 个回合`,
      rallyTitle: {
        multiHit: '多拍',
        highIntensity: '高强度',
        short: '短',
        suffix: '回合',
        recommended: '推荐回合',
        regular: '普通回合',
      },
    },
  },
} as const

export type Copy = typeof COPY.en
```

- [ ] **Step 4: Create pure language helpers**

Create `desktop/src/renderer/i18n/language.ts`:

```ts
import type { Language } from './copy'

export const LANGUAGE_STORAGE_KEY = 'bp-desktop-language'

interface StorageLike {
  getItem: (key: string) => string | null
  setItem: (key: string, value: string) => void
}

export function parseStoredLanguage(value: string | null | undefined): Language | null {
  return value === 'en' || value === 'zh' ? value : null
}

export function detectDefaultLanguage(locale: string | undefined): Language {
  return locale?.toLowerCase().startsWith('zh') ? 'zh' : 'en'
}

export function readStoredLanguage(storage: StorageLike | undefined): Language | null {
  if (!storage) return null
  try {
    return parseStoredLanguage(storage.getItem(LANGUAGE_STORAGE_KEY))
  } catch {
    return null
  }
}

export function writeStoredLanguage(storage: StorageLike | undefined, language: Language): boolean {
  if (!storage) return false
  try {
    storage.setItem(LANGUAGE_STORAGE_KEY, language)
    return true
  } catch {
    return false
  }
}
```

- [ ] **Step 5: Create i18n barrel**

Create `desktop/src/renderer/i18n/index.ts`:

```ts
export { COPY, LANGUAGE_LABELS } from './copy'
export type { Copy, Language } from './copy'
export {
  LANGUAGE_STORAGE_KEY,
  detectDefaultLanguage,
  parseStoredLanguage,
  readStoredLanguage,
  writeStoredLanguage,
} from './language'
```

- [ ] **Step 6: Run language-helper tests**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: the new language-helper assertions pass. Existing flow-copy assertions still pass because no flow-copy signatures have changed yet.

- [ ] **Step 7: Commit task 1**

Run:

```powershell
git add desktop\src\renderer\i18n\copy.ts desktop\src\renderer\i18n\language.ts desktop\src\renderer\i18n\index.ts desktop\scripts\renderer-flow.test.mjs
git commit -m "feat: add desktop i18n copy"
```

## Task 2: Localize flow-copy view-model helpers

**Files:**
- Modify: `desktop/src/renderer/viewModels/flowCopy.ts`
- Modify: `desktop/scripts/renderer-flow.test.mjs`
- Test: `desktop/scripts/renderer-flow.test.mjs`

- [ ] **Step 1: Write failing bilingual flow-copy tests**

Change the existing flow-copy import in `desktop/scripts/renderer-flow.test.mjs` to also import `getAnalysisVisualState`:

```js
const {
  getAnalysisStageView,
  getAnalysisStageNumber,
  getReviewTaskSummary,
  getExportActionCopy,
  formatClipDuration,
  getRallyTitle,
  getSegmentTone,
  getAdjustedTimeRange,
  getAnalysisVisualState,
} = loadTsModule(path.join('src', 'renderer', 'viewModels', 'flowCopy.ts'))
```

Replace the first `getAnalysisStageView` assertion block with:

```js
assert.deepEqual(plain(getAnalysisStageView(null, COPY.zh)), {
  title: '准备开始处理',
  detail: '导入视频后会自动开始分析。',
  stageLabel: '等待视频',
  progressLabel: '0 / 4',
  progress: 0,
  subProgress: null,
})
assert.deepEqual(plain(getAnalysisStageView(null, COPY.en)), {
  title: 'Ready to process',
  detail: 'Analysis starts automatically after you import a video.',
  stageLabel: 'Waiting',
  progressLabel: '0 / 4',
  progress: 0,
  subProgress: null,
})
```

Replace export and rally-title assertions with bilingual versions:

```js
assert.equal(getReviewTaskSummary([
  { start: 10, end: 20, score: 2.4, included: true, features: {}, index: 0 },
  { start: 40, end: 52.5, score: 1.4, included: false, features: {}, index: 1 },
  { start: 70, end: 95, score: 2.1, included: true, startAdjusted: 72, endAdjusted: 93, features: {}, index: 2 },
], COPY.en).instruction, 'Pick the video clips to keep, then export a highlight reel.')
assert.equal(getReviewTaskSummary([
  { start: 10, end: 20, score: 2.4, included: true, features: {}, index: 0 },
], COPY.zh).instruction, '挑选视频片段，确认保留后导出精彩合集。')
assert.equal(getExportActionCopy(0, false, COPY.en), 'Select rallies to export')
assert.equal(getExportActionCopy(3, false, COPY.en), 'Export selected rallies')
assert.equal(getExportActionCopy(3, true, COPY.en), 'Exporting 3 rallies')
assert.equal(getExportActionCopy(0, false, COPY.zh), '选择回合后导出')
assert.equal(getExportActionCopy(3, false, COPY.zh), '导出已选择的回合')
assert.equal(getExportActionCopy(3, true, COPY.zh), '正在导出 3 个回合')
assert.equal(getRallyTitle(highMultiHitSegment, COPY.en), 'Long High-intensity rally #08')
assert.equal(getRallyTitle(highMultiHitSegment, COPY.zh), '多拍高强度回合 #08')
assert.equal(getRallyTitle({
  index: 3,
  start: 20,
  end: 25,
  score: 1.8,
  included: true,
  features: { hit_count: 5 },
}, COPY.en), 'Short rally #04')
assert.equal(getRallyTitle({
  index: 4,
  start: 40,
  end: 55,
  score: 1.1,
  included: false,
  features: {},
}, COPY.en), 'Regular rally #05')
assert.equal(getAnalysisVisualState({ step: 3, total: 4, label: 'vision ranking', subCurrent: 2, subTotal: 8 }, COPY.en).headline, 'Filtering highlight clips')
assert.equal(getAnalysisVisualState({ step: 1, total: 4, label: 'load' }, COPY.zh).headline, '正在分析视频')
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: fail because `flowCopy.ts` functions do not yet accept `COPY.en` / `COPY.zh`.

- [ ] **Step 3: Update `flowCopy.ts` imports and function signatures**

In `desktop/src/renderer/viewModels/flowCopy.ts`, remove the hard-coded `ANALYSIS_STAGES` constant and add this import:

```ts
import type { Copy } from '../i18n'
```

Update these function signatures:

```ts
export function getAnalysisVisualState(step: ProgressStep | null, copy: Copy): AnalysisVisualState
export function getAnalysisStageView(step: ProgressStep | null, copy: Copy): AnalysisStageView
export function getReviewTaskSummary(segments: Pick<Segment, 'included' | 'start' | 'end' | 'startAdjusted' | 'endAdjusted'>[], copy: Copy)
export function getExportActionCopy(selectedCount: number, exporting: boolean, copy: Copy): string
export function getRallyTitle(segment: Pick<Segment, 'index' | 'start' | 'end' | 'score' | 'features'>, copy: Copy): string
```

- [ ] **Step 4: Update flow-copy implementations**

Apply these implementation changes in `desktop/src/renderer/viewModels/flowCopy.ts`:

```ts
export function getAnalysisVisualState(step: ProgressStep | null, copy: Copy): AnalysisVisualState {
  const activeStage = getAnalysisStageNumber(step)
  const total = Math.max(step?.total ?? 4, 1)
  const progress = Math.min(Math.max((step?.step ?? 0) / total, 0), 1)
  const segmentTotal = Math.max(step?.subTotal ?? 12, 1)
  const activeSegment = Math.min(Math.max(step?.subCurrent ?? 1, 1), segmentTotal)
  const currentPercent = Math.round(progress * 100)
  const activeBar = Math.min(activeSegment, VISUAL_BAR_HEIGHTS.length)

  return {
    scanPercent: Math.round(progress * 1000) / 10,
    activeStage,
    activeSegment,
    segmentTotal,
    headline: activeStage === 3 ? copy.flow.visualHeadlineFiltering : copy.flow.visualHeadlineAnalyzing,
    detail: copy.flow.visualDetail(activeSegment, segmentTotal, currentPercent),
    bars: VISUAL_BAR_HEIGHTS.map((height, index) => {
      const barIndex = index + 1
      return {
        index: barIndex,
        active: barIndex === activeBar,
        done: barIndex < activeBar,
        height,
      }
    }),
  }
}

export function getAnalysisStageView(step: ProgressStep | null, copy: Copy): AnalysisStageView {
  if (!step) {
    return {
      title: copy.flow.waitingTitle,
      detail: copy.flow.waitingDetail,
      stageLabel: copy.flow.waitingStageLabel,
      progressLabel: copy.flow.progressLabel(0, 4),
      progress: 0,
      subProgress: null,
    }
  }

  const total = Math.max(step.total, 1)
  const stepIndex = getAnalysisStageNumber(step) - 1
  const stage = copy.flow.stages[stepIndex]
  const subProgress = step.subCurrent != null && step.subTotal != null
    ? {
        current: step.subCurrent,
        total: step.subTotal,
        label: copy.flow.groupLabel(step.subCurrent, step.subTotal),
      }
    : null

  return {
    title: stage.title,
    detail: stage.detail,
    stageLabel: stage.stageLabel,
    progressLabel: copy.flow.progressLabel(step.step, total, subProgress?.label),
    progress: Math.min(Math.max(step.step / total, 0), 1),
    subProgress,
  }
}

export function getReviewTaskSummary(
  segments: Pick<Segment, 'included' | 'start' | 'end' | 'startAdjusted' | 'endAdjusted'>[],
  copy: Copy,
) {
  const selected = segments.filter((segment) => segment.included)
  const selectedDuration = selected.reduce((sum, segment) => {
    const start = segment.startAdjusted ?? segment.start
    const end = segment.endAdjusted ?? segment.end
    return sum + Math.max(end - start, 0)
  }, 0)

  return {
    selectedCount: selected.length,
    totalCount: segments.length,
    selectedDurationLabel: formatClipDuration(selectedDuration),
    instruction: copy.flow.reviewInstruction,
  }
}

export function getExportActionCopy(selectedCount: number, exporting: boolean, copy: Copy): string {
  if (exporting) return copy.flow.exporting(selectedCount)
  if (selectedCount === 0) return copy.flow.exportNoSelection
  return copy.flow.exportSelected
}

export function getRallyTitle(
  segment: Pick<Segment, 'index' | 'start' | 'end' | 'score' | 'features'>,
  copy: Copy,
): string {
  const duration = Math.max(segment.end - segment.start, 0)
  const hitCount = segment.features.hit_count ?? 0
  const parts: string[] = []

  if (hitCount >= 14) parts.push(copy.flow.rallyTitle.multiHit)
  if (segment.score > 2.3) parts.push(copy.flow.rallyTitle.highIntensity)
  if (duration <= 8) parts.push(copy.flow.rallyTitle.short)

  if (parts.length > 0) {
    const joined = parts.join(copy.flow.rallyTitle.suffix === '回合' ? '' : ' ')
    return `${joined} ${copy.flow.rallyTitle.suffix} ${formatSegmentNumber(segment.index)}`
  }

  const fallback = segment.score > 1.7 ? copy.flow.rallyTitle.recommended : copy.flow.rallyTitle.regular
  return `${fallback} ${formatSegmentNumber(segment.index)}`
}
```

- [ ] **Step 5: Run flow-copy tests**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: pass for language helpers and flow-copy tests. Source checks may fail later after components are localized; if they fail now because old Chinese source assertions changed, update them in Task 4, not here.

- [ ] **Step 6: Commit task 2**

Run:

```powershell
git add desktop\src\renderer\viewModels\flowCopy.ts desktop\scripts\renderer-flow.test.mjs
git commit -m "feat: localize desktop flow copy"
```

## Task 3: Add LanguageProvider and app-level language switch

**Files:**
- Create: `desktop/src/renderer/i18n/LanguageProvider.tsx`
- Modify: `desktop/src/renderer/i18n/index.ts`
- Modify: `desktop/src/renderer\App.tsx`
- Test: `desktop/scripts/renderer-flow.test.mjs`

- [ ] **Step 1: Write failing provider/source tests**

Add this source check near the existing `appSource` assertions in `desktop/scripts/renderer-flow.test.mjs`:

```js
const providerSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'i18n', 'LanguageProvider.tsx'), 'utf8')
assert.match(providerSource, /createContext/)
assert.match(providerSource, /useLanguage/)
assert.match(providerSource, /useCopy/)
assert.match(providerSource, /navigator\.language/)
assert.match(providerSource, /writeStoredLanguage/)
assert.match(appSource, /<LanguageProvider>/)
assert.match(appSource, /useCopy/)
assert.match(appSource, /useLanguage/)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: fail because `LanguageProvider.tsx` does not exist and `App.tsx` is not wrapped.

- [ ] **Step 3: Create LanguageProvider**

Create `desktop/src/renderer/i18n/LanguageProvider.tsx`:

```tsx
import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import { COPY, type Copy, type Language } from './copy'
import { detectDefaultLanguage, readStoredLanguage, writeStoredLanguage } from './language'

interface LanguageContextValue {
  language: Language
  copy: Copy
  setLanguage: (language: Language) => void
}

const LanguageContext = createContext<LanguageContextValue | null>(null)

function getInitialLanguage(): Language {
  const stored = readStoredLanguage(typeof window !== 'undefined' ? window.localStorage : undefined)
  if (stored) return stored
  const locale = typeof navigator !== 'undefined' ? navigator.language : undefined
  return detectDefaultLanguage(locale)
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(getInitialLanguage)

  const value = useMemo<LanguageContextValue>(() => ({
    language,
    copy: COPY[language],
    setLanguage: (nextLanguage) => {
      setLanguageState(nextLanguage)
      writeStoredLanguage(typeof window !== 'undefined' ? window.localStorage : undefined, nextLanguage)
    },
  }), [language])

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  )
}

function useLanguageContext(): LanguageContextValue {
  const value = useContext(LanguageContext)
  if (!value) {
    throw new Error('LanguageProvider is missing')
  }
  return value
}

export function useLanguage() {
  const { language, setLanguage } = useLanguageContext()
  return { language, setLanguage }
}

export function useCopy(): Copy {
  return useLanguageContext().copy
}
```

- [ ] **Step 4: Export provider hooks**

Update `desktop/src/renderer/i18n/index.ts`:

```ts
export { COPY, LANGUAGE_LABELS } from './copy'
export type { Copy, Language } from './copy'
export {
  LANGUAGE_STORAGE_KEY,
  detectDefaultLanguage,
  parseStoredLanguage,
  readStoredLanguage,
  writeStoredLanguage,
} from './language'
export { LanguageProvider, useCopy, useLanguage } from './LanguageProvider'
```

- [ ] **Step 5: Wrap `App` and localize top-level copy**

In `desktop/src/renderer/App.tsx`, add:

```ts
import { LanguageProvider, useCopy, useLanguage, LANGUAGE_LABELS, type Language } from './i18n'
```

Inside `AppInner`, add:

```ts
  const copy = useCopy()
  const { language, setLanguage } = useLanguage()
  const languageSwitch = <LanguageSwitch language={language} onChange={setLanguage} />
```

Replace top-level user strings with `copy`:

```tsx
setResourceError(`${copy.app.missingResources} ${res.missing.join(', ')}`)
dispatch({ type: 'ANALYSIS_ERROR', message: copy.app.reportMissing })
dispatch({ type: 'ANALYSIS_ERROR', message: event.message ?? copy.app.unknownError })
setExportResult({ status: 'error', message: `${copy.app.exportFailedPrefix}${result.error}` })
setExportResult({ status: 'complete', message: copy.app.exportComplete, outputPath: result.outputPath })
dispatch({ type: 'ANALYSIS_ERROR', message: copy.app.cancelled })
return <WelcomeScreen onVideoSelected={handleVideoSelected} languageSwitch={languageSwitch} />
<h2 ...>{copy.app.resourceErrorTitle}</h2>
<span ...>{copy.common.appName} · {copy.app.reviewTitle}</span>
<button ...>{copy.app.returnWelcome}</button>
<button ...>{copy.app.rerunAnalysis}</button>
```

Wrap exported app:

```tsx
export default function App() {
  return (
    <LanguageProvider>
      <AppProvider>
        <AppInner />
      </AppProvider>
    </LanguageProvider>
  )
}
```

Add this component before `topBtnStyle`:

```tsx
function LanguageSwitch({ language, onChange }: { language: Language; onChange: (language: Language) => void }) {
  return (
    <div style={{ display: 'inline-flex', gap: 4, WebkitAppRegion: 'no-drag' } as React.CSSProperties}>
      {(['en', 'zh'] as Language[]).map((item) => (
        <button
          key={item}
          onClick={() => onChange(item)}
          style={{
            ...topBtnStyle,
            background: language === item ? 'var(--color-green)' : 'var(--color-surface)',
            color: language === item ? '#fff' : 'var(--color-green-dark)',
          }}
        >
          {LANGUAGE_LABELS[item]}
        </button>
      ))}
    </div>
  )
}
```

Pass `languageSwitch={languageSwitch}` into `AnalysisScreen`.

- [ ] **Step 6: Run provider/source tests**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: provider/source tests pass. Type errors from components that do not accept `languageSwitch` yet are handled in Task 4.

- [ ] **Step 7: Commit task 3**

Run:

```powershell
git add desktop\src\renderer\i18n\LanguageProvider.tsx desktop\src\renderer\i18n\index.ts desktop\src\renderer\App.tsx desktop\scripts\renderer-flow.test.mjs
git commit -m "feat: add desktop language provider"
```

## Task 4: Localize renderer components

**Files:**
- Modify: `desktop/src/renderer/components/WelcomeScreen.tsx`
- Modify: `desktop/src/renderer/components/AnalysisScreen.tsx`
- Modify: `desktop/src/renderer/components/AnalysisProgressPanel.tsx`
- Modify: `desktop/src/renderer/components/MatchMap.tsx`
- Modify: `desktop/src/renderer/components/RallyQueue.tsx`
- Modify: `desktop/scripts/renderer-flow.test.mjs`
- Test: `desktop/scripts/renderer-flow.test.mjs`

- [ ] **Step 1: Write failing component source checks**

Replace the existing Chinese source assertions in `desktop/scripts/renderer-flow.test.mjs` with checks that components use copy hooks and no longer hard-code core Chinese strings:

```js
const welcomeSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'components', 'WelcomeScreen.tsx'), 'utf8')
assert.match(welcomeSource, /useCopy/)
assert.match(welcomeSource, /languageSwitch/)
assert.doesNotMatch(welcomeSource, /导入新视频|打开之前的视频|或把视频文件拖到这里/)

assert.match(analysisPanelSource, /useCopy/)
assert.doesNotMatch(analysisPanelSource, /取消处理|筛选进度|处理失败/)

assert.match(analysisScreenSource, /useCopy/)
assert.match(analysisScreenSource, /languageSwitch/)
assert.doesNotMatch(analysisScreenSource, /分析遇到问题|正在分析视频/)

assert.match(matchMapSource, /useCopy/)
assert.doesNotMatch(matchMapSource, /整场比赛地图|只看建议保留|显示全部回合/)

const rallyQueueSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'components', 'RallyQueue.tsx'), 'utf8')
assert.match(rallyQueueSource, /useCopy/)
assert.doesNotMatch(rallyQueueSource, /回合队列|全选|推荐|清空|取消导出|重置/)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: fail because components still hard-code Chinese strings.

- [ ] **Step 3: Localize WelcomeScreen**

In `desktop/src/renderer/components/WelcomeScreen.tsx`, add:

```ts
import { useCopy } from '../i18n'
```

Change props:

```ts
interface Props {
  onVideoSelected: (path: string) => void
  languageSwitch: React.ReactNode
}
```

Inside the component:

```ts
export default function WelcomeScreen({ onVideoSelected, languageSwitch }: Props) {
  const copy = useCopy()
```

Replace user-visible text:

```tsx
{copy.welcome.eyebrow}
{copy.welcome.description}
v{appVersion || '0.0.0'} — {copy.common.desktop}
{languageSwitch}
{copy.welcome.startLabel}
{copy.welcome.importTitle}
{copy.welcome.importDetail}
<p style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>{copy.welcome.dropHint}</p>
{copy.welcome.recentTitle}
{[[ 'Ctrl+O', copy.welcome.shortcutImport ], [ 'Ctrl+Q', copy.welcome.shortcutQuit ]].map(([key, label]) => (
```

Place `{languageSwitch}` in the action panel near the top of the inner content, before the start label:

```tsx
<div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 24 }}>
  {languageSwitch}
</div>
```

- [ ] **Step 4: Localize AnalysisScreen and AnalysisProgressPanel**

In `desktop/src/renderer/components/AnalysisScreen.tsx`, add:

```ts
import { useCopy } from '../i18n'
```

Change props:

```ts
  languageSwitch: React.ReactNode
```

Inside the component:

```ts
  const copy = useCopy()
```

Replace header:

```tsx
<div>{copy.common.appName} · {errorMessage ? copy.analysisScreen.problemTitle : copy.analysisScreen.runningTitle}</div>
<div style={{ display: 'flex', alignItems: 'center', gap: 10, WebkitAppRegion: 'no-drag' } as CSSProperties}>
  {languageSwitch}
  <span>v0.1.6</span>
</div>
```

In `desktop/src/renderer/components/AnalysisProgressPanel.tsx`, add:

```ts
import { useCopy } from '../i18n'
```

Inside the component:

```ts
  const copy = useCopy()
  const view = getAnalysisStageView(step, copy)
  const activeStage = getAnalysisStageNumber(step)
  const stages = copy.analysisPanel.stages
```

Replace all strings:

```tsx
{copy.analysisPanel.failedEyebrow}
{copy.analysisPanel.failedTitle}
{copy.analysisPanel.retry}
{copy.analysisPanel.returnWelcome}
{copy.analysisPanel.autoStart}
{copy.analysisPanel.headline.split('\\n').map((line, index) => (
  <span key={line}>{index > 0 && <br />}{line}</span>
))}
{copy.analysisPanel.intro}
const status = done ? copy.analysisPanel.statusDone : current ? copy.analysisPanel.statusCurrent : copy.analysisPanel.statusNext
{copy.analysisPanel.subProgressTitle}
{copy.analysisPanel.cancel}
```

- [ ] **Step 5: Localize MatchMap**

In `desktop/src/renderer/components/MatchMap.tsx`, add:

```ts
import { useCopy } from '../i18n'
```

Inside the component:

```ts
  const copy = useCopy()
```

Replace user-visible strings:

```tsx
<h2 style={mapTitleStyle}>{copy.matchMap.title}</h2>
<p style={mapSubtitleStyle}>{copy.matchMap.subtitle}</p>
<span ...>{copy.matchMap.highlight}</span>
<span ...>{copy.matchMap.keep}</span>
<span ...>{copy.matchMap.discarded}</span>
title={`#${String(originalIndex + 1).padStart(2, '0')} · ${range.label} · ${copy.matchMap.intensity} ${segment.score.toFixed(2)}`}
{recommendedOnly ? copy.matchMap.showAll : copy.matchMap.recommendedOnly}
```

- [ ] **Step 6: Localize RallyQueue**

In `desktop/src/renderer/components/RallyQueue.tsx`, add:

```ts
import { useCopy, type Copy } from '../i18n'
```

Change `toneLabel`:

```ts
function toneLabel(segment: Segment, copy: Copy): string {
  const tone = getSegmentTone(segment)
  if (tone === 'highlight') return copy.rallyQueue.toneHighlight
  if (tone === 'keep') return copy.rallyQueue.toneKeep
  return copy.rallyQueue.toneDiscarded
}
```

Inside `RallyQueue`:

```ts
  const copy = useCopy()
  const summary = getReviewTaskSummary(segments, copy)
```

Pass `copy` into child components:

```tsx
<RallyCard ... copy={copy} />
<TrimEditor ... copy={copy} />
```

Replace queue/export strings:

```tsx
<h2 style={titleStyle}>{copy.rallyQueue.title}</h2>
{copy.rallyQueue.exportCount(summary.selectedCount, summary.totalCount)}
{copy.rallyQueue.includeAll}
{copy.rallyQueue.restoreRecommended}
{copy.rallyQueue.excludeAll}
{copy.rallyQueue.empty}
{copy.rallyQueue.exportSummary(summary.selectedCount)}
{copy.rallyQueue.exportDuration(summary.selectedDurationLabel)}
{copy.rallyQueue.openExport}
{copy.rallyQueue.cancelExport}
{getExportActionCopy(summary.selectedCount, false, copy)} ↗
```

Update `RallyCard` props:

```ts
  copy: Copy
```

Use localized card copy:

```tsx
{getRallyTitle(segment, copy)}
{isEdited && <span style={editedDotStyle} title={copy.common.edited} />}
{toneLabel(segment, copy)} · {copy.rallyQueue.hits(segment.features.hit_count ?? copy.common.hitCountUnknown)} · {copy.rallyQueue.intensity(segment.score.toFixed(2))}
```

Update `TrimEditor` props:

```ts
  copy: Copy
```

Use localized trim copy:

```tsx
<span>{copy.rallyQueue.start} <b>{formatTimePrecise(effectiveStart)}</b></span>
<span>{copy.rallyQueue.end} <b>{formatTimePrecise(effectiveEnd)}</b></span>
<span>{copy.rallyQueue.trimHelp(formatTimePrecise(segment.start), formatTimePrecise(segment.end))}</span>
{copy.rallyQueue.reset}
```

- [ ] **Step 7: Run renderer flow tests**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: pass. If a source assertion still finds a Chinese literal, replace that literal with the matching copy key.

- [ ] **Step 8: Commit task 4**

Run:

```powershell
git add desktop\src\renderer\components\WelcomeScreen.tsx desktop\src\renderer\components\AnalysisScreen.tsx desktop\src\renderer\components\AnalysisProgressPanel.tsx desktop\src\renderer\components\MatchMap.tsx desktop\src\renderer\components\RallyQueue.tsx desktop\scripts\renderer-flow.test.mjs
git commit -m "feat: localize desktop renderer UI"
```

## Task 5: Build verification and final cleanup

**Files:**
- Modify if needed: files touched in Tasks 1-4
- Test: `desktop/scripts/renderer-flow.test.mjs`

- [ ] **Step 1: Run renderer tests**

Run:

```powershell
Set-Location .\desktop
npm run test:renderer-flow
```

Expected: pass with no assertion failures.

- [ ] **Step 2: Run production build**

Run:

```powershell
Set-Location .\desktop
npm run build
```

Expected: TypeScript and Vite build complete successfully. Any TypeScript error about missing `copy` arguments means a call site still needs to pass `copy` from `useCopy()`.

- [ ] **Step 3: Search for remaining hard-coded Chinese in renderer UI**

Run:

```powershell
rg "[\p{Han}]" .\desktop\src\renderer -g "*.ts" -g "*.tsx"
```

Expected: remaining Chinese text is limited to `desktop\src\renderer\i18n\copy.ts`. If other renderer files appear, move those user-visible strings into `COPY.zh` and use the corresponding copy key.

- [ ] **Step 4: Verify git status**

Run:

```powershell
git --no-pager status --short --branch
```

Expected: only intentional localization files are modified.

- [ ] **Step 5: Commit final fixes if Step 2 or Step 3 required edits**

Run this only if Step 2 or Step 3 required follow-up edits:

```powershell
git add desktop\src\renderer desktop\scripts\renderer-flow.test.mjs
git commit -m "fix: complete desktop localization coverage"
```

## Self-review notes

- Spec coverage: Tasks cover typed dictionaries, language default detection, persisted switching, localized welcome/analysis/review/map/export UI, dynamic flow copy, tests, build, and Chinese-literal search.
- Scope: Plan stays within desktop app UI. It does not split installers, docs, screenshots, or public website copy.
- Type consistency: `Copy` and `Language` are introduced in Task 1, consumed by `flowCopy.ts` in Task 2, exposed through hooks in Task 3, and used by components in Task 4.
