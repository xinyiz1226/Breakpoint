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
      jsx: ts.JsxEmit.ReactJSX,
      strict: true,
    },
  }).outputText

  const module = { exports: {} }
  const require = (specifier) => {
    if (specifier === 'react') {
      return {
        createContext: () => ({}),
        useContext: () => null,
        useReducer: () => [null, () => {}],
      }
    }
    if (specifier === 'react/jsx-runtime') {
      return { jsx: () => ({}), jsxs: () => ({}), Fragment: Symbol('Fragment') }
    }
    throw new Error(`Unexpected test module import: ${specifier}`)
  }
  vm.runInNewContext(compiled, { module, exports: module.exports, require }, { filename: sourcePath })
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
  getAnalysisVisualState,
} = loadTsModule(path.join('src', 'renderer', 'viewModels', 'flowCopy.ts'))

const {
  hasReusableAnalysisReport,
} = loadTsModule(path.join('src', 'renderer', 'analysisFlow.ts'))

const {
  createVideoRecords,
  createRalliesForVideo,
  getSortedRallies,
  getRalliesForVideo,
  getExportClips,
  getVideoDisplayName,
} = loadTsModule(path.join('src', 'renderer', 'batchFlow.ts'))

const {
  MIN_SEGMENT_DURATION,
  reducer,
} = loadTsModule(path.join('src', 'renderer', 'state', 'AppState.tsx'))

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

const plain = (value) => JSON.parse(JSON.stringify(value))

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
const completedBatchVideos = batchVideos.map((video) => ({ ...video, status: 'done' }))
assert.deepEqual(firstVideoRallies.map((r) => r.id), ['video-1-rally-2', 'video-1-rally-1'])
assert.equal(firstVideoRallies[0].videoId, 'video-1')
assert.equal(firstVideoRallies[0].sourceIndex, 2)
assert.equal(firstVideoRallies[0].included, true)
assert.equal(firstVideoRallies[1].included, true)

const sortedRallies = getSortedRallies([
  secondVideoRallies[0],
  firstVideoRallies[0],
  firstVideoRallies[1],
], completedBatchVideos)
assert.deepEqual(sortedRallies.map((r) => r.id), ['video-1-rally-1', 'video-1-rally-2', 'video-2-rally-0'])
assert.deepEqual(getRalliesForVideo(sortedRallies, 'video-1').map((r) => r.id), ['video-1-rally-1', 'video-1-rally-2'])
assert.deepEqual(plain(getExportClips(sortedRallies, completedBatchVideos)), [
  { videoPath: 'D:\\match\\first.mp4', start: 10, end: 22 },
  { videoPath: 'D:\\match\\first.mp4', start: 30, end: 38 },
  { videoPath: 'D:\\match\\second.mov', start: 5, end: 12 },
])
assert.deepEqual(plain(getExportClips([
  { ...firstVideoRallies[1], startAdjusted: 11, endAdjusted: 20 },
  { ...secondVideoRallies[0], included: false },
], completedBatchVideos)), [
  { videoPath: 'D:\\match\\first.mp4', start: 11, end: 20 },
])
assert.deepEqual(plain(getExportClips(sortedRallies, [
  { ...completedBatchVideos[0], status: 'running' },
  { ...completedBatchVideos[1], status: 'error' },
])), [])

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
assert.equal(COPY.en.welcome.importTitle, 'Import videos')
assert.equal(COPY.zh.welcome.importTitle, '导入多个视频')
assert.equal(COPY.en.batch.videoProgress(2, 5), 'Video 2 / 5')
assert.equal(COPY.zh.batch.videoProgress(2, 5), '第 2 / 5 个视频')
assert.equal(COPY.en.batch.retryVideo, 'Retry')
assert.equal(COPY.zh.batch.retryVideo, '重试')
assert.equal(COPY.en.rallyQueue.sourceLabel('Video 1'), 'Source: Video 1')
assert.equal(COPY.zh.rallyQueue.sourceLabel('Video 1'), '来源：Video 1')
assert.equal(COPY.zh.app.cancelled, '已取消')
assert.equal(COPY.zh.app.reportMissing, '找不到分析报告文件')
assert.equal(COPY.zh.app.unknownError, '未知错误')
assert.equal(COPY.en.flow.rallyTitle.joinPartsWithSpace, true)
assert.equal(COPY.zh.flow.rallyTitle.joinPartsWithSpace, false)
assert.deepEqual(COPY.en.analysisPanel.headline.split('\n'), ['AI is analyzing', 'the full video'])
assert.deepEqual(COPY.zh.analysisPanel.headline.split('\n'), ['正在用 AI', '分析整场视频'])
assert.doesNotMatch(COPY.en.analysisPanel.headline.split('\n')[0], /\\$/)
assert.doesNotMatch(COPY.zh.analysisPanel.headline.split('\n')[0], /\\$/)
assert.doesNotMatch(COPY.en.analysisPanel.headline, /\\/)
assert.doesNotMatch(COPY.zh.analysisPanel.headline, /\\/)

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

assert.deepEqual(plain(getAnalysisStageView({ step: 3, total: 4, label: 'vision ranking', subCurrent: 1, subTotal: 10 }, COPY.zh)), {
  title: '正在筛选精彩瞬间',
  detail: '正在逐组确认可分享的高光片段，请保持窗口打开。',
  stageLabel: '筛选中',
  progressLabel: '3 / 4 · 1 / 10 组',
  progress: 0.75,
  subProgress: { current: 1, total: 10, label: '1 / 10 组' },
})

assert.deepEqual(plain(getAnalysisStageView({ step: 3.5, total: 4, label: 'Analyzing player motion', subCurrent: 1, subTotal: 32 }, COPY.zh)), {
  title: '正在筛选精彩瞬间',
  detail: '正在逐组确认可分享的高光片段，请保持窗口打开。',
  stageLabel: '筛选中',
  progressLabel: '3.5 / 4 · 1 / 32 组',
  progress: 0.875,
  subProgress: { current: 1, total: 32, label: '1 / 32 组' },
})
assert.equal(getAnalysisStageNumber({ step: 3.5, total: 4, label: 'Analyzing player motion', subCurrent: 1, subTotal: 32 }), 3)
assert.equal(getAnalysisStageNumber({ step: 4, total: 4, label: 'Ranking points' }), 4)

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
assert.equal(formatClipDuration(61.8), '1:01')
const highMultiHitSegment = {
  sourceIndex: 7,
  start: 1463,
  end: 1484,
  score: 2.6,
  included: true,
  features: { hit_count: 18 },
}
assert.equal(getRallyTitle(highMultiHitSegment, COPY.en), 'Long High-intensity rally #08')
assert.equal(getRallyTitle(highMultiHitSegment, COPY.zh), '多拍高强度回合 #08')
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
  sourceIndex: 3,
  start: 20,
  end: 25,
  score: 1.8,
  included: true,
  features: { hit_count: 5 },
}, COPY.en), 'Short rally #04')
assert.equal(getSegmentTone({
  index: 3,
  start: 20,
  end: 25,
  score: 1.8,
  included: true,
  features: { hit_count: 5 },
}), 'keep')

assert.equal(getRallyTitle({
  sourceIndex: 4,
  start: 40,
  end: 55,
  score: 1.1,
  included: false,
  features: {},
}, COPY.en), 'Regular rally #05')
assert.equal(getAnalysisVisualState({ step: 3, total: 4, label: 'vision ranking', subCurrent: 2, subTotal: 8 }, COPY.en).headline, 'Filtering highlight clips')
assert.equal(getAnalysisVisualState({ step: 1, total: 4, label: 'load' }, COPY.zh).headline, '正在分析视频')
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
assert.match(analysisPanelSource, /useCopy/)
assert.match(analysisPanelSource, /activeStage === 3/)
assert.match(analysisPanelSource, /view\.subProgress/)
assert.match(analysisPanelSource, /batchLabel/)
assert.match(analysisPanelSource, /<span key=\{index\}>/)
assert.doesNotMatch(analysisPanelSource, /<span key=\{line\}>/)
assert.doesNotMatch(analysisPanelSource, /取消处理|筛选进度|处理失败/)

const analysisScreenSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'components', 'AnalysisScreen.tsx'), 'utf8')
assert.match(analysisScreenSource, /AnalysisCourtVisual/)
assert.match(analysisScreenSource, /AnalysisProgressPanel/)
assert.match(analysisScreenSource, /languageSwitch/)
assert.match(analysisScreenSource, /useCopy/)
assert.match(analysisScreenSource, /const copy = useCopy\(\)/)
assert.match(analysisScreenSource, /copy\.analysisScreen\.problemTitle/)
assert.match(analysisScreenSource, /copy\.analysisScreen\.runningTitle/)
assert.match(analysisScreenSource, /batchLabel\?: string/)
assert.match(analysisScreenSource, /batchLabel=\{batchLabel\}/)
assert.doesNotMatch(analysisScreenSource, /分析遇到问题/)
assert.doesNotMatch(analysisScreenSource, /正在分析视频/)

const batchVideoListSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'components', 'BatchVideoList.tsx'), 'utf8')
assert.match(batchVideoListSource, /export default function BatchVideoList/)
assert.match(batchVideoListSource, /import type \{ CSSProperties \} from 'react'/)
assert.match(batchVideoListSource, /import \{ useCopy, type Copy \} from '\.\.\/i18n'/)
assert.match(batchVideoListSource, /videos: VideoRecord\[\]/)
assert.match(batchVideoListSource, /activeVideoId: string \| null/)
assert.match(batchVideoListSource, /onSelect: \(videoId: string\) => void/)
assert.match(batchVideoListSource, /onRetry: \(videoId: string\) => void/)
assert.match(batchVideoListSource, /const copy = useCopy\(\)/)
assert.match(batchVideoListSource, /copy\.batch\.title/)
assert.match(batchVideoListSource, /copy\.batch\.retryVideo/)
assert.match(batchVideoListSource, /copy\.batch\.successfulVideos/)
assert.match(batchVideoListSource, /video\.displayName/)
assert.match(batchVideoListSource, /video\.errorMessage/)
assert.match(batchVideoListSource, /copy\.batch\.pending/)
assert.match(batchVideoListSource, /copy\.batch\.running/)
assert.match(batchVideoListSource, /copy\.batch\.done/)
assert.match(batchVideoListSource, /copy\.batch\.failed/)
assert.match(batchVideoListSource, /<button\s+type="button"[\s\S]*onClick=\{\(\) => onSelect\(video\.id\)\}/)
assert.match(batchVideoListSource, /<button\s+type="button"[\s\S]*onClick=\{\(event\) => \{[\s\S]*event\.stopPropagation\(\)[\s\S]*onRetry\(video\.id\)/)
assert.doesNotMatch(batchVideoListSource, /role="button"/)
assert.match(batchVideoListSource, /\{statusText\} · \{video\.rallyCount\}/)

const welcomeSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'components', 'WelcomeScreen.tsx'), 'utf8')
assert.match(welcomeSource, /useCopy/)
assert.match(welcomeSource, /languageSwitch/)
assert.doesNotMatch(welcomeSource, /导入新视频|打开之前的视频|或把视频文件拖到这里/)
assert.match(welcomeSource, /onVideosSelected: \(paths: string\[\]\) => void/)
assert.match(welcomeSource, /const paths = await window\.api\.openFileDialog\(\)/)
assert.match(welcomeSource, /if \(paths && paths\.length > 0\) onVideosSelected\(paths\)/)
assert.match(welcomeSource, /Array\.from\(e\.dataTransfer\.files\)/)
assert.match(welcomeSource, /onVideosSelected\(paths\)/)
assert.doesNotMatch(welcomeSource, /onVideoSelected/)

const matchMapSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'components', 'MatchMap.tsx'), 'utf8')
assert.match(matchMapSource, /const safeDuration = Math\.max\(videoDuration, 1\)/)
assert.match(matchMapSource, /key=\{segment\.id\}/)
assert.doesNotMatch(matchMapSource, /\/ videoDuration\) \* 100/)
assert.match(matchMapSource, /useCopy/)
assert.match(matchMapSource, /getRalliesForVideo/)
assert.match(matchMapSource, /activeVideoId/)
assert.match(matchMapSource, /selectedRallyId/)
assert.match(matchMapSource, /dispatch\(\{ type: 'SELECT_RALLY', id: segment\.id \}\)/)
assert.match(matchMapSource, /dispatch\(\{ type: 'SET_ACTIVE_VIDEO', id: segment\.videoId \}\)/)
assert.doesNotMatch(matchMapSource, /整场比赛地图|只看建议保留|显示全部回合/)

const rallyQueueSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'components', 'RallyQueue.tsx'), 'utf8')
assert.match(rallyQueueSource, /useCopy/)
assert.match(rallyQueueSource, /useMemo\(\(\) => getSortedRallies\(rallies, videos\), \[rallies, videos\]\)/)
assert.match(rallyQueueSource, /videosById: Map<string, VideoRecord>/)
assert.match(rallyQueueSource, /copy\.rallyQueue\.sourceLabel/)
assert.match(rallyQueueSource, /dispatch\(\{ type: 'SELECT_RALLY', id: segment\.id \}\)/)
assert.match(rallyQueueSource, /dispatch\(\{ type: 'SET_ACTIVE_VIDEO', id: segment\.videoId \}\)/)
assert.match(rallyQueueSource, /dispatch\(\{ type: 'TOGGLE_INCLUDE', id: segment\.id \}\)/)
assert.match(rallyQueueSource, /dispatch\(\{ type: 'ADJUST_RALLY', id: segment\.id/)
assert.doesNotMatch(rallyQueueSource, /回合队列|全选|推荐|清空|取消导出|重置/)

const videoPlayerSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'components', 'VideoPlayer.tsx'), 'utf8')
assert.match(videoPlayerSource, /useEffect\(\(\) => \{\s*setPlaying\(false\)\s*setCurrentTime\(0\)\s*setDuration\(0\)\s*pauseFiredRef\.current = false\s*\}, \[videoPath\]\)/)
assert.match(videoPlayerSource, /const playerRootStyle: React\.CSSProperties/)
assert.match(videoPlayerSource, /const videoViewportStyle: React\.CSSProperties/)
assert.match(videoPlayerSource, /const videoElementStyle: React\.CSSProperties/)
assert.match(videoPlayerSource, /const controlBarStyle: React\.CSSProperties/)
const playerRootStyleBlock = videoPlayerSource.match(/const playerRootStyle: React\.CSSProperties = \{([\s\S]*?)\n\}/)?.[1] ?? ''
const videoViewportStyleBlock = videoPlayerSource.match(/const videoViewportStyle: React\.CSSProperties = \{([\s\S]*?)\n\}/)?.[1] ?? ''
const videoElementStyleBlock = videoPlayerSource.match(/const videoElementStyle: React\.CSSProperties = \{([\s\S]*?)\n\}/)?.[1] ?? ''
const controlBarStyleBlock = videoPlayerSource.match(/const controlBarStyle: React\.CSSProperties = \{([\s\S]*?)\n\}/)?.[1] ?? ''
assert.match(playerRootStyleBlock, /height: '100%'/)
assert.match(videoViewportStyleBlock, /flex: '1 1 0'/)
assert.match(videoElementStyleBlock, /maxHeight: '100%'/)
assert.match(videoElementStyleBlock, /objectFit: 'contain'/)
assert.match(controlBarStyleBlock, /flexShrink: 0/)

const appSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'App.tsx'), 'utf8')
const mainSource = fs.readFileSync(path.join(root, 'src', 'main', 'main.ts'), 'utf8')
const pythonBridgeSource = fs.readFileSync(path.join(root, 'src', 'main', 'pythonBridge.ts'), 'utf8')
const ffmpegSource = fs.readFileSync(path.join(root, 'src', 'main', 'ffmpegBridge.ts'), 'utf8')
const preloadSource = fs.readFileSync(path.join(root, 'src', 'main', 'preload.ts'), 'utf8')
const typesSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'types.d.ts'), 'utf8')
const providerSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'i18n', 'LanguageProvider.tsx'), 'utf8')
const appExecutableSource = appSource.replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '')
const pythonBridgeExecutableSource = pythonBridgeSource.replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '')
const ffmpegExecutableSource = ffmpegSource.replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '')
const cancelAnalysisHandlerSource = pythonBridgeExecutableSource.match(/ipcMain\.handle\('cancel-analysis'[\s\S]*?\n\s*\}\)\s*\n\s*ipcMain\.handle\('load-report'/)?.[0] ?? ''
const analyzeVideoSource = appExecutableSource.match(/const analyzeVideo = useCallback\(async \(video: VideoRecord, runId: number, options\?: \{ reuseReport\?: boolean \}\) => \{([\s\S]*?)\n\s*\}, \[copy\.app\.reportMissing/)?.[1] ?? ''
const handleVideosSelectedSource = appExecutableSource.match(/const handleVideosSelected = useCallback\([\s\S]*?\n\s*\}, \[dispatch, startBatchAnalysis\]\)/)?.[0] ?? ''
const handleRetryVideoSource = appExecutableSource.match(/const handleRetryVideo = useCallback\(async \(videoId: string\) => \{([\s\S]*?)\n\s*\}, \[/)?.[1] ?? ''
assert.match(mainSource, /properties: \['openFile', 'multiSelections'\]/)
assert.match(mainSource, /return filePaths/)
assert.match(ffmpegSource, /interface ExportClip/)
assert.match(ffmpegSource, /videoPath: string/)
assert.match(ffmpegExecutableSource, /ipcMain\.handle\('export-highlights', async \(event, clips: ExportClip\[\]\) =>/)
assert.match(ffmpegExecutableSource, /if \(!firstClip\) return \{ error: 'No clips selected for export' \}/)
assert.match(ffmpegExecutableSource, /path\.dirname\(firstClip\.videoPath\)/)
assert.match(ffmpegExecutableSource, /path\.basename\(firstClip\.videoPath, path\.extname\(firstClip\.videoPath\)\)/)
assert.match(ffmpegExecutableSource, /const sorted = \[\.\.\.clips\]/)
assert.match(ffmpegExecutableSource, /if \(sorted\.length === 0\) return \{ error: 'No valid clips selected for export' \}/)
assert.match(ffmpegExecutableSource, /inputs\.push\('-ss', String\(clip\.start\), '-t', String\(clip\.end - clip\.start\), '-i', clip\.videoPath\)/)
assert.match(ffmpegExecutableSource, /scale=1280:720:force_original_aspect_ratio=decrease/)
assert.match(ffmpegExecutableSource, /pad=1280:720:\(ow-iw\)\/2:\(oh-ih\)\/2/)
assert.match(ffmpegExecutableSource, /setsar=1/)
assert.match(ffmpegExecutableSource, /fps=30/)
assert.match(ffmpegExecutableSource, /format=yuv420p/)
assert.match(ffmpegExecutableSource, /aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo/)
assert.match(ffmpegExecutableSource, /\[v\$\{i\}\]\[a\$\{i\}\]/)
assert.match(preloadSource, /openFileDialog: \(\) => ipcRenderer\.invoke\('open-file-dialog'\) as Promise<string\[] \| null>/)
assert.doesNotMatch(preloadSource, /\/\/\s*exportHighlights/)
assert.doesNotMatch(preloadSource, /segments\?:/)
assert.doesNotMatch(preloadSource, /\|\s*string/)
assert.match(preloadSource, /exportHighlights: \(clips: \{ videoPath: string; start: number; end: number \}\[\]\) =>\s*ipcRenderer\.invoke\(\s*'export-highlights',\s*clips\s*,?\s*\)/)
assert.match(typesSource, /openFileDialog: \(\) => Promise<string\[] \| null>/)
assert.doesNotMatch(typesSource, /\/\/\s*exportHighlights/)
assert.doesNotMatch(typesSource, /segments\?:/)
assert.doesNotMatch(typesSource, /\|\s*string/)
assert.match(typesSource, /exportHighlights: \(clips: \{ videoPath: string; start: number; end: number \}\[\]\) =>\s*Promise<\{ error\?: string; cancelled\?: boolean; outputPath\?: string \}>/)
assert.match(providerSource, /createContext/)
assert.match(providerSource, /useLanguage/)
assert.match(providerSource, /useCopy/)
assert.match(providerSource, /navigator\.language/)
assert.match(providerSource, /writeStoredLanguage/)
assert.match(appSource, /<AnalysisScreen/)
assert.doesNotMatch(appSource, /<ProgressOverlay/)
assert.doesNotMatch(appSource, /exportHighlights\(state\.videoPath, activeSegments\)/)
assert.match(appSource, /createVideoRecords/)
assert.match(appSource, /createRalliesForVideo/)
assert.match(appSource, /getExportClips/)
assert.match(appSource, /const analyzeVideo = useCallback/)
assert.match(appSource, /const startBatchAnalysis = useCallback/)
assert.match(appSource, /for \(const video of videosToAnalyze\)/)
assert.match(appSource, /const batchCancelledRef = useRef\(false\)/)
assert.match(appExecutableSource, /if \(batchCancelledRef\.current \|\| batchRunIdRef\.current !== runId\) break/)
assert.match(appExecutableSource, /if \(!batchCancelledRef\.current && batchRunIdRef\.current === runId\) \{[\s\S]*dispatch\(\{ type: 'BATCH_ANALYSIS_DONE' \}\)/)
assert.match(appExecutableSource, /const batchRunIdRef = useRef\(0\)/)
assert.match(appExecutableSource, /batchRunIdRef\.current \+= 1/)
assert.match(appExecutableSource, /const runId = batchRunIdRef\.current/)
assert.match(appExecutableSource, /const analyzeVideo = useCallback\(async \(video: VideoRecord, runId: number, options\?: \{ reuseReport\?: boolean \}\) =>/)
assert.match(appExecutableSource, /const reuseReport = options\?\.reuseReport !== false/)
assert.match(appExecutableSource, /if \(reuseReport\) \{[\s\S]*existing = await window\.api\.loadReport\(video\.path\)[\s\S]*hasReusableAnalysisReport\(existing\)[\s\S]*return true[\s\S]*\}/)
assert.match(analyzeVideoSource, /catch \(error\) \{[\s\S]*dispatch\(\{ type: 'VIDEO_ANALYSIS_ERROR', videoId: video\.id, message: error instanceof Error \? error\.message : copy\.app\.unknownError \}\)[\s\S]*return false[\s\S]*\}/)
assert.match(analyzeVideoSource, /report = await window\.api\.loadReport\(video\.path\)[\s\S]*catch \(error\) \{[\s\S]*VIDEO_ANALYSIS_ERROR[\s\S]*return false/)
assert.match(appExecutableSource, /analyzeVideo\(video, runId, options\)/)
assert.match(appExecutableSource, /batchRunIdRef\.current !== runId/)
assert.match(handleVideosSelectedSource, /async \(paths: string\[\]\) => \{[\s\S]*await window\.api\.cancelAnalysis\(\)[\s\S]*dispatch\(\{ type: 'CREATE_BATCH', videos \}\)[\s\S]*startBatchAnalysis\(videos\)/)
assert.ok(handleRetryVideoSource.indexOf('batchRunIdRef.current += 1') >= 0)
assert.ok(handleRetryVideoSource.indexOf('batchCancelledRef.current = true') >= 0)
assert.ok(handleRetryVideoSource.indexOf('batchRunIdRef.current += 1') < handleRetryVideoSource.indexOf('await window.api.cancelAnalysis()'))
assert.ok(handleRetryVideoSource.indexOf('batchCancelledRef.current = true') < handleRetryVideoSource.indexOf('await window.api.cancelAnalysis()'))
assert.match(handleRetryVideoSource, /await window\.api\.cancelAnalysis\(\)/)
assert.match(handleRetryVideoSource, /startBatchAnalysis\(\[video\], \{ reuseReport: false \}\)/)
assert.ok(handleRetryVideoSource.indexOf('await window.api.cancelAnalysis()') < handleRetryVideoSource.indexOf('startBatchAnalysis([video], { reuseReport: false })'))
assert.match(appExecutableSource, /const retryVideo = runningVideo \?\? state\.videos\.find\(\(video\) => video\.status === 'error'\) \?\? null/)
assert.match(appExecutableSource, /onRetry=\{\(\) => \{[\s\S]*if \(retryVideo\) handleRetryVideo\(retryVideo\.id\)[\s\S]*\}\}/)
assert.doesNotMatch(appExecutableSource, /onRetry=\{\(\) => \{[\s\S]*if \(runningVideo\) handleRetryVideo\(runningVideo\.id\)[\s\S]*\}\}/)
assert.match(appExecutableSource, /<button onClick=\{\(\) => handleRetryVideo\(activeVideo\.id\)\}/)
assert.match(appExecutableSource, /const handleReturnWelcome[\s\S]*batchRunIdRef\.current \+= 1[\s\S]*window\.api\.cancelAnalysis\(\)/)
assert.match(appSource, /if \(runningVideo\) \{[\s\S]*dispatch\(\{ type: 'VIDEO_ANALYSIS_ERROR', videoId: runningVideo\.id, message: copy\.app\.cancelled \}\)[\s\S]*\}\s*dispatch\(\{ type: 'BATCH_ANALYSIS_ERROR', message: copy\.app\.cancelled \}\)/)
assert.match(appSource, /dispatch\(\{ type: 'CREATE_BATCH', videos \}\)/)
assert.match(appSource, /dispatch\(\{ type: 'VIDEO_ANALYSIS_DONE', videoId: video\.id, rallies \}\)/)
assert.match(appSource, /window\.api\.exportHighlights\(clips\)/)
assert.match(appSource, /<BatchVideoList/)
assert.match(appSource, /const handleReturnWelcome[\s\S]*window\.api\.cancelAnalysis\(\)[\s\S]*dispatch\(\{ type: 'CLOSE_VIDEO' \}\)/)
assert.match(appSource, /const handleReturnWelcome[\s\S]*setSeekTarget\(null\)/)
assert.match(appSource, /const handleReturnWelcome[\s\S]*setCurrentTime\(0\)/)
assert.match(appSource, /const handleReturnWelcome[\s\S]*setAutoPlay\(false\)/)
assert.match(appSource, /<LanguageProvider>/)
assert.match(appSource, /useCopy/)
assert.match(appSource, /useLanguage/)
assert.match(appSource, /aria-label=\{language === item \? `\$\{LANGUAGE_LABELS\[item\]\} selected` : `Switch to \$\{LANGUAGE_LABELS\[item\]\}`\}/)
assert.doesNotMatch(pythonBridgeExecutableSource, /if \(msg\.type === 'complete'\) \{[\s\S]*?resolve\(\{\}\)[\s\S]*?\}/)
assert.match(pythonBridgeExecutableSource, /let completed = false/)
assert.match(pythonBridgeExecutableSource, /completed = true/)
assert.match(pythonBridgeExecutableSource, /let settled = false/)
assert.match(pythonBridgeExecutableSource, /const settle = \(result: \{ error\?: string \}\) =>/)
assert.match(pythonBridgeExecutableSource, /(?:analysisProcess|child)\.on\('close', \(code\) => \{[\s\S]*(?:analysisProcess = null|clearAnalysisProcess\(child\))[\s\S]*(?:else )?if \(completed\) \{[\s\S]*settle\(\{\}\)/)
assert.match(cancelAnalysisHandlerSource, /new Promise(?:<[^>]+>)?\(\(resolve\) => \{[\s\S]*(?:processToCancel|analysisProcess)\.(?:once|on)\('close'[\s\S]*(?:processToCancel|analysisProcess)\.(?:once|on)\('error'/)
assert.doesNotMatch(cancelAnalysisHandlerSource, /kill\(\)[\s\S]{0,160}analysisProcess = null/)

const appStateSource = fs.readFileSync(path.join(root, 'src', 'renderer', 'state', 'AppState.tsx'), 'utf8')
assert.match(appStateSource, /RESTORE_RECOMMENDED/)
assert.match(appStateSource, /case 'RESTORE_RECOMMENDED'/)
assert.match(appStateSource, /included: rally\.score > INCLUDE_THRESHOLD/)
assert.doesNotMatch(appStateSource, /case 'RESTORE_RECOMMENDED':[\s\S]*startAdjusted: undefined/)
assert.equal(MIN_SEGMENT_DURATION, 0.5)
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
const sourceSwitchState = {
  ...reducerBatchState,
  videos: completedBatchVideos,
  activeVideoId: batchVideos[0].id,
  rallies: [
    ...firstVideoRallies,
    ...secondVideoRallies,
  ],
}
assert.equal(
  reducer({ ...sourceSwitchState, selectedRallyId: firstVideoRallies[0].id }, { type: 'SET_ACTIVE_VIDEO', id: batchVideos[1].id }).selectedRallyId,
  null,
)
assert.equal(
  reducer({ ...sourceSwitchState, selectedRallyId: secondVideoRallies[0].id }, { type: 'SET_ACTIVE_VIDEO', id: batchVideos[1].id }).selectedRallyId,
  secondVideoRallies[0].id,
)
assert.equal(reducer(reducerBatchState, { type: 'VIDEO_ANALYSIS_RETRY', videoId: 'video-2' }).videos[1].status, 'running')
assert.equal(reducer(reducerBatchState, { type: 'VIDEO_ANALYSIS_ERROR', videoId: 'video-2', message: 'still bad' }).videos[1].errorMessage, 'still bad')
for (const actionType of ['VIDEO_ANALYSIS_START', 'VIDEO_ANALYSIS_RETRY']) {
  const staleBatchState = {
    ...reducerBatchState,
    selectedRallyId: 'video-1-rally-1',
    rallies: [
      ...reducerBatchState.rallies,
      { id: 'video-2-rally-0', videoId: 'video-2', sourceIndex: 0, index: 0, start: 30, end: 34, score: 2, included: true, features: {} },
    ],
  }
  const rerunState = reducer(staleBatchState, { type: actionType, videoId: 'video-1' })
  assert.deepEqual(rerunState.rallies.map((rally) => rally.id), ['video-2-rally-0'])
  assert.equal(rerunState.selectedRallyId, null)
  assert.equal(rerunState.videos[0].rallyCount, 0)
  assert.equal(rerunState.videos[1].rallyCount, 0)
}
assert.equal(reducer({ ...reducerBatchState, selectedRallyId: 'video-1-rally-1' }, { type: 'VIDEO_ANALYSIS_RETRY', videoId: 'video-2' }).selectedRallyId, 'video-1-rally-1')
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
