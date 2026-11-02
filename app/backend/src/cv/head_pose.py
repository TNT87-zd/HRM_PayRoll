"""Independent server-side head pose validation using the shared landmark model."""
from dataclasses import dataclass
import math
from pathlib import Path
import threading
import cv2
import numpy as np


@dataclass
class Pose:
    yaw: float
    pitch: float
    roll: float


def angles_from_matrix(matrix):
    rotation = np.asarray(matrix, dtype=float).reshape(4, 4)[:3, :3]
    # The facial matrix can include scale. Recover its nearest proper rotation.
    u, _, vt = np.linalg.svd(rotation)
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        u[:, -1] *= -1
        rotation = u @ vt
    yaw = math.degrees(math.atan2(-rotation[2, 0], math.hypot(rotation[0, 0], rotation[1, 0])))
    pitch = math.degrees(math.atan2(rotation[2, 1], rotation[2, 2]))
    roll = math.degrees(math.atan2(rotation[1, 0], rotation[0, 0]))
    return Pose(yaw=yaw, pitch=pitch, roll=roll)


def relative_pose(pose, baseline):
    return Pose(**{key: getattr(pose, key) - baseline.get(key, 0) for key in ("yaw", "pitch", "roll")})


def classify_pose(pose):
    """Subject-relative directions for unmirrored MediaPipe input."""
    if abs(pose.roll) > 12:
        return None
    if abs(pose.yaw) <= 10 and abs(pose.pitch) <= 10:
        return "front"
    if abs(pose.pitch) <= 12 and 15 <= abs(pose.yaw) <= 32:
        return "left" if pose.yaw > 0 else "right"
    if abs(pose.yaw) <= 12 and 10 <= abs(pose.pitch) <= 22:
        # MediaPipe's positive pitch looks down; negative pitch looks up.
        return "down" if pose.pitch > 0 else "up"
    return None


class PoseEstimator:
    def __init__(self, model_path):
        self.model_path = Path(model_path)
        self.landmarker = None
        self.lock = threading.RLock()

    def startup(self):
        if not self.model_path.is_file():
            raise RuntimeError("Thiếu model hướng mặt. Chạy scripts/setup_face_assets.py")
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode
        self.mp = mp
        self.landmarker = FaceLandmarker.create_from_options(FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(self.model_path), delegate=BaseOptions.Delegate.CPU),
            running_mode=RunningMode.IMAGE, num_faces=2,
            output_facial_transformation_matrixes=True,
            min_face_detection_confidence=0.6, min_face_presence_confidence=0.6,
        ))

    def analyze(self, image):
        with self.lock:
            if self.landmarker is None:
                self.startup()
            rgb = np.ascontiguousarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            result = self.landmarker.detect(self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb))
            if len(result.face_landmarks) != 1:
                raise ValueError("multiple_faces" if result.face_landmarks else "no_face")
            points = result.face_landmarks[0]
            if any(p.x < 0.005 or p.x > 0.995 or p.y < 0.005 or p.y > 0.995 for p in points):
                raise ValueError("face_clipped")
            return angles_from_matrix(result.facial_transformation_matrixes[0])

    def close(self):
        if self.landmarker is not None:
            self.landmarker.close()
            self.landmarker = None
