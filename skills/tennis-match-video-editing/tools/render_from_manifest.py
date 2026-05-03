#!/usr/bin/env python3
"""Render tennis highlight video from a manifest JSON using ffmpeg.

This script implements the automatic path for the tennis-match-video-editing skill:
1) Read keep clips from manifest
2) Cut each keep clip from source
3) Concatenate all keep clips into final mp4
4) Emit an edit log with source/output and resolution checks
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List


class RenderError(RuntimeError):
    pass


@dataclass
class Clip:
    clip_id: str
    start: str
    end: str
    action: str
    reason: str
    tags: List[str]


def run_cmd(cmd: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def require_bin(name: str) -> None:
    if shutil.which(name) is None:
        raise RenderError(f"Required binary not found: {name}")


def ffprobe_resolution(source: Path) -> tuple[int, int]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        str(source),
    ]
    result = run_cmd(cmd)
    if result.returncode != 0:
        raise RenderError(f"ffprobe failed for source resolution: {result.stderr.strip()}")

    payload = json.loads(result.stdout)
    streams = payload.get("streams", [])
    if not streams:
        raise RenderError("No video stream found in source file")

    width = streams[0].get("width")
    height = streams[0].get("height")
    if not isinstance(width, int) or not isinstance(height, int):
        raise RenderError("Invalid resolution from ffprobe")

    return width, height


def default_output_path(source: Path) -> Path:
    return source.with_name(f"{source.stem}_highlights.mp4")


def parse_manifest(path: Path) -> tuple[Path, Path, List[Clip]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RenderError(f"Failed to parse manifest json: {exc}") from exc

    source = Path(payload.get("source", "")).expanduser()
    output_raw = payload.get("output")

    if not source.exists():
        raise RenderError(f"Source video not found: {source}")
    output = Path(output_raw).expanduser() if output_raw else default_output_path(source)
    if source == output:
        raise RenderError("Source and output cannot be the same path")

    clips_raw = payload.get("clips", [])
    if not isinstance(clips_raw, list) or not clips_raw:
        raise RenderError("Manifest must contain non-empty 'clips' array")

    clips: List[Clip] = []
    for item in clips_raw:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action", "")).lower().strip()
        if action != "keep":
            continue

        clip_id = str(item.get("id", "")).strip() or f"clip_{len(clips)+1:03d}"
        start = str(item.get("start", "")).strip()
        end = str(item.get("end", "")).strip()
        reason = str(item.get("reason", "")).strip()
        tags = item.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        if not start or not end:
            raise RenderError(f"Clip {clip_id} missing start/end")

        clips.append(Clip(clip_id=clip_id, start=start, end=end, action=action, reason=reason, tags=[str(t) for t in tags]))

    if not clips:
        raise RenderError("No keep clips found in manifest")

    return source, output, clips


_CHECKLIST_LINE_RE = re.compile(
    r"^\s*-\s*\[(?P<chk>[ xX])\]\s*"
    r"(?P<id>\S+)\s*\|\s*"
    r"(?P<start>\d{2}:\d{2}:\d{2}\.\d{3})\s*(?:->|→|=>)\s*"
    r"(?P<end>\d{2}:\d{2}:\d{2}\.\d{3})"
    r"(?P<rest>.*)$"
)


def parse_checklist_md(path: Path) -> tuple[Path, Path, List[Clip]]:
    text = path.read_text(encoding="utf-8")
    source: Path | None = None
    output: Path | None = None
    for line in text.splitlines():
        m_src = re.match(r"\s*-\s*Source:\s*`?([^`]+?)`?\s*$", line)
        if m_src and source is None:
            source = Path(m_src.group(1)).expanduser()
            continue
        m_out = re.match(r"\s*-\s*Output:\s*`?([^`]+?)`?\s*$", line)
        if m_out and output is None:
            output = Path(m_out.group(1)).expanduser()
            continue

    if source is None or not source.exists():
        raise RenderError(f"Checklist missing valid `- Source:` line or source not found: {source}")
    if output is None:
        output = default_output_path(source)
    if source == output:
        raise RenderError("Source and output cannot be the same path")

    clips: List[Clip] = []
    total = 0
    for line in text.splitlines():
        m = _CHECKLIST_LINE_RE.match(line)
        if not m:
            continue
        total += 1
        if m.group("chk").lower() != "x":
            continue
        rest = m.group("rest").strip(" |")
        clips.append(
            Clip(
                clip_id=m.group("id"),
                start=m.group("start"),
                end=m.group("end"),
                action="keep",
                reason=rest,
                tags=["CHECKLIST"],
            )
        )

    if total == 0:
        raise RenderError("Checklist contains no candidate lines")
    if not clips:
        raise RenderError("No clips checked in checklist; tick at least one `- [x]` entry")

    return source, output, clips


def load_clips(path: Path) -> tuple[Path, Path, List[Clip]]:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return parse_checklist_md(path)
    return parse_manifest(path)


def cut_clip(source: Path, target: Path, clip: Clip, width: int, height: int, crf: int, preset: str) -> None:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        clip.start,
        "-to",
        clip.end,
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-vf",
        f"scale={width}:{height}",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(target),
    ]
    result = run_cmd(cmd)
    if result.returncode != 0:
        raise RenderError(f"Failed to cut {clip.clip_id}: {result.stderr.strip()}")


def concat_clips(parts: List[Path], output: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="tennis_concat_") as tmpdir:
        concat_file = Path(tmpdir) / "concat.txt"
        lines = [f"file '{p.as_posix()}'" for p in parts]
        concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(output),
        ]
        result = run_cmd(cmd)
        if result.returncode != 0:
            raise RenderError(f"Failed to concatenate clips: {result.stderr.strip()}")


def write_log(log_path: Path, source: Path, output: Path, width: int, height: int, clips: List[Clip]) -> None:
    lines = [
        "# Edit Log",
        "",
        f"- Source: {source}",
        f"- Output: {output}",
        f"- Resolution lock: {width}x{height}",
        f"- Keep clips count: {len(clips)}",
        "",
        "## Kept Clips",
    ]
    for clip in clips:
        tags = ", ".join(clip.tags) if clip.tags else "-"
        lines.append(f"- {clip.clip_id} | {clip.start}-{clip.end} | {clip.reason or '-'} | {tags}")

    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render highlight video from manifest json or markdown checklist")
    parser.add_argument("manifest", type=Path, help="Path to manifest .json or candidates .md (checklist)")
    parser.add_argument("--log", type=Path, default=None, help="Optional output edit-log path")
    parser.add_argument("--crf", type=int, default=18, help="Video quality crf (default: 18)")
    parser.add_argument("--preset", type=str, default="medium", help="x264 preset (default: medium)")
    args = parser.parse_args()

    try:
        require_bin("ffmpeg")
        require_bin("ffprobe")
        source, output, clips = load_clips(args.manifest)

        output.parent.mkdir(parents=True, exist_ok=True)
        width, height = ffprobe_resolution(source)

        with tempfile.TemporaryDirectory(prefix="tennis_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            parts: List[Path] = []
            for idx, clip in enumerate(clips, start=1):
                part = tmp_root / f"part_{idx:04d}.mp4"
                cut_clip(source=source, target=part, clip=clip, width=width, height=height, crf=args.crf, preset=args.preset)
                parts.append(part)

            concat_clips(parts=parts, output=output)

        # Validate resolution lock after render.
        out_w, out_h = ffprobe_resolution(output)
        if (out_w, out_h) != (width, height):
            raise RenderError(
                f"Resolution mismatch after render: source={width}x{height}, output={out_w}x{out_h}"
            )

        log_path = args.log or output.with_suffix(".edit-log.md")
        write_log(log_path=log_path, source=source, output=output, width=width, height=height, clips=clips)

        print(f"Render complete: {output}")
        print(f"Edit log: {log_path}")
        return 0
    except RenderError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
