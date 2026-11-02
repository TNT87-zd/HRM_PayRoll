"""ONNX Runtime adapters for SCRFD detection and ArcFace embeddings."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np

from .matching import l2_normalize


try:
    import onnxruntime as ort
except ImportError as exc:  # pragma: no cover
    ort = None  # type: ignore[assignment]
    _ORT_IMPORT_ERROR: Optional[ImportError] = exc
else:
    _ORT_IMPORT_ERROR = None


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
