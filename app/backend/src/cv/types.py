"""Data contracts and quality configuration for the face pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np


@dataclass
class FaceQualityConfig:
    """Cấu hình kiểm tra chất lượng khuôn mặt cho Kiosk và Enrollment."""

    min_det_score: float = 0.60
    min_face_size: int = 80  # Chiều rộng và chiều cao tối thiểu của bbox (px)
    min_blur_score: float = 35.0  # Phương sai Laplacian tối thiểu (chống ảnh mờ)
    min_brightness: float = 40.0  # Độ sáng trung bình tối thiểu (0..255)
    max_brightness: float = 225.0  # Độ sáng trung bình tối đa (chống cháy sáng)
    max_yaw_ratio: float = 0.68  # Độ lệch ngang tối đa của mũi so với 2 mắt
    max_pitch_ratio: float = 0.75  # Độ lệch dọc tối đa


@dataclass
class FaceQualityReport:
    """Báo cáo đánh giá chất lượng khuôn mặt trên một khung hình."""

    is_valid: bool
    num_faces: int
    det_score: float = 0.0
    face_width: int = 0
    face_height: int = 0
    blur_score: float = 0.0
    brightness: float = 0.0
    yaw_ratio: float = 0.0
    pitch_ratio: float = 0.0
    reasons: List[str] = field(default_factory=list)


@dataclass
class DetectedFace:
    """Thông tin một khuôn mặt phát hiện được trong ảnh."""

    bbox: np.ndarray  # shape (4,): [x1, y1, x2, y2]
    det_score: float
    kps: np.ndarray  # shape (5, 2): 5-point facial landmarks
    aligned_face: Optional[np.ndarray] = None  # shape (112, 112, 3) BGR
    embedding: Optional[np.ndarray] = None  # shape (512,) đã chuẩn hóa L2
    quality: Optional[FaceQualityReport] = None


@dataclass
class EnrollmentResult:
    """Kết quả đăng ký khuôn mặt (Enrollment) từ nhiều góc ảnh của 1 nhân viên."""

    success: bool
    employee_id: Optional[str]
    centroid_embedding: Optional[np.ndarray]  # Vector đại diện (512,) đã L2-normalize
    embeddings: List[np.ndarray]  # Danh sách vector hợp lệ từng ảnh
    valid_files: List[str]
    rejected_files: Dict[str, List[str]]  # {file_path: [reasons]}
    mean_intra_similarity: float = 0.0
    message: str = ""


@dataclass
class MatchResult:
    """Kết quả so khớp khuôn mặt với cơ sở dữ liệu nhân viên."""

    matched: bool
    employee_id: Optional[str]
    similarity: float
    second_best_employee_id: Optional[str]
    second_best_similarity: float
    margin: float
    threshold: float
    min_margin: float
    reason: str
