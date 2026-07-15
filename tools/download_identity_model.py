"""Download the official Apache-2.0 YOLOX-Nano ONNX model."""

import hashlib
import urllib.request
from pathlib import Path


MODEL_URL = (
    "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/"
    "0.1.1rc0/yolox_nano.onnx"
)
MODEL_SHA256 = "c789161ed43c8269fcd4e67c67eeb4e80c622da2eb296a20bc6007bd18a0b7d"
MODEL_PATH = Path(__file__).resolve().parent.parent / "engine" / "vision" / "models" / "yolox_nano.onnx"


def main():
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {MODEL_URL}")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    digest = hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()
    if digest != MODEL_SHA256:
        MODEL_PATH.unlink(missing_ok=True)
        raise RuntimeError(f"Model checksum mismatch: expected {MODEL_SHA256}, got {digest}")
    print(f"Saved verified model to {MODEL_PATH}")


if __name__ == "__main__":
    main()
