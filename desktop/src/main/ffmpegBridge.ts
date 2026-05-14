import { spawn } from 'node:child_process'
import { ipcMain, dialog, shell, BrowserWindow } from 'electron'
import path from 'node:path'

interface ExportSegment {
  start: number
  end: number
}

export function setupFfmpegBridge() {
  ipcMain.handle('export-highlights', async (event, videoPath: string, segments: ExportSegment[]) => {
    const win = BrowserWindow.fromWebContents(event.sender)

    const result = await dialog.showSaveDialog({
      defaultPath: path.join(
        path.dirname(videoPath),
        `${path.basename(videoPath, path.extname(videoPath))}_highlights.mp4`,
      ),
      filters: [{ name: 'MP4', extensions: ['mp4'] }],
    })

    if (result.canceled || !result.filePath) return { cancelled: true }
    const outputPath = result.filePath

    const sorted = [...segments].sort((a, b) => a.start - b.start)

    const inputs: string[] = []
    const filterParts: string[] = []
    for (let i = 0; i < sorted.length; i++) {
      const seg = sorted[i]
      inputs.push('-ss', String(seg.start), '-t', String(seg.end - seg.start), '-i', videoPath)
      filterParts.push(`[${i}:v][${i}:a]`)
    }

    const filterStr = filterParts.join('') + `concat=n=${sorted.length}:v=1:a=1[outv][outa]`

    const cmd = ['ffmpeg', '-y', ...inputs, '-filter_complex', filterStr, '-map', '[outv]', '-map', '[outa]', outputPath]

    return new Promise<{ error?: string; cancelled?: boolean; outputPath?: string }>((resolve) => {
      const proc = spawn(cmd[0], cmd.slice(1), { stdio: ['ignore', 'pipe', 'pipe'] })

      proc.stderr?.on('data', (data: Buffer) => {
        const line = data.toString()
        const match = line.match(/time=(\d+):(\d+):(\d+\.\d+)/)
        if (match) {
          const secs = parseInt(match[1]) * 3600 + parseInt(match[2]) * 60 + parseFloat(match[3])
          win?.webContents.send('export-progress', { time: secs })
        }
      })

      proc.on('close', (code) => {
        if (code === 0) {
          resolve({ outputPath })
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
