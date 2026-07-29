from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.services.media_subprocess import run_capture_process, run_json_progress_process


@dataclass(frozen=True)
class MediaProbe:
    duration_seconds: float
    container: str
    video_codec: str | None
    audio_codec: str | None

    @property
    def browser_compatible(self) -> bool:
        containers = {value.strip() for value in self.container.split(",")}
        return (
            bool(containers.intersection({"mp4", "mov", "m4a", "3gp", "3g2", "mj2"}))
            and self.video_codec == "h264"
            and self.audio_codec in (None, "aac")
        )


class RealMediaTools:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _run(self, command, *, cancelled, progress) -> str:
        return run_json_progress_process(
            command,
            cancelled=cancelled,
            progress=progress,
            stderr_max_chars=self.settings.job_stderr_max_chars,
            progress_line_max_chars=self.settings.job_progress_line_max_chars,
        )

    def probe(self, source: Path, *, cancelled=None) -> MediaProbe:
        stdout, _stderr = run_capture_process(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,format_name:stream=codec_type,codec_name",
                "-of",
                "json",
                str(source),
            ],
            cancelled=cancelled or (lambda: False),
            timeout_seconds=60,
            stderr_max_chars=self.settings.job_stderr_max_chars,
        )
        payload = json.loads(stdout)
        streams = payload.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
        return MediaProbe(
            duration_seconds=float(payload["format"]["duration"]),
            container=str(payload["format"].get("format_name", "")),
            video_codec=video.get("codec_name"),
            audio_codec=audio.get("codec_name"),
        )

    def create_preview_proxy(self, source: Path, output: Path, *, cancelled, progress) -> None:
        self._run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-movflags",
                "+faststart",
                "-c:a",
                "aac",
                str(output),
            ],
            cancelled=cancelled,
            progress=progress,
        )

    def analyze(self, source: Path, output_dir: Path, *, cancelled, progress) -> Path:
        self._run(
            [
                sys.executable,
                "-m",
                "engine.pipeline",
                str(source),
                "-o",
                str(output_dir),
                "--json-progress",
            ],
            cancelled=cancelled,
            progress=progress,
        )
        return output_dir / "full_report.json"

    def export(self, source: Path, selections, output: Path, *, cancelled, progress) -> None:
        has_audio = self.probe(source).audio_codec is not None
        inputs: list[str] = []
        filter_inputs: list[str] = []
        for index, selection in enumerate(selections):
            inputs.extend(
                [
                    "-ss",
                    str(selection["start"]),
                    "-t",
                    str(selection["end"] - selection["start"]),
                    "-i",
                    str(source),
                ]
            )
            filter_inputs.append(
                f"[{index}:v][{index}:a]" if has_audio else f"[{index}:v]"
            )
        filter_graph = "".join(filter_inputs) + (
            f"concat=n={len(selections)}:v=1:a=1[outv][outa]"
            if has_audio
            else f"concat=n={len(selections)}:v=1:a=0[outv]"
        )
        command = [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            filter_graph,
            "-map",
            "[outv]",
        ]
        if has_audio:
            command.extend(["-map", "[outa]"])
        command.extend(
            [
                "-c:v",
                "libx264",
                *(["-c:a", "aac"] if has_audio else []),
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
        self._run(
            command,
            cancelled=cancelled,
            progress=progress,
        )


class FakeMediaTools:
    """Deterministic no-ffmpeg/no-engine toolchain for tests and smoke setups."""

    def probe(self, source: Path, *, cancelled=None) -> MediaProbe:
        return MediaProbe(
            duration_seconds=60.0,
            container="mp4",
            video_codec="h264",
            audio_codec="aac",
        )

    def create_preview_proxy(self, source: Path, output: Path, *, cancelled, progress) -> None:
        if cancelled():
            from app.services.media_subprocess import JobCancelled

            raise JobCancelled()
        output.write_bytes(source.read_bytes())

    def analyze(self, source: Path, output_dir: Path, *, cancelled, progress) -> Path:
        if cancelled():
            from app.services.media_subprocess import JobCancelled

            raise JobCancelled()
        progress({"type": "step", "step": 1, "total": 1, "label": "Fake analysis"})
        report = output_dir / "full_report.json"
        report.write_text("[]", encoding="utf-8")
        return report

    def export(self, source: Path, selections, output: Path, *, cancelled, progress) -> None:
        if cancelled():
            from app.services.media_subprocess import JobCancelled

            raise JobCancelled()
        progress({"progress": 0.9, "label": "Fake export"})
        output.write_bytes(source.read_bytes())
