"""Command-line enrollment, matching and webcam demo."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional

from .face_engine import FaceEngine

_PROJECT_ROOT = Path(__file__).resolve().parents[4]


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
