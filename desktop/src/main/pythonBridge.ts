import { spawn, ChildProcess } from 'node:child_process'
import { app, ipcMain, BrowserWindow } from 'electron'
import path from 'node:path'
import fs from 'node:fs'

let analysisProcess: ChildProcess | null = null
let analysisCancellationPromise: Promise<void> | null = null

function clearAnalysisProcess(child: ChildProcess) {
  if (analysisProcess === child) {
    analysisProcess = null
    analysisCancellationPromise = null
  }
}

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
      let settled = false
      const settle = (result: { error?: string }) => {
        if (settled) return
        settled = true
        resolve(result)
      }

      const child = spawn(cmd, fullArgs, {
        cwd,
        env,
        stdio: ['ignore', 'pipe', 'pipe'],
      })
      analysisProcess = child

      const win = BrowserWindow.fromWebContents(event.sender)
      let stdoutBuf = ''
      let stderrBuf = ''
      let completed = false
      let completionError: string | null = null

      const handleStdoutLine = (line: string) => {
        const trimmed = line.trim()
        if (!trimmed) return
        try {
          const msg = JSON.parse(trimmed)
          win?.webContents.send('analysis-progress', msg)
          if (msg.type === 'complete') {
            completed = true
          }
          if (msg.type === 'error') {
            completionError = msg.traceback ?? msg.message ?? 'Analysis failed'
          }
        } catch {
          // non-JSON output, ignore
        }
      }

      child.stdout?.on('data', (data: Buffer) => {
        stdoutBuf += data.toString()
        const parts = stdoutBuf.split('\n')
        stdoutBuf = parts.pop()!
        for (const line of parts) {
          handleStdoutLine(line)
        }
      })

      child.stderr?.on('data', (data: Buffer) => {
        const text = data.toString()
        stderrBuf += text
        console.error('[python]', text)
        win?.webContents.send('analysis-progress', { type: 'stderr', message: text })
      })

      child.on('close', (code) => {
        if (stdoutBuf.trim()) {
          handleStdoutLine(stdoutBuf)
        }
        clearAnalysisProcess(child)
        if (completionError) {
          settle({ error: completionError })
        } else if (code !== 0) {
          const detail = stderrBuf.trim()
          settle({ error: detail || `Process exited with code ${code}` })
        } else if (completed) {
          settle({})
        } else {
          settle({ error: 'Analysis process ended before completion' })
        }
      })

      child.on('error', (err) => {
        clearAnalysisProcess(child)
        settle({ error: err.message })
      })
    })
  })

  ipcMain.handle('cancel-analysis', async () => {
    const processToCancel = analysisProcess
    if (!processToCancel) {
      return
    }

    if (!analysisCancellationPromise) {
      analysisCancellationPromise = new Promise<void>((resolve) => {
        let settled = false
        const settle = () => {
          if (settled) return
          settled = true
          processToCancel.off('close', settle)
          processToCancel.off('error', settle)
          resolve()
        }

        processToCancel.once('close', settle)
        processToCancel.once('error', settle)
      })
      processToCancel.kill()
    }

    return analysisCancellationPromise
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
