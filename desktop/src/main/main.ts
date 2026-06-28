import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron'
import path from 'node:path'
import fs from 'node:fs'
import Store from 'electron-store'
import { setupPythonBridge } from './pythonBridge'
import { setupFfmpegBridge } from './ffmpegBridge'

const store = new Store<{ recentProjects: string[] }>({
  defaults: { recentProjects: [] },
})

process.env.DIST_ELECTRON = path.join(__dirname, '..')
process.env.DIST = path.join(process.env.DIST_ELECTRON, '../dist')
process.env.VITE_PUBLIC = app.isPackaged
  ? process.env.DIST
  : path.join(process.env.DIST_ELECTRON, '../../public')

let win: BrowserWindow | null = null
const VITE_DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL

if (process.platform === 'win32') {
  app.setAppUserModelId('com.breakpoint.app')
}

function getWindowIconPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'icon.ico')
  }
  return path.resolve(path.join(__dirname, '../../build/icon.ico'))
}

function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 600,
    icon: getWindowIconPath(),
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, '../preload/preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: false,
    },
  })

  if (VITE_DEV_SERVER_URL) {
    win.loadURL(VITE_DEV_SERVER_URL)
  } else {
    win.loadFile(path.join(process.env.DIST!, 'index.html'))
  }
}

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

ipcMain.handle('get-recent-projects', () => {
  return store.get('recentProjects')
})

ipcMain.handle('get-app-version', () => {
  return app.getVersion()
})

ipcMain.handle('check-resources', () => {
  if (!app.isPackaged) return { ok: true, missing: [] }
  const checks = [
    { label: 'engine (TennisHighlightAnalysis.exe)', path: path.join(process.resourcesPath, 'engine', 'TennisHighlightAnalysis', 'TennisHighlightAnalysis.exe') },
    { label: 'ffmpeg (ffmpeg.exe)', path: path.join(process.resourcesPath, 'engine', 'ffmpeg', 'ffmpeg.exe') },
  ]
  const missing = checks.filter((c) => !fs.existsSync(c.path)).map((c) => c.label)
  return { ok: missing.length === 0, missing }
})

ipcMain.handle('open-path', async (_event, targetPath: string) => {
  return shell.openPath(targetPath)
})

app.whenReady().then(() => {
  setupPythonBridge()
  setupFfmpegBridge()
  createWindow()
})

app.on('window-all-closed', () => {
  win = null
  app.quit()
})
