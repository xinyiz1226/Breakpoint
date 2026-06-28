export type Language = 'en' | 'zh'

export const LANGUAGE_LABELS: Record<Language, string> = {
  en: 'EN',
  zh: '中文',
}

interface CopyStage {
  title: string
  detail: string
}

interface CopyFlowStage extends CopyStage {
  stageLabel: string
}

type AnalysisPanelStages = [CopyStage, CopyStage, CopyStage, CopyStage]
type FlowStages = [CopyFlowStage, CopyFlowStage, CopyFlowStage, CopyFlowStage]

interface RallyTitleCopy {
  multiHit: string
  highIntensity: string
  short: string
  suffix: string
  joinPartsWithSpace: boolean
  recommended: string
  regular: string
}

export interface Copy {
  common: {
    appName: string
    desktop: string
    open: string
    edited: string
    hitCountUnknown: string
  }
  language: {
    label: string
  }
  welcome: {
    eyebrow: string
    description: string
    startLabel: string
    importTitle: string
    importDetail: string
    dropHint: string
    recentTitle: string
    shortcutImport: string
    shortcutQuit: string
  }
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
  app: {
    resourceErrorTitle: string
    missingResources: string
    reviewTitle: string
    returnWelcome: string
    rerunAnalysis: string
    exportFailedPrefix: string
    exportComplete: string
    cancelled: string
    reportMissing: string
    unknownError: string
  }
  analysisScreen: {
    problemTitle: string
    runningTitle: string
  }
  analysisPanel: {
    failedEyebrow: string
    failedTitle: string
    retry: string
    returnWelcome: string
    autoStart: string
    headline: string
    intro: string
    cancel: string
    subProgressTitle: string
    statusDone: string
    statusCurrent: string
    statusNext: string
    stages: AnalysisPanelStages
  }
  matchMap: {
    title: string
    subtitle: string
    highlight: string
    keep: string
    discarded: string
    intensity: string
    showAll: string
    recommendedOnly: string
  }
  rallyQueue: {
    title: string
    exportCount: (selected: number, total: number) => string
    includeAll: string
    restoreRecommended: string
    excludeAll: string
    empty: string
    exportSummary: (selected: number) => string
    exportDuration: (duration: string) => string
    cancelExport: string
    openExport: string
    toneHighlight: string
    toneKeep: string
    toneDiscarded: string
    hits: (count: number | string) => string
    intensity: (score: string) => string
    start: string
    end: string
    trimHelp: (start: string, end: string) => string
    sourceLabel: (source: string) => string
    reset: string
  }
  flow: {
    stages: FlowStages
    waitingTitle: string
    waitingDetail: string
    waitingStageLabel: string
    groupLabel: (current: number, total: number) => string
    progressLabel: (step: number, total: number, groupLabel?: string) => string
    visualHeadlineFiltering: string
    visualHeadlineAnalyzing: string
    visualDetail: (segment: number, total: number, percent: number) => string
    reviewInstruction: string
    exportNoSelection: string
    exportSelected: string
    exporting: (selected: number) => string
    rallyTitle: RallyTitleCopy
  }
}

export const COPY: Record<Language, Copy> = {
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
      importTitle: 'Import videos',
      importDetail: 'Choose one or more match or practice videos. Breakpoint analyzes them as a batch.',
      dropHint: 'Or drop video files here',
      recentTitle: 'Open recent videos',
      shortcutImport: 'Import video',
      shortcutQuit: 'Quit',
    },
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
      headline: 'AI is analyzing\nthe full video',
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
      sourceLabel: (source: string) => `Source: ${source}`,
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
        joinPartsWithSpace: true,
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
      importTitle: '导入多个视频',
      importDetail: '选择一个或多个比赛/训练视频，Breakpoint 会按批次逐个分析。',
      dropHint: '或把多个视频文件拖到这里',
      recentTitle: '打开之前的视频',
      shortcutImport: '导入视频',
      shortcutQuit: '退出',
    },
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
    app: {
      resourceErrorTitle: '资源错误',
      missingResources: '安装包缺少必要资源：',
      reviewTitle: '确认回合片段',
      returnWelcome: '返回欢迎页',
      rerunAnalysis: '重新处理',
      exportFailedPrefix: '导出失败：',
      exportComplete: '精彩合集已导出',
      cancelled: '已取消',
      reportMissing: '找不到分析报告文件',
      unknownError: '未知错误',
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
      headline: '正在用 AI\n分析整场视频',
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
      sourceLabel: (source: string) => `来源：${source}`,
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
        joinPartsWithSpace: false,
        recommended: '推荐回合',
        regular: '普通回合',
      },
    },
  },
}
