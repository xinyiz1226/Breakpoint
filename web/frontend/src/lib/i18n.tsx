"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Language = "en" | "zh";

const en = {
  appName: "BREAKPOINT",
  tagline: "The match, cut to its pulse.",
  signIn: "Sign in",
  createAccount: "Create account",
  email: "Email address",
  password: "Password",
  newPassword: "New password",
  confirmNewPassword: "Confirm new password",
  passwordMismatch: "Passwords do not match.",
  registerIntro: "Enter your email. You will choose a password only after opening the verification link.",
  registrationSent: "Verification sent. Check your inbox to establish your credentials.",
  verifyTitle: "Establish your account",
  verifyIntro: "This one-time link proves mailbox ownership. Choose the password you will use to sign in.",
  accountVerifiedNotice: "Account verified and password set successfully. Sign in to continue.",
  forgotPassword: "Forgot password?",
  forgotTitle: "Recover access",
  forgotSent: "If the account exists, a reset link is on its way.",
  resetTitle: "Choose a new password",
  passwordResetNotice: "Password reset successfully. Sign in with your new password.",
  submit: "Continue",
  backToLogin: "Back to sign in",
  homeEyebrow: "From full match to publish-ready cut",
  homeTitleLineOne: "Full match.",
  homeTitleLineTwo: "Key rallies.",
  homeIntro: "Upload a match and Breakpoint finds every rally. Review the cut, trim to 0.1 second, then export a highlight made for this match.",
  homePrimaryCta: "Create your first match",
  homeLimitNote: "Videos up to 3 hours and 20 GB",
  homeWorkflow: "How Breakpoint works",
  homeStepUpload: "Upload match",
  homeStepUploadNote: "Choose the full source video",
  homeStepDetect: "Find rallies",
  homeStepDetectNote: "Split the match automatically",
  homeStepTrim: "Trim precisely",
  homeStepTrimNote: "Adjust boundaries by 0.1 sec",
  homeStepExport: "Export highlight",
  homeStepExportNote: "Generate a shareable video",
  homePreviewLabel: "Real editing workflow",
  homePreviewStatus: "8 rallies selected",
  homePreviewPath: "Match room / Weekend singles / Review",
  projects: "Match rooms",
  projectsIntro: "One video. One focused edit. Seven days to finish the cut.",
  newProject: "New match",
  projectName: "Project name",
  create: "Create",
  delete: "Delete",
  open: "Open",
  noProjects: "No matches on the board yet.",
  noProjectsHint: "Create a match room, then upload one full match or practice session.",
  quota: "Monthly court time",
  analysis: "Analysis",
  storage: "Storage",
  activeJobs: "Active jobs",
  logout: "Log out",
  uploadTitle: "Send the full match",
  uploadIntro: "MP4, MOV, MKV, WebM or AVI · up to 20 GB · up to 3 hours",
  uploadDetail: "Choose one complete match video. We validate the file first, then find every rally and build an editable timeline.",
  dropVideo: "Drop a video or choose a file",
  dropVideoHint: "We show file details before anything uploads",
  uploadFormats: "MP4 · MOV · MKV · WebM · AVI",
  uploadRetentionTitle: "Source video kept for 7 days",
  uploadRetentionHint: "Finish review, trimming and export before the source is removed automatically.",
  uploadAllowance: "Uploading starts using this month's analysis allowance. Your video is never published automatically.",
  uploadStage: "Uploading source video",
  chooseVideo: "Choose video",
  replaceVideo: "Choose another",
  uploading: "Uploading",
  uploaded: "Upload complete",
  duration: "Duration",
  size: "File size",
  startUpload: "Upload & analyze",
  preparing: "Reading video metadata",
  progressTitle: "Match analysis",
  progressIntro: "Keep this tab open. Processing continues if you leave.",
  queued: "In the queue",
  running: "Reading the match",
  succeeded: "Review ready",
  failed: "Analysis stopped",
  cancelled: "Analysis cancelled",
  cancel: "Cancel",
  cleanupPending: "Storage cleanup is pending. Retry cancellation before starting again.",
  uploadCancellationPending: "Finishing upload cancellation…",
  createNewMatch: "Create a new match",
  checkingSession: "Checking session…",
  sessionUnavailable: "We could not restore your session. Check your connection and try again.",
  retrySession: "Retry session",
  retry: "Retry",
  review: "Open review",
  reconnecting: "Reconnecting to live scoring…",
  reviewTitle: "Rally desk",
  sourceExpired: "The source video is no longer available.",
  sourceExpiredHint: "Reports and edits remain, but playback and new exports require a live source.",
  matchMap: "Match map",
  suggestedOnly: "Suggested only",
  showAll: "Show all",
  highlight: "Highlight",
  keep: "Keep",
  cut: "Cut",
  rallyQueue: "Rally queue",
  includeAll: "Include all",
  recommended: "Recommended",
  excludeAll: "Exclude all",
  included: "included",
  trim: "Precise trim",
  start: "Start",
  end: "End",
  reset: "Reset",
  saved: "Saved",
  saving: "Saving",
  saveFailed: "Save failed",
  retrySave: "Retry save",
  export: "Create highlight reel",
  exporting: "Building highlight reel",
  exportReady: "Highlight reel ready",
  download: "Download MP4",
  noSelection: "Include at least one rally to export.",
  immutableSnapshot: "This export keeps the current rally selection, even if you edit later.",
  loading: "Loading match data…",
  tryAgain: "Try again",
  unexpected: "Something went off court.",
};

const zh: Record<keyof typeof en, string> = {
  appName: "BREAKPOINT",
  tagline: "捕捉比赛脉搏，剪出每一分精彩。",
  signIn: "登录",
  createAccount: "创建账户",
  email: "邮箱地址",
  password: "密码",
  newPassword: "新密码",
  confirmNewPassword: "确认新密码",
  passwordMismatch: "两次输入的密码不一致。",
  registerIntro: "输入邮箱。打开验证链接后再设置密码，确保账户属于邮箱本人。",
  registrationSent: "验证邮件已发送。请在邮箱中完成账户设置。",
  verifyTitle: "设置你的账户",
  verifyIntro: "此一次性链接用于验证邮箱归属。请设置今后登录使用的密码。",
  accountVerifiedNotice: "邮箱验证和密码设置成功，请登录继续。",
  forgotPassword: "忘记密码？",
  forgotTitle: "找回账户",
  forgotSent: "如果该账户存在，重置链接已发送。",
  resetTitle: "设置新密码",
  passwordResetNotice: "密码重置成功，请使用新密码登录。",
  submit: "继续",
  backToLogin: "返回登录",
  homeEyebrow: "从完整比赛到可发布集锦",
  homeTitleLineOne: "把整场比赛，",
  homeTitleLineTwo: "剪成关键回合。",
  homeIntro: "上传比赛视频，Breakpoint 自动识别每个回合。你只需确认、精确到 0.1 秒裁剪，然后导出属于这场比赛的集锦。",
  homePrimaryCta: "创建第一场比赛",
  homeLimitNote: "支持最长 3 小时、20 GB 的比赛视频",
  homeWorkflow: "Breakpoint 工作流程",
  homeStepUpload: "上传比赛",
  homeStepUploadNote: "选择完整源视频",
  homeStepDetect: "识别回合",
  homeStepDetectNote: "自动切分比赛片段",
  homeStepTrim: "精确裁剪",
  homeStepTrimNote: "以 0.1 秒微调边界",
  homeStepExport: "导出集锦",
  homeStepExportNote: "生成可分享视频",
  homePreviewLabel: "真实剪辑工作流",
  homePreviewStatus: "已选 8 个回合",
  homePreviewPath: "比赛空间 / 周末单打 / 剪辑确认",
  projects: "比赛空间",
  projectsIntro: "一个视频，一次专注剪辑，七天内完成作品。",
  newProject: "新建比赛",
  projectName: "项目名称",
  create: "创建",
  delete: "删除",
  open: "打开",
  noProjects: "记分牌上还没有比赛。",
  noProjectsHint: "创建比赛空间，然后上传一场完整比赛或训练视频。",
  quota: "本月处理额度",
  analysis: "分析时长",
  storage: "存储空间",
  activeJobs: "进行中任务",
  logout: "退出登录",
  uploadTitle: "上传完整比赛",
  uploadIntro: "MP4、MOV、MKV、WebM 或 AVI · 最大 20 GB · 最长 3 小时",
  uploadDetail: "选择一段完整比赛视频。系统会先校验文件，再识别每个回合并生成可编辑的时间线。",
  dropVideo: "拖入视频，或点击选择",
  dropVideoHint: "选中后会先显示文件信息，不会立即上传",
  uploadFormats: "MP4 · MOV · MKV · WebM · AVI",
  uploadRetentionTitle: "源视频保留 7 天",
  uploadRetentionHint: "请在保留期内完成确认、裁剪与导出，到期后源视频会自动清理。",
  uploadAllowance: "上传会开始占用本月分析额度，视频不会自动发布。",
  uploadStage: "正在上传源视频",
  chooseVideo: "选择视频",
  replaceVideo: "重新选择",
  uploading: "正在上传",
  uploaded: "上传完成",
  duration: "时长",
  size: "文件大小",
  startUpload: "上传并分析",
  preparing: "正在读取视频信息",
  progressTitle: "比赛分析",
  progressIntro: "可离开此页面，后台仍会继续处理。",
  queued: "等待处理",
  running: "正在读取比赛",
  succeeded: "可以开始确认",
  failed: "分析已停止",
  cancelled: "分析已取消",
  cancel: "取消",
  cleanupPending: "存储清理尚未完成。请重试取消后再重新上传。",
  uploadCancellationPending: "正在完成上传取消操作…",
  createNewMatch: "创建新比赛",
  checkingSession: "正在检查会话…",
  sessionUnavailable: "无法恢复会话。请检查网络连接后重试。",
  retrySession: "重试会话",
  retry: "重试",
  review: "打开剪辑台",
  reconnecting: "正在重新连接实时进度…",
  reviewTitle: "回合剪辑台",
  sourceExpired: "源视频已过期，无法播放。",
  sourceExpiredHint: "报告和编辑记录仍保留，但播放和新导出需要有效源视频。",
  matchMap: "整场比赛地图",
  suggestedOnly: "只看推荐",
  showAll: "显示全部",
  highlight: "高光",
  keep: "保留",
  cut: "剔除",
  rallyQueue: "回合队列",
  includeAll: "全部保留",
  recommended: "恢复推荐",
  excludeAll: "全部剔除",
  included: "个已选择",
  trim: "精确裁剪",
  start: "开始",
  end: "结束",
  reset: "重置",
  saved: "已保存",
  saving: "保存中",
  saveFailed: "保存失败",
  retrySave: "重试保存",
  export: "生成精彩集锦",
  exporting: "正在生成精彩集锦",
  exportReady: "精彩集锦已完成",
  download: "下载 MP4",
  noSelection: "请至少保留一个回合再导出。",
  immutableSnapshot: "本次导出会固定当前选择，之后的编辑不会改变它。",
  loading: "正在载入比赛数据…",
  tryAgain: "重试",
  unexpected: "比赛暂时中断。",
};

type MessageKey = keyof typeof en;

interface I18nValue {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: MessageKey) => string;
}

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>("en");

  useEffect(() => {
    const saved = window.localStorage.getItem("breakpoint-language");
    if (saved === "en" || saved === "zh") setLanguageState(saved);
  }, []);

  const setLanguage = useCallback((next: Language) => {
    setLanguageState(next);
    window.localStorage.setItem("breakpoint-language", next);
  }, []);

  useEffect(() => {
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  }, [language]);

  const value = useMemo<I18nValue>(
    () => ({
      language,
      setLanguage,
      t: (key) => (language === "zh" ? zh[key] : en[key]),
    }),
    [language, setLanguage],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used inside I18nProvider");
  return value;
}

export function LanguageSwitch() {
  const { language, setLanguage } = useI18n();
  return (
    <button
      className="language-switch"
      onClick={() => setLanguage(language === "en" ? "zh" : "en")}
      aria-label={language === "en" ? "切换到中文" : "Switch to English"}
    >
      <span className={language === "en" ? "active" : ""}>EN</span>
      <i />
      <span className={language === "zh" ? "active" : ""}>中文</span>
    </button>
  );
}
