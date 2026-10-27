"""
Wrapper InsightFace (SCRFD + ArcFace) chạy trên ONNX Runtime.

Phục vụ Phân hệ Nhận diện Khuôn mặt & Kiosk Chấm công (Mục 4.1 - PLAN.MD):
- Phát hiện khuôn mặt + 5 điểm mốc (5-point landmarks) bằng SCRFD.
- Căn chỉnh khuôn mặt chuẩn 112x112 (similarity transform / norm_crop).
- Kiểm tra chất lượng ảnh khuôn mặt (đúng 1 mặt, kích thước tối thiểu, độ mờ, độ sáng, góc nghiêng).
- Trích xuất vector đặc trưng 512 chiều bằng ArcFace và chuẩn hóa L2.
- Đăng ký khuôn mặt (Enrollment) từ 3-5 góc chụp (ví dụ: front, left, right, up, under).
- So khớp (Verification / 1:N Matching) bằng Cosine Similarity kèm điều kiện ngưỡng
  `threshold` và khoảng cách tối thiểu giữa điểm khớp nhất - khớp nhì (`min_margin`).

Hỗ trợ 2 chế độ nạp model linh hoạt:
1. Chạy thuần `onnxruntime.InferenceSession` trực tiếp từ file `.onnx` của SCRFD và ArcFace
   (không phụ thuộc bắt buộc vào Cython build của gói `insightface`).
2. Tự động tìm hoặc tải gói model (`buffalo_l`, `buffalo_s`, `buffalo_sc`) thông qua
   `insightface.app.FaceAnalysis` nếu chưa có sẵn file `.onnx` cục bộ.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import os
import ssl
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np

try:
    import onnxruntime as ort
except ImportError as exc:  # pragma: no cover
    ort = None  # type: ignore[assignment]
    _ORT_IMPORT_ERROR: Optional[ImportError] = exc
else:
    _ORT_IMPORT_ERROR = None

logger = logging.getLogger(__name__)

# Đường dẫn thư mục gốc của ứng dụng HRM_PayRoll (app/backend/src/cv -> HRM_PayRoll)
_PROJECT_ROOT = Path(__file__).resolve().parents[4]

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


# ============================================================================
# 1. CẤU TRÚC DỮ LIỆU ĐẦU RA (DATACLASSES)
# ============================================================================


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


# ============================================================================
# 2. CÁC HÀM TIỆN ÍCH: CĂN CHỈNH MẶT, CHẤT LƯỢNG ẢNH & COSINE SIMILARITY
# ============================================================================


def l2_normalize(vec: np.ndarray, axis: int = -1, eps: float = 1e-12) -> np.ndarray:
    """Chuẩn hóa vector hoặc ma trận vector theo chuẩn L2."""
    arr = np.asarray(vec, dtype=np.float32)
    norm = np.linalg.norm(arr, axis=axis, keepdims=True)
    return arr / np.maximum(norm, eps)


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """Tính Cosine Similarity giữa 2 vector 1D (trong khoảng [-1, 1])."""
    a = l2_normalize(vec_a.reshape(-1))
    b = l2_normalize(vec_b.reshape(-1))
    return float(np.dot(a, b))


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


# ============================================================================
# 3. PURE ONNX RUNTIME SCRFD DETECTOR & ARCFACE RECOGNIZER
# ============================================================================


def _nms_boxes(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> List[int]:
    """Non-Maximum Suppression (NMS) chuẩn trên numpy."""
    if boxes.size == 0:
        return []

    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = np.maximum(0.0, x2 - x1 + 1.0) * np.maximum(0.0, y2 - y1 + 1.0)
    order = scores.argsort()[::-1]

    keep: List[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break

        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w = np.maximum(0.0, xx2 - xx1 + 1.0)
        h = np.maximum(0.0, yy2 - yy1 + 1.0)
        inter = w * h
        ovr = inter / np.maximum(areas[i] + areas[order[1:]] - inter, 1e-12)

        inds = np.where(ovr <= iou_threshold)[0]
        order = order[inds + 1]

    return keep


class SCRFDOnnxDetector:
    """
    Bộ phát hiện khuôn mặt & 5 điểm mốc SCRFD chạy trực tiếp trên `onnxruntime.InferenceSession`.
    Tương thích với các file `det_10g.onnx`, `det_2.5g.onnx`, `det_500m.onnx` của InsightFace.
    """

    def __init__(
        self,
        model_path: Union[str, Path],
        input_size: Tuple[int, int] = (640, 640),
        det_thresh: float = 0.5,
        nms_thresh: float = 0.4,
        providers: Optional[Sequence[str]] = None,
        session_options: Optional[Any] = None,
    ) -> None:
        if ort is None:  # pragma: no cover
            raise ImportError(
                "Cần cài đặt `onnxruntime` để chạy SCRFDOnnxDetector."
            ) from _ORT_IMPORT_ERROR

        self.model_path = str(model_path)
        self.input_size = (int(input_size[0]), int(input_size[1]))  # (width, height)
        self.det_thresh = float(det_thresh)
        self.nms_thresh = float(nms_thresh)

        self.session = ort.InferenceSession(
            self.model_path,
            sess_options=session_options,
            providers=list(providers) if providers else ort.get_available_providers(),
        )

        input_meta = self.session.get_inputs()[0]
        self.input_name: str = input_meta.name
        input_shape = input_meta.shape
        if (
            len(input_shape) == 4
            and isinstance(input_shape[2], int)
            and isinstance(input_shape[3], int)
        ):
            self.input_size = (int(input_shape[3]), int(input_shape[2]))

        outputs = self.session.get_outputs()
        self.output_names: List[str] = [o.name for o in outputs]
        self._center_cache: Dict[Tuple[int, int, int], np.ndarray] = {}

        # Cấu hình kiến trúc đầu ra của SCRFD (6, 9, 10 hoặc 15 nhánh)
        num_outputs = len(outputs)
        if num_outputs == 6:
            self.fmc = 3
            self.feat_stride_fpn = [8, 16, 32]
            self.num_anchors = 2
            self.use_kps = False
        elif num_outputs == 9:
            self.fmc = 3
            self.feat_stride_fpn = [8, 16, 32]
            self.num_anchors = 2
            self.use_kps = True
        elif num_outputs == 10:
            self.fmc = 5
            self.feat_stride_fpn = [8, 16, 32, 64, 128]
            self.num_anchors = 1
            self.use_kps = False
        elif num_outputs == 15:
            self.fmc = 5
            self.feat_stride_fpn = [8, 16, 32, 64, 128]
            self.num_anchors = 1
            self.use_kps = True
        else:
            raise ValueError(
                f"Model SCRFD '{self.model_path}' có số lượng output không hợp lệ: {num_outputs}."
            )

    @staticmethod
    def _distance2bbox(points: np.ndarray, distance: np.ndarray) -> np.ndarray:
        x1 = points[:, 0] - distance[:, 0]
        y1 = points[:, 1] - distance[:, 1]
        x2 = points[:, 0] + distance[:, 2]
        y2 = points[:, 1] + distance[:, 3]
        return np.stack([x1, y1, x2, y2], axis=-1)

    @staticmethod
    def _distance2kps(points: np.ndarray, distance: np.ndarray) -> np.ndarray:
        preds = []
        for i in range(0, distance.shape[1], 2):
            px = points[:, i % 2] + distance[:, i]
            py = points[:, i % 2 + 1] + distance[:, i + 1]
            preds.append(px)
            preds.append(py)
        return np.stack(preds, axis=-1)

    def detect(
        self,
        image: np.ndarray,
        det_thresh: Optional[float] = None,
        max_num: int = 0,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Phát hiện khuôn mặt trong ảnh BGR.
        Trả về:
        - `det`: shape `(N, 5)` gồm `[x1, y1, x2, y2, score]`
        - `kpss`: shape `(N, 5, 2)` gồm tọa độ 5 điểm mốc
        """
        thresh = float(det_thresh if det_thresh is not None else self.det_thresh)
        input_w, input_h = self.input_size
        im_h, im_w = image.shape[:2]

        # Letterbox resize giữ nguyên tỷ lệ khung hình giống chuẩn SCRFD của InsightFace
        im_ratio = float(im_h) / float(im_w)
        model_ratio = float(input_h) / float(input_w)
        if im_ratio > model_ratio:
            new_h = input_h
            new_w = int(new_h / im_ratio)
        else:
            new_w = input_w
            new_h = int(new_w * im_ratio)

        det_scale = float(new_h) / float(im_h)
        resized_img = cv2.resize(image, (new_w, new_h))
        det_img = np.zeros((input_h, input_w, 3), dtype=np.uint8)
        det_img[:new_h, :new_w, :] = resized_img

        blob = cv2.dnn.blobFromImage(
            det_img,
            scalefactor=1.0 / 128.0,
            size=(input_w, input_h),
            mean=(127.5, 127.5, 127.5),
            swapRB=True,
        )

        net_outs = self.session.run(self.output_names, {self.input_name: blob})

        scores_list: List[np.ndarray] = []
        bboxes_list: List[np.ndarray] = []
        kpss_list: List[np.ndarray] = []

        for idx, stride in enumerate(self.feat_stride_fpn):
            scores = np.asarray(net_outs[idx], dtype=np.float32).reshape(-1)
            bbox_preds = (
                np.asarray(net_outs[idx + self.fmc], dtype=np.float32) * stride
            ).reshape(-1, 4)
            kps_preds: Optional[np.ndarray] = None
            if self.use_kps:
                kps_preds = (
                    np.asarray(net_outs[idx + self.fmc * 2], dtype=np.float32) * stride
                ).reshape(-1, 10)

            feat_h = input_h // stride
            feat_w = input_w // stride
            cache_key = (feat_h, feat_w, stride)

            if cache_key in self._center_cache:
                anchor_centers = self._center_cache[cache_key]
            else:
                grid_x, grid_y = np.meshgrid(
                    np.arange(feat_w, dtype=np.float32),
                    np.arange(feat_h, dtype=np.float32),
                )
                anchor_centers = np.stack([grid_x, grid_y], axis=-1).astype(np.float32)
                anchor_centers = (anchor_centers * stride).reshape((-1, 2))
                if self.num_anchors > 1:
                    anchor_centers = np.stack(
                        [anchor_centers] * self.num_anchors,
                        axis=1,
                    ).reshape((-1, 2))
                if len(self._center_cache) < 100:
                    self._center_cache[cache_key] = anchor_centers

            pos_inds = np.where(scores >= thresh)[0]
            if pos_inds.size == 0:
                continue

            pos_scores = scores[pos_inds]
            pos_anchors = anchor_centers[pos_inds]
            pos_bbox_preds = bbox_preds[pos_inds]

            bboxes = self._distance2bbox(pos_anchors, pos_bbox_preds)
            scores_list.append(pos_scores)
            bboxes_list.append(bboxes)
            if self.use_kps and kps_preds is not None:
                pos_kps_preds = kps_preds[pos_inds]
                kpss = self._distance2kps(pos_anchors, pos_kps_preds)
                kpss = kpss.reshape((kpss.shape[0], -1, 2))
                kpss_list.append(kpss)

        if not scores_list:
            return (
                np.empty((0, 5), dtype=np.float32),
                np.empty((0, 5, 2), dtype=np.float32),
            )

        scores_all = np.concatenate(scores_list, axis=0)
        bboxes_all = np.concatenate(bboxes_list, axis=0) / det_scale
        if self.use_kps and kpss_list:
            kpss_all = np.concatenate(kpss_list, axis=0) / det_scale
        else:
            kpss_all = np.zeros((bboxes_all.shape[0], 5, 2), dtype=np.float32)

        keep = _nms_boxes(bboxes_all, scores_all, self.nms_thresh)
        det = np.hstack([bboxes_all[keep], scores_all[keep, None]]).astype(np.float32)
        kpss_out = kpss_all[keep].astype(np.float32)

        # Sắp xếp ưu tiên mặt lớn & ở gần trung tâm nếu giới hạn max_num
        if max_num > 0 and det.shape[0] > max_num:
            area = (det[:, 2] - det[:, 0]) * (det[:, 3] - det[:, 1])
            img_center = (im_w / 2.0, im_h / 2.0)
            offsets = np.vstack(
                [
                    (det[:, 0] + det[:, 2]) / 2.0 - img_center[0],
                    (det[:, 1] + det[:, 3]) / 2.0 - img_center[1],
                ]
            )
            offset_dist_squared = np.sum(np.power(offsets, 2.0), axis=0)
            values = area - offset_dist_squared * 2.0
            bindex = np.argsort(values)[::-1][:max_num]
            det = det[bindex]
            kpss_out = kpss_out[bindex]

        return det, kpss_out


class ArcFaceOnnxRecognizer:
    """
    Bộ trích xuất đặc trưng khuôn mặt 512 chiều ArcFace chạy trực tiếp trên `onnxruntime.InferenceSession`.
    Tương thích với `w600k_r50.onnx`, `w600k_mbf.onnx`, `glintr100.onnx` của InsightFace.
    """

    def __init__(
        self,
        model_path: Union[str, Path],
        input_size: Tuple[int, int] = (112, 112),
        providers: Optional[Sequence[str]] = None,
        session_options: Optional[Any] = None,
    ) -> None:
        if ort is None:  # pragma: no cover
            raise ImportError(
                "Cần cài đặt `onnxruntime` để chạy ArcFaceOnnxRecognizer."
            ) from _ORT_IMPORT_ERROR

        self.model_path = str(model_path)
        self.input_size = (int(input_size[0]), int(input_size[1]))
        self.session = ort.InferenceSession(
            self.model_path,
            sess_options=session_options,
            providers=list(providers) if providers else ort.get_available_providers(),
        )
        self.input_name: str = self.session.get_inputs()[0].name
        self.output_names: List[str] = [o.name for o in self.session.get_outputs()]

    def get_embedding(self, aligned_bgr: np.ndarray) -> np.ndarray:
        """
        Trích xuất vector đặc trưng 512 chiều đã chuẩn hóa L2 từ ảnh mặt BGR 112x112.
        """
        embeddings = self.get_embeddings_batch([aligned_bgr])
        return embeddings[0]

    def get_embeddings_batch(self, aligned_bgr_list: Sequence[np.ndarray]) -> np.ndarray:
        """
        Trích xuất batch vector đặc trưng `(N, 512)` đã chuẩn hóa L2 từ danh sách ảnh mặt BGR 112x112.
        """
        if not aligned_bgr_list:
            return np.empty((0, 512), dtype=np.float32)

        blob = cv2.dnn.blobFromImages(
            list(aligned_bgr_list),
            scalefactor=1.0 / 127.5,
            size=self.input_size,
            mean=(127.5, 127.5, 127.5),
            swapRB=True,
        )
        raw_out = np.asarray(
            self.session.run(self.output_names, {self.input_name: blob})[0],
            dtype=np.float32,
        )
        return l2_normalize(raw_out, axis=1)


# ============================================================================
# 4. UNIFIED INSIGHTFACE (SCRFD + ARCFACE) WRAPPER
# ============================================================================


class FaceEngine:
    """
    Wrapper thống nhất cho pipeline InsightFace (SCRFD + ArcFace) chạy ONNX Runtime.

    Cách khởi tạo:
    - Nếu truyền `det_model_path` và `rec_model_path` (hoặc đã có sẵn trong `~/.insightface/models/<model_pack>/`):
      sử dụng trực tiếp `SCRFDOnnxDetector` + `ArcFaceOnnxRecognizer` trên `onnxruntime.InferenceSession`.
    - Nếu chưa có file `.onnx` tại chỗ, tự động gọi `insightface.app.FaceAnalysis` để tải gói model
      (`buffalo_l` hoặc `buffalo_s`), sau đó nạp qua ONNX Runtime.
    """

    # Cặp tên file model chuẩn trong các gói của InsightFace
    KNOWN_PACK_FILES: Dict[str, Tuple[str, str]] = {
        "buffalo_l": ("det_10g.onnx", "w600k_r50.onnx"),
        "buffalo_s": ("det_500m.onnx", "w600k_mbf.onnx"),
        "buffalo_sc": ("det_500m.onnx", "w600k_mbf.onnx"),
    }

    def __init__(
        self,
        model_pack: str = "buffalo_l",
        model_root: Optional[Union[str, Path]] = None,
        det_model_path: Optional[Union[str, Path]] = None,
        rec_model_path: Optional[Union[str, Path]] = None,
        det_size: Tuple[int, int] = (640, 640),
        det_thresh: float = 0.50,
        nms_thresh: float = 0.40,
        providers: Optional[Sequence[str]] = None,
        intra_op_num_threads: int = 4,
        quality_config: Optional[FaceQualityConfig] = None,
        auto_download: bool = True,
    ) -> None:
        if ort is None:  # pragma: no cover
            raise ImportError(
                "Chưa cài đặt `onnxruntime`. Vui lòng chạy: pip install onnxruntime opencv-python numpy"
            ) from _ORT_IMPORT_ERROR

        self.model_pack = model_pack
        if model_root is not None:
            self.model_root = Path(model_root).expanduser()
        elif "INSIGHTFACE_ROOT" in os.environ:
            self.model_root = Path(os.environ["INSIGHTFACE_ROOT"]).expanduser()
        else:
            # Ưu tiên thư mục models ngay trong dự án; nếu ~/.insightface đã có sẵn model thì tái sử dụng
            project_model_root = _PROJECT_ROOT / "models" / "insightface"
            home_model_root = Path.home() / ".insightface"
            if (home_model_root / "models" / model_pack).is_dir() and not (
                project_model_root / "models" / model_pack
            ).is_dir():
                self.model_root = home_model_root
            else:
                self.model_root = project_model_root
        self.det_size = det_size
        self.det_thresh = det_thresh
        self.nms_thresh = nms_thresh
        self.quality_config = quality_config or FaceQualityConfig(
            min_det_score=max(0.50, det_thresh)
        )

        # Thiết lập ONNX Runtime Execution Providers & SessionOptions tối ưu CPU/RAM
        available = ort.get_available_providers()
        if providers is None:
            preferred = ["CUDAExecutionProvider", "CoreMLExecutionProvider", "CPUExecutionProvider"]
            resolved_providers = [p for p in preferred if p in available]
            if not resolved_providers:
                resolved_providers = ["CPUExecutionProvider"]
        else:
            resolved_providers = [p for p in providers if p in available] or ["CPUExecutionProvider"]
        self.providers: List[str] = resolved_providers

        self.session_options = ort.SessionOptions()
        self.session_options.graph_optimization_level = (
            ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        )
        if intra_op_num_threads > 0:
            self.session_options.intra_op_num_threads = int(intra_op_num_threads)

        det_path, rec_path = self._resolve_onnx_paths(
            det_model_path=det_model_path,
            rec_model_path=rec_model_path,
            auto_download=auto_download,
        )
        self.det_model_path = det_path
        self.rec_model_path = rec_path

        self.detector = SCRFDOnnxDetector(
            model_path=det_path,
            input_size=det_size,
            det_thresh=det_thresh,
            nms_thresh=nms_thresh,
            providers=self.providers,
            session_options=self.session_options,
        )
        self.recognizer = ArcFaceOnnxRecognizer(
            model_path=rec_path,
            input_size=(112, 112),
            providers=self.providers,
            session_options=self.session_options,
        )

    def _resolve_onnx_paths(
        self,
        det_model_path: Optional[Union[str, Path]],
        rec_model_path: Optional[Union[str, Path]],
        auto_download: bool,
    ) -> Tuple[Path, Path]:
        """Tìm đường dẫn file `.onnx` của SCRFD và ArcFace hoặc tải tự động nếu được phép."""
        if det_model_path and rec_model_path:
            det_p = Path(det_model_path).expanduser().resolve()
            rec_p = Path(rec_model_path).expanduser().resolve()
            if not det_p.is_file():
                raise FileNotFoundError(f"Không tìm thấy model SCRFD tại: {det_p}")
            if not rec_p.is_file():
                raise FileNotFoundError(f"Không tìm thấy model ArcFace tại: {rec_p}")
            return det_p, rec_p

        pack_dir = self.model_root / "models" / self.model_pack
        det_p, rec_p = self._find_models_in_dir(pack_dir)

        if (det_p is None or rec_p is None) and auto_download:
            self._download_pack_via_insightface()
            det_p, rec_p = self._find_models_in_dir(pack_dir)

        if det_p is None or rec_p is None:
            expected_det, expected_rec = self.KNOWN_PACK_FILES.get(
                self.model_pack, ("det_*.onnx", "w600k_*.onnx")
            )
            raise FileNotFoundError(
                f"Không tìm thấy bộ model ONNX '{self.model_pack}' trong '{pack_dir}'.\n"
                f"Cần có file SCRFD ({expected_det}) và ArcFace ({expected_rec}), "
                f"hoặc cài đặt gói `insightface` để tự động tải về."
            )

        return det_p, rec_p

    def _find_models_in_dir(
        self, directory: Path
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """Tìm cặp model SCRFD (`det_*.onnx`) và ArcFace (`w600k_*.onnx` / `glintr*.onnx`) trong thư mục."""
        if not directory.is_dir():
            return None, None

        if self.model_pack in self.KNOWN_PACK_FILES:
            det_name, rec_name = self.KNOWN_PACK_FILES[self.model_pack]
            det_candidate = directory / det_name
            rec_candidate = directory / rec_name
            if det_candidate.is_file() and rec_candidate.is_file():
                return det_candidate, rec_candidate

        det_matches = sorted(directory.glob("det_*.onnx")) or sorted(
            directory.glob("scrfd_*.onnx")
        )
        rec_matches = (
            sorted(directory.glob("w600k_*.onnx"))
            or sorted(directory.glob("glintr*.onnx"))
            or sorted(directory.glob("*arcface*.onnx"))
        )

        det_p = det_matches[0] if det_matches else None
        rec_p = rec_matches[0] if rec_matches else None
        return det_p, rec_p

    def _download_pack_via_insightface(self) -> None:
        """
        Tải gói model chuẩn của InsightFace.
        Ưu tiên dùng `insightface.app.FaceAnalysis` nếu có; nếu không cài `insightface`
        (ví dụ trên Python 3.13), tự động tải trực tiếp gói `.zip` từ GitHub Releases
        của InsightFace và giải nén vào `<model_root>/models/<model_pack>/`.
        """
        try:
            insightface_app = importlib.import_module("insightface.app")
            face_analysis_cls = getattr(insightface_app, "FaceAnalysis")

            logger.info("Đang tải gói model '%s' qua insightface...", self.model_pack)
            app = face_analysis_cls(
                name=self.model_pack,
                root=str(self.model_root),
                allowed_modules=["detection", "recognition"],
                providers=self.providers,
            )
            app.prepare(ctx_id=0, det_size=self.det_size, det_thresh=self.det_thresh)
            return
        except (ImportError, AttributeError):
            pass

        url = (
            f"https://github.com/deepinsight/insightface/releases/download/v0.7/"
            f"{self.model_pack}.zip"
        )
        models_dir = self.model_root / "models"
        pack_dir = models_dir / self.model_pack
        zip_path = models_dir / f"{self.model_pack}.zip"
        part_path = models_dir / f"{self.model_pack}.zip.part"
        pack_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Đang tải gói model ONNX '%s' từ %s ...", self.model_pack, url)
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (HRM_PayRoll FaceEngine)"},
            )
            # Xử lý chứng chỉ SSL trên macOS (Python.org installer thiếu cert.pem mặc định)
            cafile: Optional[str] = None
            try:
                certifi_mod = importlib.import_module("certifi")
                cafile = str(certifi_mod.where())
            except ImportError:
                if Path("/etc/ssl/cert.pem").is_file():
                    cafile = "/etc/ssl/cert.pem"

            try:
                ssl_ctx = (
                    ssl.create_default_context(cafile=cafile)
                    if cafile
                    else ssl.create_default_context()
                )
                response = urllib.request.urlopen(req, timeout=120, context=ssl_ctx)
            except urllib.error.URLError as url_err:
                if isinstance(url_err.reason, ssl.SSLError):
                    ssl_ctx = ssl._create_unverified_context()
                    response = urllib.request.urlopen(req, timeout=120, context=ssl_ctx)
                else:
                    raise

            with response, open(part_path, "wb") as out_file:
                total_header = response.headers.get("Content-Length")
                total_bytes = int(total_header) if total_header and total_header.isdigit() else 0
                downloaded = 0
                next_log_pct = 10
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    if total_bytes > 0:
                        pct = int(downloaded * 100 / total_bytes)
                        if pct >= next_log_pct:
                            logger.info(
                                "  Đang tải %s: %d%% (%.1f / %.1f MB)",
                                self.model_pack,
                                pct,
                                downloaded / (1024 * 1024),
                                total_bytes / (1024 * 1024),
                            )
                            next_log_pct = ((pct // 10) + 1) * 10
            part_path.replace(zip_path)

            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    filename = Path(member.filename).name
                    if not filename:
                        continue
                    target_file = pack_dir / filename
                    with zf.open(member) as src, open(target_file, "wb") as dst:
                        dst.write(src.read())
        except Exception as exc:
            raise RuntimeError(
                f"Không thể tự động tải gói model '{self.model_pack}' từ {url}: {exc}"
            ) from exc
        finally:
            for tmp_file in (part_path, zip_path):
                if tmp_file.exists():
                    try:
                        tmp_file.unlink()
                    except OSError:
                        pass

    # ------------------------------------------------------------------------
    # CÁC PHƯƠNG THỨC XỬ LÝ ẢNH, TRÍCH XUẤT EMBEDDING & KIỂM TRA CHẤT LƯỢNG
    # ------------------------------------------------------------------------

    @staticmethod
    def read_image(image_or_path: Union[str, Path, np.ndarray]) -> np.ndarray:
        """Đọc ảnh từ đường dẫn hoặc kiểm tra mảng numpy BGR đầu vào."""
        if isinstance(image_or_path, (str, Path)):
            img = cv2.imread(str(image_or_path))
            if img is None:
                raise ValueError(f"Không thể đọc file ảnh: {image_or_path}")
            return np.asarray(img, dtype=np.uint8)
        if isinstance(image_or_path, np.ndarray):
            if image_or_path.ndim != 3 or image_or_path.shape[2] != 3:
                raise ValueError(
                    f"Ảnh numpy phải có dạng (H, W, 3) BGR, nhận được {image_or_path.shape}"
                )
            return image_or_path
        raise TypeError(f"Kiểu dữ liệu ảnh không được hỗ trợ: {type(image_or_path)}")

    def detect(
        self,
        image_or_path: Union[str, Path, np.ndarray],
        max_num: int = 0,
        extract_embedding: bool = False,
        check_quality: bool = True,
        allow_pose_variation: bool = False,
    ) -> List[DetectedFace]:
        """
        Phát hiện toàn bộ khuôn mặt trong khung hình, căn chỉnh 112x112,
        và tùy chọn đánh giá chất lượng + trích xuất vector 512 chiều.
        """
        image = self.read_image(image_or_path)
        det, kpss = self.detector.detect(image, max_num=max_num)
        num_faces = int(det.shape[0])

        faces: List[DetectedFace] = []
        aligned_list: List[np.ndarray] = []

        for i in range(num_faces):
            bbox = det[i, :4].copy()
            score = float(det[i, 4])
            kps = kpss[i].copy()
            aligned = align_face_5p(image, kps, image_size=112)

            face_obj = DetectedFace(
                bbox=bbox,
                det_score=score,
                kps=kps,
                aligned_face=aligned,
            )
            if check_quality:
                face_obj.quality = assess_face_quality(
                    image=image,
                    face=face_obj,
                    num_faces_in_frame=num_faces,
                    config=self.quality_config,
                    require_single_face=False,
                    allow_pose_variation=allow_pose_variation,
                )
            faces.append(face_obj)
            aligned_list.append(aligned)

        if extract_embedding and aligned_list:
            embeddings = self.recognizer.get_embeddings_batch(aligned_list)
            for face_obj, emb in zip(faces, embeddings):
                face_obj.embedding = emb

        return faces

    def extract_single_face(
        self,
        image_or_path: Union[str, Path, np.ndarray],
        require_single_face: bool = True,
        check_quality: bool = True,
        allow_pose_variation: bool = False,
        min_secondary_face_area_ratio: float = 0.25,
    ) -> Tuple[Optional[DetectedFace], FaceQualityReport]:
        """
        Phát hiện khuôn mặt chính, kiểm tra điều kiện hợp lệ (bắt buộc đúng 1 mặt ở tiền cảnh khi chấm công)
        và trích xuất vector đặc trưng 512 chiều đã chuẩn hóa L2.

        Tham số `min_secondary_face_area_ratio` (mặc định 0.25): bỏ qua các khuôn mặt phụ ở hậu cảnh
        có diện tích nhỏ hơn 25% diện tích khuôn mặt chính đứng trước Kiosk.
        """
        image = self.read_image(image_or_path)
        det_thresh = (
            min(self.det_thresh, 0.45) if allow_pose_variation else self.det_thresh
        )
        det, kpss = self.detector.detect(image, det_thresh=det_thresh, max_num=0)
        num_faces = int(det.shape[0])

        if num_faces == 0:
            report = FaceQualityReport(
                is_valid=False,
                num_faces=0,
                reasons=["no_face"],
            )
            return None, report

        # Chọn khuôn mặt có diện tích lớn nhất làm khuôn mặt chính ở tiền cảnh
        areas = (det[:, 2] - det[:, 0]) * (det[:, 3] - det[:, 1])
        best_idx = int(np.argmax(areas))
        max_area = float(areas[best_idx])

        # Chỉ tính các khuôn mặt có diện tích đáng kể (>= 25% mặt chính) là mặt cạnh tranh ở tiền cảnh
        foreground_mask = areas >= (max_area * float(min_secondary_face_area_ratio))
        num_foreground_faces = int(np.sum(foreground_mask))

        bbox = det[best_idx, :4].copy()
        score = float(det[best_idx, 4])
        kps = kpss[best_idx].copy()
        aligned = align_face_5p(image, kps, image_size=112)

        face_obj = DetectedFace(
            bbox=bbox,
            det_score=score,
            kps=kps,
            aligned_face=aligned,
        )

        report = assess_face_quality(
            image=image,
            face=face_obj,
            num_faces_in_frame=num_foreground_faces,
            config=self.quality_config,
            require_single_face=require_single_face,
            allow_pose_variation=allow_pose_variation,
        )
        face_obj.quality = report

        if check_quality and not report.is_valid:
            return face_obj, report

        face_obj.embedding = self.recognizer.get_embedding(aligned)
        return face_obj, report

    def get_embedding(
        self,
        image_or_path: Union[str, Path, np.ndarray],
        require_single_face: bool = True,
        check_quality: bool = True,
        allow_pose_variation: bool = False,
    ) -> np.ndarray:
        """
        Trả về trực tiếp vector embedding 512 chiều (L2-normalized).
        Ném `ValueError` kèm lý do nếu khung hình không đạt tiêu chuẩn.
        """
        face, report = self.extract_single_face(
            image_or_path=image_or_path,
            require_single_face=require_single_face,
            check_quality=check_quality,
            allow_pose_variation=allow_pose_variation,
        )
        if face is None or face.embedding is None:
            raise ValueError(
                f"Không thể trích xuất embedding hợp lệ. Lý do: {', '.join(report.reasons)}"
            )
        return face.embedding

    # ------------------------------------------------------------------------
    # ĐĂNG KÝ KHUÔN MẶT (ENROLLMENT) & SO KHỚP (VERIFICATION / 1:N MATCHING)
    # ------------------------------------------------------------------------

    def enroll_from_images(
        self,
        images_or_dir: Union[str, Path, Sequence[Union[str, Path, np.ndarray]]],
        employee_id: Optional[str] = None,
        min_valid_images: int = 3,
        min_intra_similarity: float = 0.35,
        check_quality: bool = True,
    ) -> EnrollmentResult:
        """
        Đăng ký khuôn mặt nhân viên từ thư mục ảnh (ví dụ `data/face/raw/NV0001`)
        hoặc danh sách 3-5 ảnh chụp ở các góc (thẳng, trái, phải, trên, dưới).

        Quy trình (Mục 4.1 - PLAN.MD):
        1. Kiểm tra chất lượng từng ảnh (loại ảnh mờ, tối, nhiều mặt, không thấy mặt).
        2. Căn chỉnh theo 5 điểm mốc và trích xuất vector 512 chiều cho từng ảnh hợp lệ.
        3. Kiểm tra độ đồng nhất giữa các ảnh đăng ký (tránh trộn ảnh của 2 người khác nhau).
        4. Tính vector đại diện (centroid) đã chuẩn hóa L2.
        """
        if isinstance(images_or_dir, (str, Path)):
            dir_path = Path(images_or_dir)
            if dir_path.is_dir():
                if employee_id is None:
                    employee_id = dir_path.name
                valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
                items: List[Union[str, Path, np.ndarray]] = [
                    p
                    for p in sorted(dir_path.iterdir())
                    if p.is_file() and p.suffix.lower() in valid_exts
                ]
            else:
                items = [dir_path]
        else:
            items = list(images_or_dir)

        embeddings: List[np.ndarray] = []
        valid_files: List[str] = []
        rejected_files: Dict[str, List[str]] = {}

        for idx, item in enumerate(items):
            label = str(item) if isinstance(item, (str, Path)) else f"frame_{idx}"
            try:
                face, report = self.extract_single_face(
                    image_or_path=item,
                    require_single_face=True,
                    check_quality=check_quality,
                    allow_pose_variation=True,  # Cho phép góc nghiêng nhẹ khi enrollment
                )
            except Exception as exc:
                rejected_files[label] = [f"read_error:{exc}"]
                continue

            if face is None or face.embedding is None or (check_quality and not report.is_valid):
                rejected_files[label] = report.reasons or ["invalid_face"]
                continue

            embeddings.append(face.embedding)
            valid_files.append(label)

        if len(embeddings) < min_valid_images:
            return EnrollmentResult(
                success=False,
                employee_id=employee_id,
                centroid_embedding=None,
                embeddings=embeddings,
                valid_files=valid_files,
                rejected_files=rejected_files,
                mean_intra_similarity=0.0,
                message=(
                    f"Số lượng ảnh hợp lệ ({len(embeddings)}) ít hơn mức tối thiểu ({min_valid_images})."
                ),
            )

        emb_matrix = np.vstack(embeddings).astype(np.float32)  # (K, 512)
        centroid = l2_normalize(emb_matrix.mean(axis=0))

        # Tính độ tương đồng trung bình giữa từng ảnh góc với vector trung tâm
        sims_to_centroid = np.asarray(emb_matrix @ centroid, dtype=np.float32)
        mean_sim = float(sims_to_centroid.mean())
        min_sim = float(sims_to_centroid.min())

        if min_sim < min_intra_similarity:
            return EnrollmentResult(
                success=False,
                employee_id=employee_id,
                centroid_embedding=None,
                embeddings=embeddings,
                valid_files=valid_files,
                rejected_files=rejected_files,
                mean_intra_similarity=mean_sim,
                message=(
                    f"Các ảnh đăng ký không đồng nhất (min similarity = {min_sim:.3f} < {min_intra_similarity:.3f})."
                ),
            )

        return EnrollmentResult(
            success=True,
            employee_id=employee_id,
            centroid_embedding=centroid,
            embeddings=embeddings,
            valid_files=valid_files,
            rejected_files=rejected_files,
            mean_intra_similarity=mean_sim,
            message=f"Đăng ký thành công {len(embeddings)}/{len(items)} ảnh.",
        )

    @staticmethod
    def match(
        query_embedding: np.ndarray,
        gallery: Dict[str, np.ndarray],
        threshold: float = 0.55,
        min_margin: float = 0.08,
    ) -> MatchResult:
        """
        So khớp vector khuôn mặt `query_embedding` (512,) với danh sách nhân viên `gallery`.

        - `gallery`: Dict ánh xạ `employee_id -> np.ndarray` có shape `(512,)` (1 vector centroid)
          hoặc `(K, 512)` (nhiều mẫu góc mặt của nhân viên đó).
        - Quy tắc chấp nhận (Mục 4.1 - PLAN.MD):
          1. Điểm khớp cao nhất `best_score >= threshold`.
          2. Nếu trong gallery có từ 2 nhân viên trở lên, khoảng cách giữa người khớp nhất
             và người khớp nhì phải thỏa `best_score - second_best_score >= min_margin`.
        """
        if not gallery:
            return MatchResult(
                matched=False,
                employee_id=None,
                similarity=0.0,
                second_best_employee_id=None,
                second_best_similarity=0.0,
                margin=0.0,
                threshold=threshold,
                min_margin=min_margin,
                reason="empty_gallery",
            )

        q = l2_normalize(query_embedding.reshape(-1))
        scores: List[Tuple[str, float]] = []

        for emp_id, ref in gallery.items():
            ref_arr = np.asarray(ref, dtype=np.float32)
            if ref_arr.ndim == 1:
                ref_norm = l2_normalize(ref_arr)
                score = float(np.dot(q, ref_norm))
            elif ref_arr.ndim == 2:
                ref_norm = l2_normalize(ref_arr, axis=1)
                score = float(np.max(ref_norm @ q))
            else:
                raise ValueError(
                    f"Embedding của nhân viên '{emp_id}' có shape không hợp lệ: {ref_arr.shape}"
                )
            scores.append((emp_id, score))

        scores.sort(key=lambda item: item[1], reverse=True)
        best_emp, best_score = scores[0]
        if len(scores) > 1:
            second_emp, second_score = scores[1]
            margin = float(best_score - second_score)
        else:
            second_emp, second_score = None, -1.0
            margin = float("inf")

        if best_score < threshold:
            return MatchResult(
                matched=False,
                employee_id=None,
                similarity=best_score,
                second_best_employee_id=second_emp,
                second_best_similarity=second_score,
                margin=margin,
                threshold=threshold,
                min_margin=min_margin,
                reason="below_threshold",
            )

        if len(scores) > 1 and margin < min_margin:
            return MatchResult(
                matched=False,
                employee_id=None,
                similarity=best_score,
                second_best_employee_id=second_emp,
                second_best_similarity=second_score,
                margin=margin,
                threshold=threshold,
                min_margin=min_margin,
                reason="ambiguous_margin",
            )

        return MatchResult(
            matched=True,
            employee_id=best_emp,
            similarity=best_score,
            second_best_employee_id=second_emp,
            second_best_similarity=second_score,
            margin=margin,
            threshold=threshold,
            min_margin=min_margin,
            reason="accepted",
        )

    def enroll_gallery_from_root(
        self,
        raw_root_or_emp_dir: Union[str, Path],
        min_valid_images: int = 3,
    ) -> Tuple[Dict[str, np.ndarray], List[EnrollmentResult]]:
        """
        Tự động nạp danh sách nhân viên từ một thư mục gốc (ví dụ `data/face/raw/` chứa `NV0001`, `NV0002`...)
        hoặc từ thư mục của 1 nhân viên (`data/face/raw/NV0001`).

        Lưu cả vector trung tâm (`centroid_embedding`) lẫn các vector từng góc chụp hợp lệ thành ma trận
        `(K + 1, 512)` cho mỗi nhân viên để tăng độ chính xác khi nhận diện nghiêng đầu trên camera.
        """
        root_path = Path(raw_root_or_emp_dir)
        if not root_path.exists():
            return {}, []

        subdirs = sorted([d for d in root_path.iterdir() if d.is_dir()])
        target_dirs = subdirs if subdirs else [root_path]

        gallery: Dict[str, np.ndarray] = {}
        results: List[EnrollmentResult] = []
        for emp_dir in target_dirs:
            res = self.enroll_from_images(
                emp_dir,
                employee_id=emp_dir.name,
                min_valid_images=min_valid_images,
            )
            results.append(res)
            if res.success and res.centroid_embedding is not None:
                all_vecs = np.vstack([res.centroid_embedding] + res.embeddings).astype(
                    np.float32
                )
                gallery[str(res.employee_id)] = all_vecs

        return gallery, results

    def run_webcam(
        self,
        gallery: Dict[str, np.ndarray],
        camera_id: int = 0,
        threshold: float = 0.55,
        min_margin: float = 0.08,
        mirror: bool = True,
        save_dir: Optional[Union[str, Path]] = None,
    ) -> None:  # pragma: no cover
        """
        Bật Webcam nhận diện khuôn mặt thời gian thực (Kiosk Realtime Mode).
        Phím tắt trên cửa sổ camera:
          - `q` hoặc `ESC`: Thoát camera.
          - `c`: Chụp và lưu khung hình hiện tại (phục vụ thu thập thêm ảnh mẫu).
        """
        cap = cv2.VideoCapture(camera_id)
        if not cap.isOpened():
            raise RuntimeError(
                f"Không thể mở camera (camera_id={camera_id}). "
                "Trên macOS, hãy kiểm tra quyền Camera cho Terminal / VS Code trong System Settings > Privacy & Security > Camera."
            )

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        window_name = "HRM_PayRoll - Kiosk Face Recognition (Press 'q' to exit, 'c' to capture)"
        print(f"\n[WEBCAM] Đang mở camera {camera_id}... Nhấn 'q' hoặc ESC trên cửa sổ video để thoát.")

        save_root = Path(save_dir) if save_dir else (_PROJECT_ROOT / "data" / "face" / "captures")
        fps_ema = 0.0

        try:
            while True:
                t_start = time.perf_counter()
                ok, frame = cap.read()
                if not ok or frame is None:
                    print("[WEBCAM] Không đọc được khung hình từ camera.")
                    break

                if mirror:
                    frame = cv2.flip(frame, 1)

                display = frame.copy()
                face, report = self.extract_single_face(
                    frame,
                    require_single_face=True,
                    check_quality=True,
                    allow_pose_variation=False,
                )

                infer_ms = (time.perf_counter() - t_start) * 1000.0
                inst_fps = 1000.0 / max(infer_ms, 1e-3)
                fps_ema = inst_fps if fps_ema == 0.0 else (0.85 * fps_ema + 0.15 * inst_fps)

                status_text = "NO FACE DETECTED"
                status_color = (180, 180, 180)

                if face is not None:
                    x1, y1, x2, y2 = [int(v) for v in face.bbox]

                    if report.is_valid and face.embedding is not None:
                        match_res = self.match(
                            face.embedding,
                            gallery,
                            threshold=threshold,
                            min_margin=min_margin,
                        )
                        if match_res.matched and match_res.employee_id is not None:
                            box_color = (0, 210, 0)  # Xanh lá: Nhận diện thành công
                            label = f"{match_res.employee_id} | sim={match_res.similarity:.2f}"
                            status_text = f"CHECK-IN OK: {match_res.employee_id} ({match_res.similarity:.3f})"
                            status_color = (0, 230, 0)
                        else:
                            box_color = (0, 0, 235)  # Đỏ: Người lạ / dưới ngưỡng
                            label = f"UNKNOWN | sim={match_res.similarity:.2f}"
                            status_text = f"REJECTED ({match_res.reason}: {match_res.similarity:.3f})"
                            status_color = (0, 0, 255)
                    else:
                        box_color = (0, 165, 255)  # Cam: Chất lượng khung hình chưa đạt
                        reasons_str = ", ".join(report.reasons)
                        label = f"QUALITY: {reasons_str}"
                        status_text = f"WARNING: {reasons_str}"
                        status_color = (0, 180, 255)

                    # Vẽ khung mặt & 5 điểm mốc
                    cv2.rectangle(display, (x1, y1), (x2, y2), box_color, 2)
                    for pt in face.kps.astype(int):
                        cv2.circle(display, (int(pt[0]), int(pt[1])), 3, (255, 255, 0), -1)

                    cv2.putText(
                        display,
                        label,
                        (x1, max(30, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.75,
                        box_color,
                        2,
                        cv2.LINE_AA,
                    )

                # Thanh thông tin Kiosk ở góc trên
                cv2.rectangle(display, (0, 0), (display.shape[1], 75), (25, 25, 25), -1)
                cv2.putText(
                    display,
                    f"Latency: {infer_ms:.1f} ms | FPS: {fps_ema:.1f} | Gallery: {len(gallery)} emp",
                    (15, 28),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.68,
                    (240, 240, 240),
                    2,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    display,
                    status_text,
                    (15, 60),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.78,
                    status_color,
                    2,
                    cv2.LINE_AA,
                )

                cv2.imshow(window_name, display)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):  # 'q' hoặc ESC
                    break
                if key == ord("c"):
                    save_root.mkdir(parents=True, exist_ok=True)
                    ts_name = f"capture_{int(time.time() * 1000)}.jpg"
                    out_file = save_root / ts_name
                    cv2.imwrite(str(out_file), frame)
                    print(f"[WEBCAM] Đã lưu ảnh chụp tại: {out_file}")
        finally:
            cap.release()
            cv2.destroyAllWindows()


# Bí danh tương thích ngược
InsightFaceEngine = FaceEngine


# ============================================================================
# 5. CLI DEMO ĐĂNG KÝ, SO KHỚP & WEBCAM REALTIME (MILESTONE M1)
# ============================================================================


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CLI thử nghiệm Wrapper InsightFace (SCRFD + ArcFace) trên ONNX Runtime"
    )
    parser.add_argument(
        "--enroll-dir",
        type=str,
        default="HRM_PayRoll/data/face/raw",
        help="Thư mục chứa ảnh nhân viên để đăng ký (ví dụ: HRM_PayRoll/data/face/raw hoặc HRM_PayRoll/data/face/raw/NV0001)",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Đường dẫn ảnh cần kiểm tra so khớp (mặc định: lấy ảnh đầu tiên hợp lệ)",
    )
    parser.add_argument(
        "--webcam",
        action="store_true",
        help="Bật camera quét và nhận diện khuôn mặt thời gian thực sau khi nạp dữ liệu đăng ký",
    )
    parser.add_argument(
        "--camera-id",
        type=int,
        default=0,
        help="Chỉ số thiết bị camera (mặc định: 0)",
    )
    parser.add_argument(
        "--model-pack",
        type=str,
        default="buffalo_l",
        help="Tên gói model InsightFace (buffalo_l hoặc buffalo_s)",
    )
    parser.add_argument(
        "--det-model",
        type=str,
        default=None,
        help="Đường dẫn trực tiếp tới file ONNX của SCRFD (ví dụ: det_10g.onnx)",
    )
    parser.add_argument(
        "--rec-model",
        type=str,
        default=None,
        help="Đường dẫn trực tiếp tới file ONNX của ArcFace (ví dụ: w600k_r50.onnx)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.55,
        help="Ngưỡng Cosine Similarity tối thiểu để chấp nhận (mặc định: 0.55)",
    )
    return parser


def main() -> None:  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    args = _build_cli_parser().parse_args()

    engine = FaceEngine(
        model_pack=args.model_pack,
        det_model_path=args.det_model,
        rec_model_path=args.rec_model,
    )
    print(f"Đã khởi tạo FaceEngine với providers: {engine.providers}")
    print(f"  - SCRFD ONNX  : {engine.det_model_path}")
    print(f"  - ArcFace ONNX: {engine.rec_model_path}")

    enroll_path = Path(args.enroll_dir)
    if not enroll_path.exists():
        for candidate in (
            _PROJECT_ROOT / "data" / "face" / "raw",
            Path("data/face/raw"),
            Path("HRM_PayRoll/data/face/raw/NV0001"),
        ):
            if candidate.exists():
                enroll_path = candidate
                break

    gallery, enroll_results = engine.enroll_gallery_from_root(enroll_path)
    first_valid_file: Optional[str] = None

    for result in enroll_results:
        print(f"\n[ENROLLMENT] Nhân viên: {result.employee_id}")
        print(f"  - Trạng thái           : {'THÀNH CÔNG' if result.success else 'THẤT BẠI'}")
        print(f"  - Thông báo            : {result.message}")
        print(
            f"  - Ảnh hợp lệ ({len(result.valid_files)})      : {[Path(p).name for p in result.valid_files]}"
        )
        if result.rejected_files:
            print(f"  - Ảnh bị loại ({len(result.rejected_files)})     : {result.rejected_files}")
        print(f"  - Độ đồng nhất nội bộ  : {result.mean_intra_similarity:.4f}")
        if first_valid_file is None and result.valid_files:
            first_valid_file = result.valid_files[0]

    if gallery and not args.webcam:
        query_file = args.query or first_valid_file
        if query_file:
            q_emb = engine.get_embedding(query_file, check_quality=False)
            match_res = engine.match(q_emb, gallery, threshold=args.threshold)
            print(f"\n[MATCHING] Ảnh kiểm tra: {Path(query_file).name}")
            print(f"  - Khớp nhân viên : {match_res.employee_id} (matched={match_res.matched})")
            print(f"  - Cosine Score   : {match_res.similarity:.4f} (threshold={match_res.threshold})")
            print(f"  - Lý do          : {match_res.reason}")

    if args.webcam:
        engine.run_webcam(
            gallery=gallery,
            camera_id=args.camera_id,
            threshold=args.threshold,
        )


if __name__ == "__main__":
    main()
