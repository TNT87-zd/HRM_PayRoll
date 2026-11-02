"""Shared configuration for enrollment, recognition and private storage."""
import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FACE_THRESHOLD, FACE_MIN_MARGIN = 0.55, 0.08
DUPLICATE_WINDOW_SEC, GEOFENCE_RADIUS_M = 60, 50
POSES = ("front", "left", "right", "up", "down")
CONSENT_VERSION = "face-attendance-v1"
MODEL_VERSION = "buffalo_l:w600k_r50:512-v1"
PREPROCESSING_VERSION = "arcface-112-rgb-l2:baseline-v1"


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("HRM_DATA_DIR", PROJECT_ROOT / "data")))
    storage_dir: Path = field(default_factory=lambda: Path(os.getenv("HRM_STORAGE_DIR", PROJECT_ROOT / "data/private")))
    database_url: str = field(default_factory=lambda: os.getenv("HRM_DB_URL", ""))
    landmark_model: Path = field(default_factory=lambda: PROJECT_ROOT / "models/mediapipe/face_landmarker.task")
    threshold: float = field(default_factory=lambda: float(os.getenv("HRM_FACE_THRESHOLD", FACE_THRESHOLD)))
    min_margin: float = field(default_factory=lambda: float(os.getenv("HRM_FACE_MIN_MARGIN", FACE_MIN_MARGIN)))
    session_ttl: int = 1800
    auth_ttl: int = 28800
    old_template_retention_days: int = 30
    max_image_bytes: int = 5 * 1024 * 1024
    max_image_pixels: int = 4_000_000
    secure_cookie: bool = field(default_factory=lambda: os.getenv("HRM_SECURE_COOKIE", "0") == "1")
    model_version: str = MODEL_VERSION
    preprocessing_version: str = PREPROCESSING_VERSION

    def __post_init__(self):
        self.data_dir, self.storage_dir = Path(self.data_dir), Path(self.storage_dir)
        self.landmark_model = Path(self.landmark_model)
        if not self.database_url:
            self.database_url = f"sqlite:///{self.storage_dir / 'hrm.sqlite3'}"


DB_URL = Settings().database_url
