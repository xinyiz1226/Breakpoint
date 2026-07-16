import numpy as np

from engine.vision import player_identity as identity


def _observation(side, descriptor):
    return {
        "side": side,
        "descriptor": np.asarray(descriptor, dtype=np.float32),
        "detection_confidence": 0.9,
        "movement_distance": 0.1,
        "sample_count": 4,
        "mean_position": [0.5, 0.5],
    }


def test_identity_follows_appearance_when_players_switch_sides():
    prototypes = {}
    first = identity._assign_identities({
        "near": _observation("near", [1.0, 0.0]),
        "far": _observation("far", [0.0, 1.0]),
    }, prototypes)

    assert first["player_1"]["side"] == "near"
    assert first["player_2"]["side"] == "far"

    second = identity._assign_identities({
        "near": _observation("near", [0.0, 1.0]),
        "far": _observation("far", [1.0, 0.0]),
    }, prototypes)

    assert second["player_1"]["side"] == "far"
    assert second["player_2"]["side"] == "near"


def test_two_observations_use_global_match_with_one_existing_prototype():
    prototypes = {"player_1": np.asarray([1.0, 0.0], dtype=np.float32)}
    assigned = identity._assign_identities({
        "near": _observation("near", [0.0, 1.0]),
        "far": _observation("far", [1.0, 0.0]),
    }, prototypes)

    assert assigned["player_1"]["side"] == "far"
    assert assigned["player_2"]["side"] == "near"


def test_public_player_data_does_not_expose_appearance_descriptor():
    public = identity._public_player_data({
        **_observation("near", [1.0, 0.0]),
        "identity_confidence": 0.8,
    })

    assert public["detected"] is True
    assert public["side"] == "near"
    assert "descriptor" not in public


def test_bundled_yolox_model_loads():
    detector = identity.YoloXPersonDetector()
    assert detector.model_path.name == identity.MODEL_NAME


def test_yolox_preprocessing_uses_official_mean_and_std():
    white = np.full((416, 416, 3), 255, dtype=np.uint8)
    blob, scale = identity.YoloXPersonDetector._preprocess(white)

    assert scale == 1.0
    expected = (1.0 - np.asarray([0.485, 0.456, 0.406])) / np.asarray([0.229, 0.224, 0.225])
    np.testing.assert_allclose(blob[0, :, 0, 0], expected, rtol=1e-6)
