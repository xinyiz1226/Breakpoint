import sys
import os
import subprocess
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))

from flask import Flask, request, jsonify, render_template, Response
from extract_audio import extract_audio
from detect_hits import detect_hits
from segment_points import segment_points
from rank_points import rank_points

app = Flask(__name__)

TEMP_DIR = Path(__file__).resolve().parent / "static" / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/pick-file", methods=["POST"])
def pick_file():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askopenfilename(
        title="选择视频文件",
        filetypes=[("视频文件", "*.mp4 *.mkv *.avi *.mov *.MP4 *.MKV *.AVI *.MOV"), ("所有文件", "*.*")],
    )
    root.destroy()
    if not path:
        return jsonify({"path": ""})
    return jsonify({"path": path})


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    video_path = data.get("video_path", "")
    if not video_path or not Path(video_path).exists():
        return jsonify({"error": "Video file not found"}), 400

    duration_str = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path],
        capture_output=True, text=True,
    ).stdout
    duration = float(json.loads(duration_str)["format"]["duration"])

    audio_path = str(TEMP_DIR / "audio.wav")
    extract_audio(video_path, audio_path)

    hit_times, hit_energies, sr = detect_hits(audio_path)
    points = segment_points(hit_times, hit_energies, total_duration=duration)
    ranked = rank_points(points)

    # Sort by time for display
    ranked_by_time = sorted(ranked, key=lambda x: x["start"])
    segments = []
    for i, p in enumerate(ranked_by_time):
        segments.append({
            "id": i,
            "start": p["start"],
            "end": p["end"],
            "score": p["score"],
            "hit_count": p["features"]["hit_count"],
            "duration": round(p["end"] - p["start"], 2),
        })

    return jsonify({"segments": segments, "video_path": video_path, "duration": duration})


@app.route("/video")
def serve_video():
    video_path = request.args.get("path", "")
    if not video_path or not Path(video_path).exists():
        return "Not found", 404

    file_size = os.path.getsize(video_path)
    range_header = request.headers.get("Range")

    if range_header:
        byte_start = int(range_header.replace("bytes=", "").split("-")[0])
        byte_end = min(byte_start + 5 * 1024 * 1024, file_size - 1)
        content_length = byte_end - byte_start + 1

        def generate():
            with open(video_path, "rb") as f:
                f.seek(byte_start)
                remaining = content_length
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return Response(
            generate(),
            status=206,
            mimetype="video/mp4",
            headers={
                "Content-Range": f"bytes {byte_start}-{byte_end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": content_length,
            },
        )

    def generate_full():
        with open(video_path, "rb") as f:
            while chunk := f.read(65536):
                yield chunk

    return Response(
        generate_full(),
        mimetype="video/mp4",
        headers={"Accept-Ranges": "bytes", "Content-Length": file_size},
    )


@app.route("/export", methods=["POST"])
def export_video():
    data = request.get_json()
    video_path = data.get("video_path", "")
    clips = data.get("clips", [])

    if not video_path or not clips:
        return jsonify({"error": "Missing video_path or clips"}), 400

    timestamp = int(time.time())
    output_path = str(TEMP_DIR / f"highlights_{timestamp}.mp4")

    clips_sorted = sorted(clips, key=lambda x: x["start"])

    filter_parts = []
    inputs = []
    for i, clip in enumerate(clips_sorted):
        inputs.extend(["-ss", str(clip["start"]), "-t", str(clip["end"] - clip["start"]), "-i", video_path])
        filter_parts.append(f"[{i}:v][{i}:a]")

    filter_str = "".join(filter_parts) + f"concat=n={len(clips_sorted)}:v=1:a=1[outv][outa]"

    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filter_str,
        "-map", "[outv]", "-map", "[outa]",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return jsonify({"error": result.stderr}), 500

    return jsonify({"output_path": output_path})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
