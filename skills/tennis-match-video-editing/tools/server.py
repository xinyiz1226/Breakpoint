#!/usr/bin/env python3
"""Local backend for the tennis clip workflow.

Serves the SPA page and exposes JSON APIs that delegate analysis and rendering
to the existing tools (generate_manifest_draft.py / render_from_manifest.py).

Security: binds to 127.0.0.1 only. All file paths are resolved and must live
under --root (default: $HOME). Range requests are honored so the browser <video>
can preview the source without uploading.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT_DIR.parent.parent.parent  # AgentCollection/
TOOLS_DIR = ROOT_DIR
PAGE_FILE = TOOLS_DIR / "clip_app.html"
GENERATE_SCRIPT = TOOLS_DIR / "generate_manifest_draft.py"
RENDER_SCRIPT = TOOLS_DIR / "render_from_manifest.py"

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
AUDIO_EXTS = {".m4a", ".aac", ".mp3", ".wav", ".flac", ".ogg"}

# ------------------------------------------------------------------ Globals
SERVED_ROOT: Path = Path.home()
PYTHON_BIN: str = sys.executable
JOBS: dict[str, "Job"] = {}
JOBS_LOCK = threading.Lock()


# ------------------------------------------------------------------ Helpers
def safe_path(raw: str) -> Path:
    """Resolve a user-supplied path and ensure it lives under SERVED_ROOT."""
    p = Path(os.path.expanduser(raw)).resolve()
    try:
        p.relative_to(SERVED_ROOT)
    except ValueError:
        raise PermissionError(f"Path is outside served root: {p}")
    return p


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler: BaseHTTPRequestHandler, status: int, text: str, ctype="text/plain; charset=utf-8") -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


# ------------------------------------------------------------------ Jobs
class Job:
    def __init__(self, kind: str):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.state = "pending"  # pending | running | done | error | cancelled
        self.progress: float = 0.0
        self.message: str = ""
        self.result: dict | None = None
        self.error: str | None = None
        self.proc: subprocess.Popen | None = None
        self.cancel = threading.Event()
        self.created = time.time()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "state": self.state,
            "progress": round(self.progress, 4),
            "message": self.message,
            "result": self.result,
            "error": self.error,
        }


def register_job(job: Job) -> None:
    with JOBS_LOCK:
        JOBS[job.id] = job


def get_job(jid: str) -> Job | None:
    with JOBS_LOCK:
        return JOBS.get(jid)


# ------------------------------------------------------------------ Analysis
def run_analyze(job: Job, video_path: Path, audio_path: Path | None, params: dict) -> None:
    job.state = "running"
    job.message = "Preparing…"
    try:
        with tempfile.TemporaryDirectory(prefix="tennis_analyze_") as tmp:
            tmp_dir = Path(tmp)
            manifest_path = tmp_dir / "manifest.json"
            signal_csv = tmp_dir / "signal.csv"

            source_for_audio = audio_path or video_path
            cmd = [
                PYTHON_BIN, str(GENERATE_SCRIPT), str(source_for_audio),
                "--manifest", str(manifest_path),
                "--signal-csv", str(signal_csv),
                "--no-checklist",
                "--keep-count", "0",
                "--max-candidates", str(int(params.get("max_candidates", 200))),
                "--pre-pad", str(float(params.get("pre_pad", 2.5))),
                "--post-pad", str(float(params.get("post_pad", 4.0))),
                "--rally-min-hits", str(int(params.get("min_hits", 3))),
                "--rally-min-interval", str(float(params.get("min_interval", 0.45))),
                "--rally-max-interval", str(float(params.get("max_interval", 2.5))),
                "--onset-threshold-ratio", str(float(params.get("thr_ratio", 4.0))),
                "--onset-min-separation-ms", str(float(params.get("min_sep_ms", 120.0))),
                "--high-freq-hz", str(float(params.get("hp_hz", 2500.0))),
            ]
            job.message = f"Running analyzer on {source_for_audio.name}…"
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            job.proc = proc
            stderr_lines: list[str] = []
            assert proc.stderr is not None
            for line in proc.stderr:
                stderr_lines.append(line.rstrip())
                low = line.lower()
                if "extracting" in low: job.progress = 0.15
                elif "detecting onsets" in low: job.progress = 0.45
                elif "rally sequences" in low: job.progress = 0.75
                job.message = line.rstrip()[:200]
                if job.cancel.is_set():
                    proc.kill()
            proc.wait()
            if job.cancel.is_set():
                job.state = "cancelled"; job.message = "Cancelled"
                return
            if proc.returncode != 0:
                job.state = "error"
                job.error = "\n".join(stderr_lines[-20:]) or f"exit={proc.returncode}"
                return

            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            clips = []
            for i, c in enumerate(payload.get("clips", [])):
                clips.append({
                    "id": c.get("id") or f"AUTO-{i+1:03d}",
                    "start": c["start"],
                    "end": c["end"],
                    "reason": c.get("reason", ""),
                    "tags": c.get("tags", []),
                    "keep": False,
                })
            job.result = {
                "video_path": str(video_path),
                "audio_path": str(audio_path) if audio_path else None,
                "clips": clips,
            }
            job.progress = 1.0
            job.state = "done"
            job.message = f"{len(clips)} candidates"
    except Exception as exc:  # noqa: BLE001
        job.state = "error"
        job.error = f"{type(exc).__name__}: {exc}"


# ------------------------------------------------------------------ Render
_FFMPEG_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")


def run_render(job: Job, video_path: Path, clips: list[dict], output_path: Path,
               crf: int, preset: str) -> None:
    job.state = "running"
    job.message = "Preparing render…"
    try:
        if not clips:
            raise RuntimeError("No clips to render")
        with tempfile.TemporaryDirectory(prefix="tennis_render_") as tmp:
            tmp_dir = Path(tmp)
            manifest_path = tmp_dir / "manifest.json"
            manifest_clips = []
            total_seconds = 0.0
            for i, c in enumerate(clips, start=1):
                start = c["start"]; end = c["end"]
                manifest_clips.append({
                    "id": c.get("id") or f"CLIP-{i:03d}",
                    "start": start, "end": end,
                    "action": "keep",
                    "reason": c.get("reason", ""),
                    "tags": c.get("tags", []) or ["FRONTEND"],
                })
                total_seconds += max(0.0, _ts_to_sec(end) - _ts_to_sec(start))
            payload = {
                "source": str(video_path),
                "output": str(output_path),
                "clips": manifest_clips,
            }
            manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

            cmd = [
                PYTHON_BIN, str(RENDER_SCRIPT), str(manifest_path),
                "--crf", str(crf), "--preset", preset,
            ]
            job.message = f"Rendering {len(manifest_clips)} clips → {output_path.name}"
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            job.proc = proc

            # render_from_manifest doesn't print fine progress; estimate by time.
            t0 = time.time()
            assert proc.stderr is not None and proc.stdout is not None
            stderr_buf: list[str] = []

            def pump_stderr():
                for line in proc.stderr:
                    stderr_buf.append(line.rstrip())
                    job.message = line.rstrip()[:200]
                    m = _FFMPEG_TIME_RE.search(line)
                    if m and total_seconds > 0:
                        cur = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
                        # Each clip resets ffmpeg timer; we cannot get global progress,
                        # so just rotate a heuristic.
                        job.progress = min(0.95, 0.05 + (time.time() - t0) / max(total_seconds, 1.0) * 0.5)
                    if job.cancel.is_set():
                        proc.kill()
                        return

            t = threading.Thread(target=pump_stderr, daemon=True)
            t.start()
            for _ in proc.stdout:
                pass
            proc.wait()
            t.join(timeout=2)
            if job.cancel.is_set():
                job.state = "cancelled"; job.message = "Cancelled"
                try: output_path.unlink(missing_ok=True)
                except Exception: pass
                return
            if proc.returncode != 0:
                job.state = "error"
                job.error = "\n".join(stderr_buf[-30:]) or f"exit={proc.returncode}"
                return
            job.progress = 1.0
            job.state = "done"
            job.result = {"output": str(output_path)}
            job.message = f"Wrote {output_path.name}"
    except Exception as exc:  # noqa: BLE001
        job.state = "error"
        job.error = f"{type(exc).__name__}: {exc}"


def _ts_to_sec(ts: str) -> float:
    m = re.match(r"^(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?$", ts.strip())
    if not m:
        return 0.0
    ms = int((m.group(4) or "0").ljust(3, "0")[:3])
    return int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + ms / 1000.0


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "TennisEditor/1"

    # Quieter logging
    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    # ---------- routing ----------
    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        path = url.path
        qs = parse_qs(url.query)
        try:
            if path == "/" or path == "/index.html":
                return self.serve_page()
            if path == "/api/info":
                return json_response(self, 200, {
                    "root": str(SERVED_ROOT),
                    "python": PYTHON_BIN,
                })
            if path == "/api/browse":
                return self.api_browse(qs.get("dir", [""])[0])
            if path == "/api/job":
                return self.api_job(qs.get("id", [""])[0])
            if path == "/file":
                return self.serve_file(qs.get("path", [""])[0])
            return text_response(self, 404, "Not found")
        except PermissionError as e:
            return json_response(self, 403, {"error": str(e)})
        except FileNotFoundError as e:
            return json_response(self, 404, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            self.log_error("GET %s failed: %s", path, e)
            return json_response(self, 500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):  # noqa: N802
        url = urlparse(self.path)
        path = url.path
        try:
            if path == "/api/analyze":
                return self.api_analyze()
            if path == "/api/render":
                return self.api_render()
            if path == "/api/cancel":
                return self.api_cancel()
            return text_response(self, 404, "Not found")
        except PermissionError as e:
            return json_response(self, 403, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            self.log_error("POST %s failed: %s", path, e)
            return json_response(self, 500, {"error": f"{type(e).__name__}: {e}"})

    # ---------- handlers ----------
    def serve_page(self):
        if not PAGE_FILE.exists():
            return text_response(self, 500, f"Page not found: {PAGE_FILE}")
        body = PAGE_FILE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def api_browse(self, raw_dir: str):
        target = SERVED_ROOT if not raw_dir else safe_path(raw_dir)
        if not target.exists() or not target.is_dir():
            raise FileNotFoundError(f"Not a directory: {target}")
        entries = []
        for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if child.name.startswith("."):
                continue
            try:
                size = child.stat().st_size if child.is_file() else None
            except Exception:
                size = None
            ext = child.suffix.lower()
            entries.append({
                "name": child.name,
                "path": str(child),
                "is_dir": child.is_dir(),
                "size": size,
                "kind": ("video" if ext in VIDEO_EXTS else "audio" if ext in AUDIO_EXTS else "other"),
            })
        parent = target.parent if target != SERVED_ROOT else None
        return json_response(self, 200, {
            "cwd": str(target),
            "parent": str(parent) if parent else None,
            "entries": entries,
        })

    def api_analyze(self):
        body = read_json_body(self)
        video = safe_path(body["video_path"])
        audio = safe_path(body["audio_path"]) if body.get("audio_path") else None
        params = body.get("params") or {}
        if not video.is_file():
            raise FileNotFoundError(f"Video not found: {video}")
        if audio and not audio.is_file():
            raise FileNotFoundError(f"Audio not found: {audio}")
        job = Job("analyze")
        register_job(job)
        threading.Thread(target=run_analyze, args=(job, video, audio, params), daemon=True).start()
        return json_response(self, 200, {"job": job.to_dict()})

    def api_render(self):
        body = read_json_body(self)
        video = safe_path(body["video_path"])
        clips = body.get("clips") or []
        crf = int(body.get("crf", 18))
        preset = str(body.get("preset", "medium"))
        if body.get("output_path"):
            out = safe_path(body["output_path"])
        else:
            out = video.with_name(f"{video.stem}_highlights.mp4")
            safe_path(str(out))  # validate root
        if out == video:
            raise PermissionError("output cannot equal source")
        job = Job("render")
        register_job(job)
        threading.Thread(target=run_render, args=(job, video, clips, out, crf, preset), daemon=True).start()
        return json_response(self, 200, {"job": job.to_dict(), "output_path": str(out)})

    def api_cancel(self):
        body = read_json_body(self)
        job = get_job(body.get("id", ""))
        if not job:
            return json_response(self, 404, {"error": "job not found"})
        job.cancel.set()
        if job.proc and job.proc.poll() is None:
            try: job.proc.kill()
            except Exception: pass
        return json_response(self, 200, {"job": job.to_dict()})

    def api_job(self, jid: str):
        job = get_job(jid)
        if not job:
            return json_response(self, 404, {"error": "job not found"})
        return json_response(self, 200, {"job": job.to_dict()})

    # ---------- range-aware static file serve ----------
    def serve_file(self, raw_path: str):
        if not raw_path:
            raise FileNotFoundError("path query missing")
        target = safe_path(unquote(raw_path))
        if not target.is_file():
            raise FileNotFoundError(f"Not a file: {target}")
        size = target.stat().st_size
        ctype, _ = mimetypes.guess_type(str(target))
        ctype = ctype or "application/octet-stream"

        rng = self.headers.get("Range")
        start = 0
        end = size - 1
        status = 200
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng.strip())
            if m:
                if m.group(1):
                    start = int(m.group(1))
                if m.group(2):
                    end = int(m.group(2))
                else:
                    end = size - 1
                if start >= size or end >= size or start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "private, max-age=0")
        self.end_headers()
        with target.open("rb") as f:
            f.seek(start)
            remaining = length
            chunk_size = 1024 * 1024
            while remaining > 0:
                buf = f.read(min(chunk_size, remaining))
                if not buf:
                    break
                try:
                    self.wfile.write(buf)
                except (BrokenPipeError, ConnectionResetError):
                    return
                remaining -= len(buf)


# ------------------------------------------------------------------ Entry
def main() -> int:
    global SERVED_ROOT, PYTHON_BIN
    p = argparse.ArgumentParser(description="Tennis clip workflow backend")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--root", type=Path, default=Path.home(),
                   help="Filesystem root that the server is allowed to read")
    p.add_argument("--python", default=sys.executable,
                   help="Python interpreter to invoke for analyze/render scripts")
    args = p.parse_args()

    SERVED_ROOT = args.root.expanduser().resolve()
    PYTHON_BIN = args.python
    if not SERVED_ROOT.is_dir():
        print(f"--root does not exist: {SERVED_ROOT}", file=sys.stderr)
        return 2
    if not GENERATE_SCRIPT.exists() or not RENDER_SCRIPT.exists() or not PAGE_FILE.exists():
        print("Required tool/page files missing next to server.py", file=sys.stderr)
        return 2

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Tennis editor backend ready: {url}")
    print(f"Serving files under: {SERVED_ROOT}")
    print(f"Python for tools:     {PYTHON_BIN}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down…")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
