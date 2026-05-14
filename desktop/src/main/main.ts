import { app, BrowserWindow, dialog, ipcMain } from 'electron'
import path from 'node:path'
import Store from 'electron-store'
import { setupPythonBridge } from './pythonBridge'
import { setupFfmpegBridge } from './ffmpegBridge'

const store = new Store<{ recentProjects: string[] }>({
  defaults: { recentProjects: [] },
})

process.env.DIST_ELECTRON = path.join(__dirname)
process.env.DIST = path.join(process.env.DIST_ELECTRON, '../dist')
process.env.VITE_PUBLIC = app.isPackaged
  ? process.env.DIST
  : path.join(process.env.DIST_ELECTRON, '../../public')

let win: BrowserWindow | null = null
const VITE_DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL

function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 600,
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
    properties: ['openFile'],
    filters: [
      { name: 'Video', extensions: ['mp4', 'mkv', 'avi', 'mov'] },
    ],
  })
  if (result.canceled || result.filePaths.length === 0) return null
  const filePath = result.filePaths[0]

  const recent = store.get('recentProjects')
  const updated = [filePath, ...recent.filter((p) => p !== filePath)].slice(0, 10)
  store.set('recentProjects', updated)

  return filePath
})

ipcMain.handle('get-recent-projects', () => {
  return store.get('recentProjects')
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
