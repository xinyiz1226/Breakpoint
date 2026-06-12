import { spawn, ChildProcess } from 'node:child_process'
import { app, ipcMain, dialog, BrowserWindow } from 'electron'
import { unlink } from 'node:fs/promises'
import path from 'node:path'

function getFfmpegPath(): string {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'engine', 'ffmpeg', 'ffmpeg.exe')
  }
  return 'ffmpeg'
}

interface ExportClip {
  videoPath: string
  start: number
  end: number
}

export function setupFfmpegBridge() {
  let activeProc: ChildProcess | null = null

  ipcMain.handle('cancel-export', () => {
    if (activeProc) {
      activeProc.kill()
      activeProc = null
    }
  })

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

    if (result.canceled || !result.filePath) return { cancelled: true }
    const outputPath = result.filePath

    const sorted = [...clips].filter((clip) => clip.end > clip.start)
    if (sorted.length === 0) return { error: 'No valid clips selected for export' }

    const inputs: string[] = []
    const filterParts: string[] = []
    for (let i = 0; i < sorted.length; i++) {
      const clip = sorted[i]
      inputs.push('-ss', String(clip.start), '-t', String(clip.end - clip.start), '-i', clip.videoPath)
      filterParts.push(`[${i}:v][${i}:a]`)
    }

    const filterStr = filterParts.join('') + `concat=n=${sorted.length}:v=1:a=1[outv][outa]`

    const ffmpeg = getFfmpegPath()
    const cmd = [ffmpeg, '-y', ...inputs, '-filter_complex', filterStr, '-map', '[outv]', '-map', '[outa]', outputPath]

    return new Promise<{ error?: string; cancelled?: boolean; outputPath?: string }>((resolve) => {
      const proc = spawn(cmd[0], cmd.slice(1), { stdio: ['ignore', 'pipe', 'pipe'] })
      activeProc = proc

      proc.stderr?.on('data', (data: Buffer) => {
        const line = data.toString()
        const match = line.match(/time=(\d+):(\d+):(\d+\.\d+)/)
        if (match) {
          const secs = parseInt(match[1]) * 3600 + parseInt(match[2]) * 60 + parseFloat(match[3])
          win?.webContents.send('export-progress', { time: secs })
        }
      })

      proc.on('close', (code, signal) => {
        activeProc = null
        if (code === 0) {
          resolve({ outputPath })
        } else if (signal === 'SIGTERM' || signal === 'SIGKILL') {
          unlink(outputPath).catch(() => {})
          resolve({ cancelled: true })
        } else {
          resolve({ error: `ffmpeg exited with code ${code}` })
        }
      })

      proc.on('error', (err) => {
        resolve({ error: err.message })
      })
    })
  })
}
