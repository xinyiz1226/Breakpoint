"use strict";
const electron = require("electron");
const path = require("node:path");
const Store = require("electron-store");
const node_child_process = require("node:child_process");
const fs = require("node:fs");
let analysisProcess = null;
function getEngineCommand() {
  if (electron.app.isPackaged) {
    const enginePath = path.join(process.resourcesPath, "engine", "TennisHighlightAnalysis.exe");
    return { cmd: enginePath, args: [] };
  }
  return { cmd: "python", args: ["-m", "phase1.analyze"] };
}
function getProjectRoot() {
  if (electron.app.isPackaged) {
    return path.join(process.resourcesPath, "engine");
  }
  return path.resolve(path.join(__dirname, "../../.."));
}
function setupPythonBridge() {
  electron.ipcMain.handle("run-analysis", async (event, videoPath) => {
    if (analysisProcess) {
      return { error: "Analysis already running" };
    }
    const { cmd, args } = getEngineCommand();
    const fullArgs = [...args, videoPath, "--json-progress", "--no-vision"];
    const cwd = getProjectRoot();
    return new Promise((resolve) => {
      var _a, _b;
      analysisProcess = node_child_process.spawn(cmd, fullArgs, {
        cwd,
        stdio: ["ignore", "pipe", "pipe"]
      });
      const win2 = electron.BrowserWindow.fromWebContents(event.sender);
      (_a = analysisProcess.stdout) == null ? void 0 : _a.on("data", (data) => {
        const lines = data.toString().split("\n").filter(Boolean);
        for (const line of lines) {
          try {
            const msg = JSON.parse(line);
            win2 == null ? void 0 : win2.webContents.send("analysis-progress", msg);
            if (msg.type === "complete") {
              resolve({});
            }
            if (msg.type === "error") {
              resolve({ error: msg.message });
            }
          } catch {
          }
        }
      });
      (_b = analysisProcess.stderr) == null ? void 0 : _b.on("data", (data) => {
        console.error("[python]", data.toString());
      });
      analysisProcess.on("close", (code) => {
        analysisProcess = null;
        if (code !== 0) {
          resolve({ error: `Process exited with code ${code}` });
        }
      });
      analysisProcess.on("error", (err) => {
        analysisProcess = null;
        resolve({ error: err.message });
      });
    });
  });
  electron.ipcMain.handle("cancel-analysis", () => {
    if (analysisProcess) {
      analysisProcess.kill();
      analysisProcess = null;
    }
  });
  electron.ipcMain.handle("load-report", async (_event, videoPath) => {
    const stem = path.basename(videoPath, path.extname(videoPath));
    const dir = path.dirname(videoPath);
    const reportPath = path.join(dir, `output_${stem}`, "full_report.json");
    if (fs.existsSync(reportPath)) {
      return JSON.parse(fs.readFileSync(reportPath, "utf-8"));
    }
    return null;
  });
}
function setupFfmpegBridge() {
  electron.ipcMain.handle("export-highlights", async (event, videoPath, segments) => {
    const win2 = electron.BrowserWindow.fromWebContents(event.sender);
    const result = await electron.dialog.showSaveDialog({
      defaultPath: path.join(
        path.dirname(videoPath),
        `${path.basename(videoPath, path.extname(videoPath))}_highlights.mp4`
      ),
      filters: [{ name: "MP4", extensions: ["mp4"] }]
    });
    if (result.canceled || !result.filePath) return { cancelled: true };
    const outputPath = result.filePath;
    const sorted = [...segments].sort((a, b) => a.start - b.start);
    const inputs = [];
    const filterParts = [];
    for (let i = 0; i < sorted.length; i++) {
      const seg = sorted[i];
      inputs.push("-ss", String(seg.start), "-t", String(seg.end - seg.start), "-i", videoPath);
      filterParts.push(`[${i}:v][${i}:a]`);
    }
    const filterStr = filterParts.join("") + `concat=n=${sorted.length}:v=1:a=1[outv][outa]`;
    const cmd = ["ffmpeg", "-y", ...inputs, "-filter_complex", filterStr, "-map", "[outv]", "-map", "[outa]", outputPath];
    return new Promise((resolve) => {
      var _a;
      const proc = node_child_process.spawn(cmd[0], cmd.slice(1), { stdio: ["ignore", "pipe", "pipe"] });
      (_a = proc.stderr) == null ? void 0 : _a.on("data", (data) => {
        const line = data.toString();
        const match = line.match(/time=(\d+):(\d+):(\d+\.\d+)/);
        if (match) {
          const secs = parseInt(match[1]) * 3600 + parseInt(match[2]) * 60 + parseFloat(match[3]);
          win2 == null ? void 0 : win2.webContents.send("export-progress", { time: secs });
        }
      });
      proc.on("close", (code) => {
        if (code === 0) {
          resolve({ outputPath });
        } else {
          resolve({ error: `ffmpeg exited with code ${code}` });
        }
      });
      proc.on("error", (err) => {
        resolve({ error: err.message });
      });
    });
  });
}
const store = new Store({
  defaults: { recentProjects: [] }
});
process.env.DIST_ELECTRON = path.join(__dirname);
process.env.DIST = path.join(process.env.DIST_ELECTRON, "../dist");
process.env.VITE_PUBLIC = electron.app.isPackaged ? process.env.DIST : path.join(process.env.DIST_ELECTRON, "../../public");
let win = null;
const VITE_DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL;
function createWindow() {
  win = new electron.BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 600,
    webPreferences: {
      preload: path.join(__dirname, "../preload/preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: false
    },
    show: false
  });
  win.once("ready-to-show", () => win == null ? void 0 : win.show());
  if (VITE_DEV_SERVER_URL) {
    win.loadURL(VITE_DEV_SERVER_URL);
  } else {
    win.loadFile(path.join(process.env.DIST, "index.html"));
  }
}
electron.ipcMain.handle("open-file-dialog", async () => {
  const result = await electron.dialog.showOpenDialog({
    properties: ["openFile"],
    filters: [
      { name: "Video", extensions: ["mp4", "mkv", "avi", "mov"] }
    ]
  });
  if (result.canceled || result.filePaths.length === 0) return null;
  const filePath = result.filePaths[0];
  const recent = store.get("recentProjects");
  const updated = [filePath, ...recent.filter((p) => p !== filePath)].slice(0, 10);
  store.set("recentProjects", updated);
  return filePath;
});
electron.ipcMain.handle("get-recent-projects", () => {
  return store.get("recentProjects");
});
electron.app.whenReady().then(() => {
  setupPythonBridge();
  setupFfmpegBridge();
  createWindow();
});
electron.app.on("window-all-closed", () => {
  win = null;
  electron.app.quit();
});
