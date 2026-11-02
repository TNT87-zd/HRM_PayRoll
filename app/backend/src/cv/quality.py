"""Image quality checks independent of model inference."""

from __future__ import annotations

from typing import List, Optional

import cv2
import numpy as np

from .alignment import estimate_pose_ratios
from .types import DetectedFace, FaceQualityConfig, FaceQualityReport


def assess_face_quality(
    image: np.ndarray,
    face: DetectedFace,
    num_faces_in_frame: int = 1,
    config: Optional[FaceQualityConfig] = None,
    require_single_face: bool = True,
    allow_pose_variation: bool = False,
) -> FaceQualityReport:
    """
    Đánh giá chất lượng ảnh khuôn mặt theo các tiêu chí ở mục 4.1 (PLAN.MD):
    - Đúng 1 khuôn mặt trong khung hình (nếu `require_single_face=True`).
    - Điểm tin cậy phát hiện mặt >= `min_det_score`.
    - Kích thước mặt >= `min_face_size`.
    - Không bị quá mờ (Laplacian variance >= `min_blur_score`).
    - Không bị quá tối hoặc cháy sáng (`min_brightness` <= brightness <= `max_brightness`).
    - Góc mặt trong ngưỡng cho phép (có thể nới lỏng khi đăng ký các góc nghiêng bằng `allow_pose_variation=True`).
    """
    cfg = config or FaceQualityConfig()
    reasons: List[str] = []

    if num_faces_in_frame == 0:
        return FaceQualityReport(
            is_valid=False,
            num_faces=0,
            reasons=["no_face"],
        )

    if require_single_face and num_faces_in_frame > 1:
        reasons.append("multiple_faces")

    x1 = int(face.bbox[0])
    y1 = int(face.bbox[1])
    x2 = int(face.bbox[2])
    y2 = int(face.bbox[3])
    h_img, w_img = image.shape[:2]
    x1 = max(0, min(x1, w_img - 1))
    y1 = max(0, min(y1, h_img - 1))
    x2 = max(x1 + 1, min(x2, w_img))
    y2 = max(y1 + 1, min(y2, h_img))

    face_w = int(x2 - x1)
    face_h = int(y2 - y1)

    if face.det_score < (cfg.min_det_score * (0.75 if allow_pose_variation else 1.0)):
        reasons.append("low_det_score")

    if face_w < cfg.min_face_size or face_h < cfg.min_face_size:
        reasons.append("face_too_small")

    # Ưu tiên đo độ nét trên vùng cắt gốc (raw bbox crop) để tránh bị làm mờ bởi nội suy warpAffine
    raw_crop = image[y1:y2, x1:x2]
    if raw_crop.size > 0:
        raw_gray = np.asarray(
            cv2.cvtColor(raw_crop, cv2.COLOR_BGR2GRAY) if raw_crop.ndim == 3 else raw_crop,
            dtype=np.uint8,
        )
        lap_raw = np.asarray(cv2.Laplacian(raw_gray, cv2.CV_64F), dtype=np.float64)
        blur_raw = float(lap_raw.var())
        brightness = float(raw_gray.mean())
    else:
        blur_raw = 0.0
        brightness = 0.0

    if face.aligned_face is not None and face.aligned_face.size > 0:
        aligned_gray = np.asarray(
            cv2.cvtColor(face.aligned_face, cv2.COLOR_BGR2GRAY)
            if face.aligned_face.ndim == 3
            else face.aligned_face,
            dtype=np.uint8,
        )
        lap_aligned = np.asarray(cv2.Laplacian(aligned_gray, cv2.CV_64F), dtype=np.float64)
        blur_aligned = float(lap_aligned.var())
        if raw_crop.size == 0:
            brightness = float(aligned_gray.mean())
    else:
        blur_aligned = 0.0

    blur_score = max(blur_raw, blur_aligned)

    if blur_score < cfg.min_blur_score:
        reasons.append("too_blurry")

    if brightness < cfg.min_brightness:
        reasons.append("too_dark")
    elif brightness > cfg.max_brightness:
        reasons.append("too_bright")

    yaw_ratio, pitch_ratio = estimate_pose_ratios(face.kps)
    pose_scale = 2.5 if allow_pose_variation else 1.0
    max_yaw = cfg.max_yaw_ratio * pose_scale
    max_pitch = cfg.max_pitch_ratio * pose_scale

    if yaw_ratio > max_yaw or pitch_ratio > max_pitch:
        reasons.append("extreme_pose")

    return FaceQualityReport(
        is_valid=(len(reasons) == 0),
        num_faces=num_faces_in_frame,
        det_score=float(face.det_score),
        face_width=face_w,
        face_height=face_h,
        blur_score=blur_score,
        brightness=brightness,
        yaw_ratio=yaw_ratio,
        pitch_ratio=pitch_ratio,
        reasons=reasons,
    )
