# -*- coding: utf-8 -*-
# 
# Copyright (C) 2026 Zhang Xinyi <xinyi.zhang@outlook.com>
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
# 
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
import numpy as np
import librosa
from scipy.signal import butter, sosfilt


def bandpass_filter(y: np.ndarray, sr: int, low: int = 200, high: int = 4000) -> np.ndarray:
    sos = butter(5, [low, high], btype="band", fs=sr, output="sos")
    return sosfilt(sos, y)


def detect_hits(
    audio_path: str,
    sr: int = 22050,
    bandpass_low: int = 200,
    bandpass_high: int = 4000,
    hop_length: int = 512,
    onset_threshold: float = 0.2,
    min_gap: float = 0.3,
    window_sec: float = 60.0,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Detect ball hit times from audio file using windowed onset detection.

    Returns (hit_times, hit_energies, sr).
    """
    y, sr = librosa.load(audio_path, sr=sr)
    y_filtered = bandpass_filter(y, sr, bandpass_low, bandpass_high)

    window_samples = int(window_sec * sr)
    all_times = []
    all_energies = []

    for start in range(0, len(y_filtered), window_samples):
        chunk = y_filtered[start:start + window_samples]
        if len(chunk) < sr:
            continue
        offset = start / sr

        onset_env = librosa.onset.onset_strength(y=chunk, sr=sr, hop_length=hop_length)
        onsets = librosa.onset.onset_detect(
            onset_envelope=onset_env, sr=sr,
            hop_length=hop_length, backtrack=False,
            delta=onset_threshold, units="frames",
        )
        if len(onsets) == 0:
            continue

        times = librosa.frames_to_time(onsets, sr=sr, hop_length=hop_length) + offset
        energies = onset_env[onsets]
        all_times.append(times)
        all_energies.append(energies)

    if not all_times:
        return np.array([]), np.array([]), sr

    onset_times = np.concatenate(all_times)
    onset_energies = np.concatenate(all_energies)

    # Sort by time
    order = np.argsort(onset_times)
    onset_times = onset_times[order]
    onset_energies = onset_energies[order]

    # Merge onsets closer than min_gap
    if len(onset_times) > 1:
        keep = [0]
        for i in range(1, len(onset_times)):
            if onset_times[i] - onset_times[keep[-1]] >= min_gap:
                keep.append(i)
            elif onset_energies[i] > onset_energies[keep[-1]]:
                keep[-1] = i
        onset_times = onset_times[keep]
        onset_energies = onset_energies[keep]

    return onset_times, onset_energies, sr


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python detect_hits.py <audio_path>")
        sys.exit(1)
    times, energies, sr = detect_hits(sys.argv[1])
    print(f"Detected {len(times)} hits")
    for t, e in zip(times[:20], energies[:20]):
        print(f"  {t:7.2f}s  energy={e:.2f}")
