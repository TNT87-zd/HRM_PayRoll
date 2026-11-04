# Face recognition pipeline

`cv.face_engine.FaceEngine` is the public facade used by `services.face_service`.
Existing method signatures, the `InsightFaceEngine` alias, and public data types
and helpers imported from `cv.face_engine` remain available.

| Module | Responsibility |
| --- | --- |
| `types.py` | Data contracts and quality settings |
| `alignment.py` | Five-point alignment and pose estimates |
| `quality.py` | Blur, brightness, size, detection and pose checks |
| `onnx_backend.py` | SCRFD and ArcFace ONNX adapters |
| `model_store.py` | Model discovery and verified TLS downloads |
| `matching.py` | Embedding validation, normalization and matching |
| `enrollment.py` | Sample consistency and gallery construction |
| `face_engine.py` | Pipeline orchestration and compatibility facade |
| `webcam.py` | Optional OpenCV webcam demo |
| `cli.py` | Command-line demo |

Imports flow from the facade to the specialized modules. Enrollment receives
an engine rather than importing the facade. CLI and webcam execution are kept
outside the inference backend; the webcam module is loaded on demand.

From the repository root:

```sh
PYTHONPATH=app/backend/src .venv/bin/python -m cv.cli --help
.venv/bin/python app/backend/src/cv/face_engine.py --help
.venv/bin/python -m pytest app/backend/tests/test_face_engine.py -q
```

## Validation changes

Matching rejects non-finite, zero, empty and incorrectly shaped embeddings with
`ValueError`. Vectors must have 512 dimensions. Enrollment reports invalid
embeddings per sample and requires at least two valid samples for consistency.
The normal enrollment default remains three samples.

Enrollment keeps the existing mean similarity-to-centroid reporting field.
Acceptance now compares each sample with the normalized centroid of the other
samples and requires a connected group of pairwise matches at the configured
threshold. This prevents self-contribution from accepting unrelated samples or
separate identity groups. Thresholds still need evaluation on representative
images; these heuristics do not prove identity.

Direct model downloads retain TLS certificate verification on errors. Configure
a trusted CA or install `certifi` when certificate validation fails.

The regression suite uses synthetic embeddings and mocked downloads; it does
not require models, network access, camera access or employee data mutations.
