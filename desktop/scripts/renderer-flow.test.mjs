import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import ts from 'typescript'
import vm from 'node:vm'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
function loadTsModule(relativePath) {
  const sourcePath = path.join(root, relativePath)
  const source = fs.readFileSync(sourcePath, 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      strict: true,
    },
  }).outputText

  const module = { exports: {} }
  vm.runInNewContext(compiled, { module, exports: module.exports }, { filename: sourcePath })
  return module.exports
}

const {
  getAnalysisStageView,
  getAnalysisStageNumber,
  getReviewTaskSummary,
  getExportActionCopy,
  formatClipDuration,
  getRallyTitle,
  getSegmentTone,
  getAdjustedTimeRange,
} = loadTsModule(path.join('src', 'renderer', 'viewModels', 'flowCopy.ts'))

const {
  hasReusableAnalysisReport,
} = loadTsModule(path.join('src', 'renderer', 'analysisFlow.ts'))

const plain = (value) => JSON.parse(JSON.stringify(value))

assert.deepEqual(plain(getAnalysisStageView(null)), {
  title: '准备开始处理',
  detail: '导入视频后会自动开始分析。',
  stageLabel: '等待视频',
  progressLabel: '0 / 4',
  progress: 0,
  subProgress: null,
})

assert.deepEqual(plain(getAnalysisStageView({ step: 3, total: 4, label: 'vision ranking', subCurrent: 1, subTotal: 10 })), {
  title: '正在筛选精彩瞬间',
  detail: '正在逐组确认可分享的高光片段，请保持窗口打开。',
  stageLabel: '筛选中',
  progressLabel: '3 / 4 · 1 / 10 组',
  progress: 0.75,
  subProgress: { current: 1, total: 10, label: '1 / 10 组' },
})

assert.deepEqual(plain(getAnalysisStageView({ step: 3.5, total: 4, label: 'Analyzing player motion', subCurrent: 1, subTotal: 32 })), {
  title: '正在筛选精彩瞬间',
  detail: '正在逐组确认可分享的高光片段，请保持窗口打开。',
  stageLabel: '筛选中',
  progressLabel: '3.5 / 4 · 1 / 32 组',
  progress: 0.875,
  subProgress: { current: 1, total: 32, label: '1 / 32 组' },
})
assert.equal(getAnalysisStageNumber({ step: 3.5, total: 4, label: 'Analyzing player motion', subCurrent: 1, subTotal: 32 }), 3)
assert.equal(getAnalysisStageNumber({ step: 4, total: 4, label: 'Ranking points' }), 4)

assert.deepEqual(plain(getReviewTaskSummary([
  { start: 10, end: 20, score: 2.4, included: true, features: {}, index: 0 },
  { start: 40, end: 52.5, score: 1.4, included: false, features: {}, index: 1 },
  { start: 70, end: 95, score: 2.1, included: true, startAdjusted: 72, endAdjusted: 93, features: {}, index: 2 },
])), {
  selectedCount: 2,
  totalCount: 3,
  selectedDurationLabel: '0:31',
  instruction: '挑选视频片段，确认保留后导出精彩合集。',
})

assert.equal(getExportActionCopy(0, false), '选择回合后导出')
assert.equal(getExportActionCopy(3, false), '导出已选择的回合')
assert.equal(getExportActionCopy(3, true), '正在导出 3 个回合')
assert.equal(formatClipDuration(61.8), '1:01')
const highMultiHitSegment = {
  index: 7,
  start: 1463,
  end: 1484,
  score: 2.6,
  included: true,
  features: { hit_count: 18 },
}
assert.equal(getRallyTitle(highMultiHitSegment), '多拍高强度回合 #08')
assert.equal(getSegmentTone(highMultiHitSegment), 'highlight')
assert.deepEqual(plain(getAdjustedTimeRange({
  index: 2,
  start: 70,
  end: 95,
  score: 2.1,
  included: true,
  startAdjusted: 72.2,
  endAdjusted: 93.7,
  features: {},
})), {
  start: 72.2,
  end: 93.7,
  duration: 21.5,
  label: '1:12 - 1:33',
})

assert.equal(getRallyTitle({
  index: 3,
  start: 20,
  end: 25,
  score: 1.8,
  included: true,
  features: { hit_count: 5 },
}), '短回合 #04')
assert.equal(getSegmentTone({
  index: 3,
  start: 20,
  end: 25,
  score: 1.8,
  included: true,
  features: { hit_count: 5 },
}), 'keep')

assert.equal(getRallyTitle({
  index: 4,
  start: 40,
  end: 55,
  score: 1.1,
  included: false,
  features: {},
}), '普通回合 #05')
assert.equal(getSegmentTone({
  index: 4,
  start: 40,
  end: 55,
  score: 1.1,
  included: false,
  features: {},
}), 'discarded')
assert.equal(hasReusableAnalysisReport(null), false)
assert.equal(hasReusableAnalysisReport([]), false)
assert.equal(hasReusableAnalysisReport([{ index: 1, start: 10, end: 20, score: 2, features: {} }]), true)

const analysisCourtSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'components', 'AnalysisCourtVisual.tsx'), 'utf8')
assert.match(analysisCourtSource, /export default function AnalysisCourtVisual/)
assert.doesNotMatch(analysisCourtSource, /ProgressStep/)
assert.doesNotMatch(analysisCourtSource, /getAnalysisVisualState/)
assert.match(analysisCourtSource, /@keyframes breakpoint-scan/)
assert.match(analysisCourtSource, /Array\.from\(\{ length: 34 \}/)
assert.match(analysisCourtSource, /bottom: 74/)

const analysisPanelSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'components', 'AnalysisProgressPanel.tsx'), 'utf8')
assert.match(analysisPanelSource, /export default function AnalysisProgressPanel/)
assert.match(analysisPanelSource, /getAnalysisStageView/)
assert.match(analysisPanelSource, /取消处理/)
assert.match(analysisPanelSource, /activeStage === 3/)
assert.match(analysisPanelSource, /view\.subProgress/)
assert.match(analysisPanelSource, /筛选进度/)

const analysisScreenSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'components', 'AnalysisScreen.tsx'), 'utf8')
assert.match(analysisScreenSource, /AnalysisCourtVisual/)
assert.match(analysisScreenSource, /AnalysisProgressPanel/)

const appSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'App.tsx'), 'utf8')
assert.match(appSource, /<AnalysisScreen/)
assert.doesNotMatch(appSource, /<ProgressOverlay/)

const appStateSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'state', 'AppState.tsx'), 'utf8')
assert.match(appStateSource, /RESTORE_RECOMMENDED/)
assert.match(appStateSource, /case 'RESTORE_RECOMMENDED'/)
assert.match(appStateSource, /included: s\.score > INCLUDE_THRESHOLD/)
assert.doesNotMatch(appStateSource, /case 'RESTORE_RECOMMENDED':[\s\S]*startAdjusted: undefined/)
