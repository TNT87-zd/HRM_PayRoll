"""Five-point face alignment and landmark-based pose estimates."""

from __future__ import annotations

from typing import Tuple

import cv2
import numpy as np


# Tọa độ chuẩn 5 điểm mốc (mắt trái, mắt phải, mũi, khóe miệng trái, khóe miệng phải)
# của ArcFace cho ảnh căn chỉnh kích thước 112x112.
ARCFACE_SRC_KPS = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)


def align_face_5p(
    image: np.ndarray,
    kps: np.ndarray,
    image_size: int = 112,
) -> np.ndarray:
    """
    Căn chỉnh khuôn mặt về kích thước chuẩn (mặc định 112x112) từ 5 điểm mốc
    bằng phép biến đổi tương đồng 2D (Similarity Transform - tương đương `norm_crop` của InsightFace).
    """
    assert kps.shape == (5, 2), f"kps phải có shape (5, 2), nhận được {kps.shape}"
    ratio = float(image_size) / 112.0
    dst = ARCFACE_SRC_KPS * ratio

    matrix, _ = cv2.estimateAffinePartial2D(
        kps.astype(np.float32),
        dst,
        method=cv2.LMEDS,
    )
    if matrix is None:
        # Dự phòng nếu estimateAffinePartial2D thất bại: lấy 3 điểm đầu (2 mắt + mũi)
        matrix = cv2.getAffineTransform(kps[:3].astype(np.float32), dst[:3])

    aligned = cv2.warpAffine(
        image,
        matrix,
        (image_size, image_size),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    return np.asarray(aligned, dtype=np.uint8)


def estimate_pose_ratios(kps: np.ndarray) -> Tuple[float, float]:
    """
    Ước lượng độ lệch góc quay ngang (yaw_ratio) và góc gật dọc (pitch_ratio)
    tương đối từ 5 điểm mốc: [left_eye, right_eye, nose, left_mouth, right_mouth].
    Giá trị = 0 là nhìn chính diện; càng lớn là góc nghiêng càng mạnh.
    """
    pts = np.asarray(kps, dtype=np.float32)
    lx, ly = float(pts[0, 0]), float(pts[0, 1])
    rx, ry = float(pts[1, 0]), float(pts[1, 1])
    nx, ny = float(pts[2, 0]), float(pts[2, 1])
    mlx, mly = float(pts[3, 0]), float(pts[3, 1])
    mrx, mry = float(pts[4, 0]), float(pts[4, 1])

    eye_cx = 0.5 * (lx + rx)
    eye_cy = 0.5 * (ly + ry)
    mouth_cx = 0.5 * (mlx + mrx)
    mouth_cy = 0.5 * (mly + mry)

    eye_dist = max(float(np.hypot(rx - lx, ry - ly)), 1.0)
    eye_to_mouth = max(float(np.hypot(mouth_cx - eye_cx, mouth_cy - eye_cy)), 1.0)

    # Dùng mẫu số ổn định kết hợp eye_dist và eye_to_mouth để không bị suy biến khi quay ngang (profile)
    horiz_scale = max(0.5 * eye_dist, 0.35 * eye_to_mouth, 1.0)
    yaw_ratio = abs(nx - eye_cx) / horiz_scale

    # Tỷ lệ vị trí dọc của mũi giữa đường 2 mắt và đường miệng (chuẩn chính diện ~ 0.55)
    vert_scale = max(eye_to_mouth, 0.8 * eye_dist, 1.0)
    nose_rel_y = (ny - eye_cy) / vert_scale
    pitch_ratio = abs(nose_rel_y - 0.55) / 0.55

    return float(yaw_ratio), float(pitch_ratio)
