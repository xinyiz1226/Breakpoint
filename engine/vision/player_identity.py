# -*- coding: utf-8 -*-
#
# Copyright (C) 2026 Zhang Xinyi <xinyi.zhang@outlook.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import sys
from pathlib import Path

import cv2
import numpy as np


MODEL_NAME = "yolox_nano.onnx"
MODEL_INPUT_SIZE = 416
PLAYER_IDS = ("player_1", "player_2")


def _normalize_histogram(histogram: np.ndarray) -> np.ndarray:
    return cv2.normalize(
        histogram, histogram, alpha=1.0, norm_type=cv2.NORM_L1,
    ).flatten()


def default_model_path() -> Path:
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    bundled = bundle_root / "engine" / "vision" / "models" / MODEL_NAME
    if bundled.exists():
        return bundled
    return Path(__file__).resolve().parent / "models" / MODEL_NAME


class YoloXPersonDetector:
    """Run the Apache-2.0 YOLOX-Nano COCO person detector with OpenCV DNN."""

    def __init__(
        self,
        model_path: str | Path | None = None,
        confidence_threshold: float = 0.35,
        nms_threshold: float = 0.45,
    ):
        self.model_path = Path(model_path) if model_path else default_model_path()
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"YOLOX person detector not found: {self.model_path}. "
                "Run tools/download_identity_model.py before analysis."
            )
        self.net = cv2.dnn.readNetFromONNX(str(self.model_path))
        self.confidence_threshold = confidence_threshold
        self.nms_threshold = nms_threshold
        self._grid, self._expanded_strides = self._build_decode_grid()

    @staticmethod
    def _build_decode_grid():
        grids = []
        strides = []
        for stride in (8, 16, 32):
            height = MODEL_INPUT_SIZE // stride
            width = MODEL_INPUT_SIZE // stride
            grid_x, grid_y = np.meshgrid(np.arange(width), np.arange(height))
            grids.append(np.stack((grid_x, grid_y), axis=2).reshape(-1, 2))
            strides.append(np.full((height * width, 1), stride))
        return np.concatenate(grids), np.concatenate(strides)

    @staticmethod
    def _preprocess(frame: np.ndarray) -> tuple[np.ndarray, float]:
        height, width = frame.shape[:2]
        scale = min(MODEL_INPUT_SIZE / width, MODEL_INPUT_SIZE / height)
        resized_size = (int(width * scale), int(height * scale))
        resized = cv2.resize(frame, resized_size, interpolation=cv2.INTER_LINEAR)
        padded = np.full((MODEL_INPUT_SIZE, MODEL_INPUT_SIZE, 3), 114, dtype=np.uint8)
        padded[:resized_size[1], :resized_size[0]] = resized

        blob = cv2.dnn.blobFromImage(
            padded, scalefactor=1.0 / 255.0,
            size=(MODEL_INPUT_SIZE, MODEL_INPUT_SIZE), swapRB=True,
        )
        mean = np.asarray((0.485, 0.456, 0.406), dtype=np.float32).reshape(1, 3, 1, 1)
        std = np.asarray((0.229, 0.224, 0.225), dtype=np.float32).reshape(1, 3, 1, 1)
        return (blob - mean) / std, scale

    def detect(self, frame: np.ndarray) -> list[dict]:
        height, width = frame.shape[:2]
        blob, scale = self._preprocess(frame)
        self.net.setInput(blob)
        output = np.asarray(self.net.forward()).squeeze(0)
        if output.ndim != 2 or output.shape[0] != len(self._grid):
            raise RuntimeError(f"Unexpected YOLOX output shape: {output.shape}")

        decoded = output.copy()
        decoded[:, :2] = (decoded[:, :2] + self._grid) * self._expanded_strides
        decoded[:, 2:4] = np.exp(decoded[:, 2:4]) * self._expanded_strides
        scores = decoded[:, 4] * decoded[:, 5]  # objectness * COCO person probability
        candidate_indices = np.flatnonzero(scores >= self.confidence_threshold)

        boxes = []
        confidences = []
        for index in candidate_indices:
            center_x, center_y, box_width, box_height = decoded[index, :4] / scale
            x1 = max(0, int(center_x - box_width / 2))
            y1 = max(0, int(center_y - box_height / 2))
            x2 = min(width, int(center_x + box_width / 2))
            y2 = min(height, int(center_y + box_height / 2))
            if x2 > x1 and y2 > y1:
                boxes.append([x1, y1, x2 - x1, y2 - y1])
                confidences.append(float(scores[index]))

        if not boxes:
            return []

        kept = cv2.dnn.NMSBoxes(
            boxes, confidences, self.confidence_threshold, self.nms_threshold,
        )
        return [
            {
                "bbox": [
                    boxes[int(index)][0],
                    boxes[int(index)][1],
                    boxes[int(index)][0] + boxes[int(index)][2],
                    boxes[int(index)][1] + boxes[int(index)][3],
                ],
                "confidence": round(confidences[int(index)], 6),
            }
            for index in np.asarray(kept).reshape(-1)
        ]


def _appearance_descriptor(frame: np.ndarray, bbox: list[int]) -> np.ndarray | None:
    x1, y1, x2, y2 = bbox
    box_width = x2 - x1
    box_height = y2 - y1
    upper_body = frame[
        y1 + int(box_height * 0.08):y1 + int(box_height * 0.65),
        x1 + int(box_width * 0.15):x2 - int(box_width * 0.15),
    ]
    if upper_body.size == 0:
        return None
    hsv = cv2.cvtColor(upper_body, cv2.COLOR_BGR2HSV)
    histogram = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
    return _normalize_histogram(histogram)


def _court_side(bbox: list[int], rois: dict, frame_height: int) -> str | None:
    x1, _y1, x2, y2 = bbox
    foot = ((x1 + x2) / 2.0, float(y2))
    margin = frame_height * 0.08
    distances = {
        side: cv2.pointPolygonTest(np.asarray(rois[side], dtype=np.float32), foot, True)
        for side in ("near", "far")
    }
    side = max(distances, key=distances.get)
    return side if distances[side] >= -margin else None


def _summarize_observations(observations: list[dict], frame_shape: tuple[int, int]) -> dict | None:
    if not observations:
        return None
    descriptors = [item["descriptor"] for item in observations if item["descriptor"] is not None]
    descriptor = np.mean(descriptors, axis=0) if descriptors else None
    if descriptor is not None:
        descriptor = _normalize_histogram(descriptor)

    positions = np.asarray([item["position"] for item in observations], dtype=float)
    frame_height, frame_width = frame_shape
    diagonal = max(float(np.hypot(frame_width, frame_height)), 1.0)
    movement = (
        float(np.linalg.norm(np.diff(positions, axis=0), axis=1).sum() / diagonal)
        if len(positions) > 1 else 0.0
    )
    mean_position = positions.mean(axis=0)
    return {
        "side": observations[0]["side"],
        "descriptor": descriptor,
        "detection_confidence": float(np.mean([item["confidence"] for item in observations])),
        "movement_distance": movement,
        "sample_count": len(observations),
        "mean_position": [
            float(mean_position[0] / max(frame_width, 1)),
            float(mean_position[1] / max(frame_height, 1)),
        ],
    }


def _appearance_distance(descriptor: np.ndarray | None, prototype: np.ndarray | None) -> float:
    if descriptor is None or prototype is None:
        return 1.0
    return float(cv2.compareHist(
        descriptor.astype(np.float32),
        prototype.astype(np.float32),
        cv2.HISTCMP_BHATTACHARYYA,
    ))


def _assign_identities(observations: dict[str, dict | None], prototypes: dict[str, np.ndarray]) -> dict:
    available = [(side, value) for side, value in observations.items() if value is not None]
    if not available:
        return {}

    if prototypes and len(available) == 2:
        direct_cost = sum(
            _appearance_distance(available[i][1]["descriptor"], prototypes.get(PLAYER_IDS[i]))
            for i in range(2)
        )
        swapped_cost = sum(
            _appearance_distance(available[i][1]["descriptor"], prototypes.get(PLAYER_IDS[1 - i]))
            for i in range(2)
        )
        ids = PLAYER_IDS if direct_cost <= swapped_cost else tuple(reversed(PLAYER_IDS))
    elif prototypes:
        remaining = set(PLAYER_IDS)
        ids = []
        for _side, observation in available:
            player_id = min(
                remaining,
                key=lambda candidate: _appearance_distance(
                    observation["descriptor"], prototypes.get(candidate),
                ),
            )
            ids.append(player_id)
            remaining.remove(player_id)
    else:
        ids = tuple("player_1" if side == "near" else "player_2" for side, _ in available)

    assigned = {}
    for player_id, (_side, observation) in zip(ids, available):
        distance = _appearance_distance(observation["descriptor"], prototypes.get(player_id))
        assigned[player_id] = {
            **observation,
            "identity_confidence": 0.5 if player_id not in prototypes else max(0.0, 1.0 - distance),
        }
        descriptor = observation["descriptor"]
        if descriptor is not None:
            if player_id in prototypes:
                updated = prototypes[player_id] * 0.8 + descriptor * 0.2
                prototypes[player_id] = _normalize_histogram(updated)
            else:
                prototypes[player_id] = descriptor.copy()
    return assigned


def _public_player_data(observation: dict | None) -> dict:
    if observation is None:
        return {"detected": False}
    return {
        "detected": True,
        "side": observation["side"],
        "detection_confidence": round(observation["detection_confidence"], 4),
        "identity_confidence": round(observation["identity_confidence"], 4),
        "movement_distance": round(observation["movement_distance"], 6),
        "sample_count": observation["sample_count"],
        "mean_position": [round(value, 6) for value in observation["mean_position"]],
    }


def analyze_player_identities(
    video_path: str,
    segments: list[dict],
    rois: dict,
    model_path: str | Path | None = None,
    sample_seconds: float = 0.5,
    progress_callback=None,
    detector=None,
) -> list[dict]:
    """Detect two court players and maintain appearance-based IDs across side changes."""
    if not segments:
        return []
    detector = detector or YoloXPersonDetector(model_path)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video for player identity analysis: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    sample_interval = max(1, int(fps * sample_seconds))
    prototypes: dict[str, np.ndarray] = {}
    results = []

    try:
        for segment_index, segment in enumerate(segments):
            start_frame = max(0, int(segment["start"] * fps))
            end_frame = max(start_frame + 1, int(segment["end"] * fps))
            side_observations = {"near": [], "far": []}

            for frame_index in range(start_frame, end_frame, sample_interval):
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                read, frame = cap.read()
                if not read:
                    break
                best_by_side = {}
                for detection in detector.detect(frame):
                    side = _court_side(detection["bbox"], rois, frame_height)
                    if side is None:
                        continue
                    if side not in best_by_side or detection["confidence"] > best_by_side[side]["confidence"]:
                        best_by_side[side] = detection

                for side, detection in best_by_side.items():
                    x1, y1, x2, y2 = detection["bbox"]
                    side_observations[side].append({
                        "side": side,
                        "confidence": detection["confidence"],
                        "position": ((x1 + x2) / 2.0, float(y2)),
                        "descriptor": _appearance_descriptor(frame, detection["bbox"]),
                    })

            summarized = {
                side: _summarize_observations(items, (frame_height, frame_width))
                for side, items in side_observations.items()
            }
            assigned = _assign_identities(summarized, prototypes)
            results.append({
                "players": {
                    player_id: _public_player_data(assigned.get(player_id))
                    for player_id in PLAYER_IDS
                }
            })
            if progress_callback:
                progress_callback(segment_index + 1, len(segments))
    finally:
        cap.release()

    return results
