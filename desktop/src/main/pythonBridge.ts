import { spawn, ChildProcess } from 'node:child_process'
import { app, ipcMain, BrowserWindow } from 'electron'
import path from 'node:path'
import fs from 'node:fs'

let analysisProcess: ChildProcess | null = null

function getEngineCommand(): { cmd: string; args: string[] } {
  if (app.isPackaged) {
    const enginePath = path.join(process.resourcesPath, 'engine', 'TennisHighlightAnalysis.exe')
    return { cmd: enginePath, args: [] }
  }
  return { cmd: 'python', args: ['-m', 'phase1.analyze'] }
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
    const fullArgs = [...args, videoPath, '--json-progress', '--no-vision']
    const cwd = getProjectRoot()

    return new Promise<{ error?: string }>((resolve) => {
      analysisProcess = spawn(cmd, fullArgs, {
        cwd,
        stdio: ['ignore', 'pipe', 'pipe'],
      })

      const win = BrowserWindow.fromWebContents(event.sender)

      analysisProcess.stdout?.on('data', (data: Buffer) => {
        const lines = data.toString().split('\n').filter(Boolean)
        for (const line of lines) {
          try {
            const msg = JSON.parse(line)
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
        // stderr from Python — log but don't treat as fatal
        console.error('[python]', data.toString())
      })

      analysisProcess.on('close', (code) => {
        analysisProcess = null
        if (code !== 0) {
          resolve({ error: `Process exited with code ${code}` })
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

  ipcMain.handle('load-report', async (_event, videoPath: string) => {
    const stem = path.basename(videoPath, path.extname(videoPath))
    const dir = path.dirname(videoPath)
    const reportPath = path.join(dir, `output_${stem}`, 'full_report.json')
    if (fs.existsSync(reportPath)) {
      return JSON.parse(fs.readFileSync(reportPath, 'utf-8'))
    }
    return null
  })
}
