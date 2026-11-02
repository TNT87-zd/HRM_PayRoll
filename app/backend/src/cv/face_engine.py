"""Public facade for face detection, quality checks, enrollment and matching."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "cv"

from .alignment import ARCFACE_SRC_KPS, align_face_5p, estimate_pose_ratios
from .matching import cosine_similarity, l2_normalize, match
from .model_store import ModelStore
from .onnx_backend import ArcFaceOnnxRecognizer, SCRFDOnnxDetector, ort, _ORT_IMPORT_ERROR
from .quality import assess_face_quality
from .types import DetectedFace, EnrollmentResult, FaceQualityConfig, FaceQualityReport, MatchResult

_PROJECT_ROOT = Path(__file__).resolve().parents[4]


class FaceEngine:
    """
    Wrapper thống nhất cho pipeline InsightFace (SCRFD + ArcFace) chạy ONNX Runtime.

    Cách khởi tạo:
    - Nếu truyền `det_model_path` và `rec_model_path` (hoặc đã có sẵn trong `~/.insightface/models/<model_pack>/`):
      sử dụng trực tiếp `SCRFDOnnxDetector` + `ArcFaceOnnxRecognizer` trên `onnxruntime.InferenceSession`.
    - Nếu chưa có file `.onnx` tại chỗ, tự động gọi `insightface.app.FaceAnalysis` để tải gói model
      (`buffalo_l` hoặc `buffalo_s`), sau đó nạp qua ONNX Runtime.
    """

    KNOWN_PACK_FILES = ModelStore.KNOWN_PACK_FILES

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

        det_path, rec_path = ModelStore(
            model_pack=self.model_pack, model_root=self.model_root,
            providers=self.providers, det_size=self.det_size, det_thresh=self.det_thresh,
        ).resolve_paths(
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
        """Delegate to cv.enrollment.enroll_from_images."""
        from .enrollment import enroll_from_images

        return enroll_from_images(
            self,
            images_or_dir=images_or_dir,
            employee_id=employee_id,
            min_valid_images=min_valid_images,
            min_intra_similarity=min_intra_similarity,
            check_quality=check_quality,
        )

    @staticmethod
    def match(
        query_embedding: np.ndarray,
        gallery: Dict[str, np.ndarray],
        threshold: float = 0.55,
        min_margin: float = 0.08,
    ) -> MatchResult:
        """Match an embedding against the gallery; see cv.matching."""
        return match(
            query_embedding=query_embedding,
            gallery=gallery,
            threshold=threshold,
            min_margin=min_margin,
        )

    def enroll_gallery_from_root(
        self,
        raw_root_or_emp_dir: Union[str, Path],
        min_valid_images: int = 3,
    ) -> Tuple[Dict[str, np.ndarray], List[EnrollmentResult]]:
        """Delegate to cv.enrollment.enroll_gallery_from_root."""
        from .enrollment import enroll_gallery_from_root

        return enroll_gallery_from_root(
            self,
            raw_root_or_emp_dir=raw_root_or_emp_dir,
            min_valid_images=min_valid_images,
        )

    def run_webcam(
        self,
        gallery: Dict[str, np.ndarray],
        camera_id: int = 0,
        threshold: float = 0.55,
        min_margin: float = 0.08,
        mirror: bool = True,
        save_dir: Optional[Union[str, Path]] = None,
    ) -> None:  # pragma: no cover
        """Delegate to cv.webcam.run_webcam."""
        from .webcam import run_webcam

        return run_webcam(
            self,
            gallery=gallery,
            camera_id=camera_id,
            threshold=threshold,
            min_margin=min_margin,
            mirror=mirror,
            save_dir=save_dir,
        )


InsightFaceEngine = FaceEngine


def main() -> None:
    from .cli import main as cli_main
    cli_main()


if __name__ == "__main__":
    main()
