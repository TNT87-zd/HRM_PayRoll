"""Download pinned public MediaPipe assets with normal TLS verification.

Run from the repository root: .venv/bin/python app/backend/scripts/setup_face_assets.py
The frontend and backend use the same FaceLandmarker model (float16, version 1).
"""
import hashlib
import io
import json
from pathlib import Path
import ssl
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
VISION_VERSION = "1.2.0"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
PACKAGE_URL = f"https://registry.npmjs.org/@mediapipe/tasks-vision/-/tasks-vision-{VISION_VERSION}.tgz"


def download(url):
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    with urllib.request.urlopen(url, context=context, timeout=90) as response:
        return response.read()


def main():
    target = ROOT / "app/frontend/vendor/mediapipe"
    model = ROOT / "models/mediapipe/face_landmarker.task"
    target.mkdir(parents=True, exist_ok=True)
    model.parent.mkdir(parents=True, exist_ok=True)
    assets = {}
    with tarfile.open(fileobj=io.BytesIO(download(PACKAGE_URL)), mode="r:gz") as package:
        for member in package.getmembers():
            relative = member.name.removeprefix("package/")
            if relative == "vision_bundle.mjs" or (relative.startswith("wasm/") and relative.endswith((".wasm", ".js"))) or relative == "LICENSE":
                if not member.isfile() or ".." in Path(relative).parts:
                    continue
                content = package.extractfile(member).read()
                path = target / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                assets[relative] = hashlib.sha256(content).hexdigest()
    if not (target / "vision_bundle.mjs").is_file():
        raise RuntimeError("MediaPipe package does not contain vision_bundle.mjs")
    model.write_bytes(download(MODEL_URL))
    assets["face_landmarker.task"] = hashlib.sha256(model.read_bytes()).hexdigest()
    (target / "manifest.json").write_text(json.dumps({"version": VISION_VERSION, "sha256": assets}, indent=2) + "\n")
    print(f"Installed MediaPipe Web {VISION_VERSION}: {len(assets)} assets; model {model.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
