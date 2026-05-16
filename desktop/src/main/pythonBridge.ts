import { spawn, ChildProcess } from 'node:child_process'
import { app, ipcMain, BrowserWindow } from 'electron'
import path from 'node:path'
import fs from 'node:fs'

let analysisProcess: ChildProcess | null = null

function getEngineCommand(): { cmd: string; args: string[] } {
  if (app.isPackaged) {
    const enginePath = path.join(process.resourcesPath, 'engine', 'TennisHighlightAnalysis', 'TennisHighlightAnalysis.exe')
    return { cmd: enginePath, args: [] }
  }
  return { cmd: 'python', args: ['-m', 'engine.pipeline'] }
}

function getProjectRoot(): string {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'engine')
  }
  return path.resolve(path.join(__dirname, '../../..'))
}

export function setupPythonBridge() {
  ipcMain.handle('run-analysis', async (event, videoPath: string) => {
    if (analysisProcess) {
      return { error: 'Analysis already running' }
    }

    const { cmd, args } = getEngineCommand()
    const fullArgs = [...args, videoPath, '--json-progress']
    const cwd = getProjectRoot()

    const env = { ...process.env }
    if (app.isPackaged) {
      const ffmpegDir = path.join(process.resourcesPath, 'engine', 'ffmpeg')
      env.PATH = ffmpegDir + path.delimiter + (env.PATH ?? '')
    }

    return new Promise<{ error?: string }>((resolve) => {
      analysisProcess = spawn(cmd, fullArgs, {
        cwd,
        env,
        stdio: ['ignore', 'pipe', 'pipe'],
      })

      const win = BrowserWindow.fromWebContents(event.sender)
      let stdoutBuf = ''
      let stderrBuf = ''

      analysisProcess.stdout?.on('data', (data: Buffer) => {
        stdoutBuf += data.toString()
        const parts = stdoutBuf.split('\n')
        stdoutBuf = parts.pop()!
        for (const line of parts) {
          const trimmed = line.trim()
          if (!trimmed) continue
          try {
            const msg = JSON.parse(trimmed)
            win?.webContents.send('analysis-progress', msg)
            if (msg.type === 'complete') {
              resolve({})
            }
            if (msg.type === 'error') {
              resolve({ error: msg.message })
            }
          } catch {
            // non-JSON output, ignore
          }
        }
      })

      analysisProcess.stderr?.on('data', (data: Buffer) => {
        const text = data.toString()
        stderrBuf += text
        console.error('[python]', text)
        win?.webContents.send('analysis-progress', { type: 'stderr', message: text })
      })

      analysisProcess.on('close', (code) => {
        // Process remaining buffered output
        if (stdoutBuf.trim()) {
          try {
            const msg = JSON.parse(stdoutBuf.trim())
            win?.webContents.send('analysis-progress', msg)
            if (msg.type === 'complete') {
              analysisProcess = null
              resolve({})
              return
            }
          } catch { /* ignore */ }
        }
        analysisProcess = null
        if (code !== 0) {
          const detail = stderrBuf.trim().split('\n').pop() || ''
          resolve({ error: detail || `Process exited with code ${code}` })
        }
      })

      analysisProcess.on('error', (err) => {
        analysisProcess = null
        resolve({ error: err.message })
      })
    })
  })

  ipcMain.handle('cancel-analysis', () => {
    if (analysisProcess) {
      analysisProcess.kill()
      analysisProcess = null
    }
  })

  ipcMain.handle('load-report', async (_event, reportOrVideoPath: string) => {
    // Accept either a direct report path or a video path
    if (reportOrVideoPath.endsWith('.json') && fs.existsSync(reportOrVideoPath)) {
      return JSON.parse(fs.readFileSync(reportOrVideoPath, 'utf-8'))
    }
    const stem = path.basename(reportOrVideoPath, path.extname(reportOrVideoPath))
    const dir = path.dirname(reportOrVideoPath)
    const reportPath = path.join(dir, `output_${stem}`, 'full_report.json')
    if (fs.existsSync(reportPath)) {
      return JSON.parse(fs.readFileSync(reportPath, 'utf-8'))
    }
    return null
  })
}
