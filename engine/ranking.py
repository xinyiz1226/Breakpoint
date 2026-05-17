import numpy as np


def compute_features(point: dict, vision: dict | None = None) -> dict:
    hits = point["hit_times"]
    energies = point["hit_energies"]
    n = len(hits)

    if n < 2:
        intervals = [0]
    else:
        intervals = [hits[i] - hits[i - 1] for i in range(1, n)]

    features = {
        "hit_count": n,
        "avg_tempo": float(np.mean(intervals)) if intervals else 0,
        "max_intensity": float(np.max(energies)) if energies else 0,
        "tempo_variance": float(np.var(intervals)) if len(intervals) > 1 else 0,
        "duration": point["end"] - point["start"],
    }
    if vision:
        features["player_motion_max"] = vision.get("player_motion_max", 0.0)
        features["player_motion_var"] = vision.get("player_motion_var", 0.0)
    return features


def normalize(values: list[float]) -> list[float]:
    arr = np.array(values, dtype=float)
    rng = arr.max() - arr.min()
    if rng == 0:
        return [0.5] * len(values)
    return ((arr - arr.min()) / rng).tolist()


def rank_points(
    points: list[dict],
    weights: dict | None = None,
    vision_data: list[dict] | None = None,
) -> list[dict]:
    """Score and rank points. Returns points sorted by score descending."""
    if not points:
        return []

    if weights is None:
        weights = {"hit_count": 1.0, "inv_tempo": 1.0, "max_intensity": 1.0, "tempo_variance": 0.5}
        if vision_data:
            weights["player_motion_max"] = 1.0
            weights["player_motion_var"] = 0.5

    features = []
    for i, p in enumerate(points):
        v = vision_data[i] if vision_data else None
        features.append(compute_features(p, vision=v))

    hit_counts = normalize([f["hit_count"] for f in features])
    inv_tempos = normalize([1.0 / f["avg_tempo"] if f["avg_tempo"] > 0 else 0 for f in features])
    intensities = normalize([f["max_intensity"] for f in features])
    variances = normalize([f["tempo_variance"] for f in features])

    if vision_data:
        motion_maxes = normalize([f.get("player_motion_max", 0) for f in features])
        motion_vars = normalize([f.get("player_motion_var", 0) for f in features])

    ranked = []
    for i, p in enumerate(points):
        score = (
            weights["hit_count"] * hit_counts[i]
            + weights["inv_tempo"] * inv_tempos[i]
            + weights["max_intensity"] * intensities[i]
            + weights["tempo_variance"] * variances[i]
        )
        if vision_data:
            score += weights.get("player_motion_max", 0) * motion_maxes[i]
            score += weights.get("player_motion_var", 0) * motion_vars[i]
        ranked.append({
            **p,
            "features": features[i],
            "score": round(score, 4),
        })

    ranked.sort(key=lambda x: x["start"])
    return ranked
