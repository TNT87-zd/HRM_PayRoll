import logging
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from services.geofence import GEOFENCE_RADIUS_M, distance_to_branch

logger = logging.getLogger("uvicorn.error")  # để in log INFO ra Terminal

PROJECT_ROOT = Path(__file__).resolve().parents[4]
FACE_RAW_DIR = PROJECT_ROOT / "data" / "face" / "raw"
EMPLOYEES_CSV = PROJECT_ROOT / "data" / "clean" / "employees.csv"

THRESHOLD = 0.55          # ngưỡng cosine theo plan
MIN_MARGIN = 0.08
DUPLICATE_WINDOW_S = 60   # cùng 1 người trong 60 giây chỉ ghi nhận 1 lần


def _load_names() -> dict[str, str]:
    try:
        df = pd.read_csv(EMPLOYEES_CSV)
        col = next((c for c in ("full_name", "name", "ho_ten") if c in df.columns), None)
        if col:
            return dict(zip(df["employee_id"].astype(str), df[col].astype(str)))
    except Exception:
        logger.warning("Không đọc được tên nhân viên từ %s", EMPLOYEES_CSV)
    return {}


class FaceService:
    def __init__(self):
        self.engine = None
        self.gallery: dict[str, np.ndarray] = {}
        self.names: dict[str, str] = {}
        self.error: str | None = None
        self._last_seen: dict[str, float] = {}

    def startup(self, db=None):
        """Gọi 1 lần ở lifespan: nạp model + gallery. Lỗi thì server vẫn chạy."""
        try:
            from cv.face_engine import FaceEngine  # import muộn để thiếu thư viện không làm sập server
            self.engine = FaceEngine(model_pack="buffalo_l")
            self.load_gallery(db)
            self.error = None
            logger.info("FaceService sẵn sàng. Gallery: %s", list(self.gallery))
        except Exception as exc:
            self.engine = None
            self.error = str(exc)
            logger.exception("FaceService KHÔNG khởi động được: %s", exc)

    def load_gallery(self, db=None):
        """Nạp khuôn mặt từ data/face/raw/<mã NV>/*.jpg (chưa dùng bảng DB)."""
        self.names = _load_names()
        gallery, results = self.engine.enroll_gallery_from_root(FACE_RAW_DIR)
        self.gallery = gallery
        for r in results:
            logger.info("Đăng ký %s: %s - %s", r.employee_id, "OK" if r.success else "THẤT BẠI", r.message)

    def recognize(self, img_bgr: np.ndarray, device_id: str = "", lat=None, lon=None) -> dict:
        res = {
            "matched": False, "employee_id": None, "full_name": None,
            "similarity": 0.0, "reason": "", "bbox": None,
            "liveness_score": None,  # TODO: chưa có mô hình liveness (MiniFASNet)
            "distance_m": None,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        if self.engine is None:
            res["reason"] = "engine_unavailable"
            return res

        dist = distance_to_branch(device_id, lat, lon)
        if dist is not None:
            res["distance_m"] = round(dist, 1)

        face, report = self.engine.extract_single_face(
            img_bgr, require_single_face=True, check_quality=True
        )
        if face is None:
            res["reason"] = "no_face"
            return res

        res["bbox"] = [float(v) for v in face.bbox]  # [x1, y1, x2, y2]

        if not report.is_valid or face.embedding is None:
            reasons = [str(x) for x in (report.reasons or [])]
            logger.info("Chất lượng ảnh chưa đạt: %s", reasons)
            res["reason"] = "multiple_faces" if any("multi" in x for x in reasons) else "low_quality"
            return res

        m = self.engine.match(face.embedding, self.gallery, threshold=THRESHOLD, min_margin=MIN_MARGIN)
        res["similarity"] = round(float(m.similarity), 3)
        if not m.matched or m.employee_id is None:
            res["reason"] = m.reason  # below_threshold / ambiguous_margin / empty_gallery
            return res

        emp = str(m.employee_id)
        res["employee_id"] = emp
        res["full_name"] = self.names.get(emp, emp)

        if dist is not None and dist > GEOFENCE_RADIUS_M:
            res["reason"] = "outside_geofence"
            return res

        now = time.monotonic()
        last = self._last_seen.get(emp)
        if last is not None and now - last < DUPLICATE_WINDOW_S:
            res["matched"] = True
            res["reason"] = "duplicate"
            return res

        self._last_seen[emp] = now
        res["matched"] = True
        res["reason"] = "accepted"
        return res

    def get_employee_face_status(self, employee_id: str) -> dict:
        """Kiểm tra trạng thái ảnh và vector của nhân viên."""
        emp_id = employee_id.strip().upper()
        emp_dir = FACE_RAW_DIR / emp_id
        photos: list[str] = []
        if emp_dir.is_dir():
            valid_exts = {".jpg", ".jpeg", ".png", ".webp"}
            photos = [p.name for p in sorted(emp_dir.iterdir()) if p.is_file() and p.suffix.lower() in valid_exts]
        return {
            "employee_id": emp_id,
            "has_gallery": emp_id in self.gallery,
            "photo_count": len(photos),
            "photos": photos,
            "full_name": self.names.get(emp_id, emp_id),
        }

    def _update_employee_record(self, employee_id: str, full_name: str | None = None) -> None:
        """Cập nhật is_real_face=True và full_name vào employees.csv nếu có."""
        try:
            if not EMPLOYEES_CSV.is_file():
                return
            df = pd.read_csv(EMPLOYEES_CSV)
            if "employee_id" not in df.columns:
                return

            emp_mask = df["employee_id"].astype(str).str.upper() == employee_id.upper()
            if emp_mask.any():
                if "is_real_face" in df.columns:
                    df.loc[emp_mask, "is_real_face"] = True
                if full_name and "full_name" in df.columns:
                    df.loc[emp_mask, "full_name"] = full_name
            else:
                # Thêm nhân viên mới nếu chưa có
                new_row = {
                    "employee_id": employee_id.upper(),
                    "full_name": full_name or employee_id.upper(),
                    "branch_id": "CN01",
                    "role": "phuc_vu",
                    "contract_type": "FT",
                    "primary_shift": "CA_SANG",
                    "base_salary": 8000000.0,
                    "hourly_rate": 0.0,
                    "hire_date": datetime.now().strftime("%Y-%m-%d"),
                    "is_real_face": True,
                }
                clean_row = {col: new_row.get(col, "") for col in df.columns}
                df = pd.concat([df, pd.DataFrame([clean_row])], ignore_index=True)

            df.to_csv(EMPLOYEES_CSV, index=False, encoding="utf-8-sig")
            self.names = _load_names()
        except Exception as exc:
            logger.warning("Không thể cập nhật employees.csv cho %s: %s", employee_id, exc)

    def enroll(
        self,
        employee_id: str,
        files: list[tuple[str, bytes]],
        full_name: str | None = None,
        db=None,
    ) -> dict:
        """
        Đăng ký khuôn mặt mới hoặc cập nhật vector khuôn mặt cho nhân viên:
        - files: danh sách tuple (tên_file, nội_dung_bytes)
        - Lưu các file vào thư mục data/face/raw/<employee_id>/<pose>.jpg
        - Dùng FaceEngine để kiểm tra chất lượng & trích xuất vector 512 chiều
        - Nạp ma trận embedding vào self.gallery[employee_id] và lưu cache .npy
        """
        emp_id = employee_id.strip().upper()
        if not emp_id:
            return {
                "ok": False,
                "employee_id": emp_id,
                "num_valid": 0,
                "mean_intra_similarity": 0.0,
                "message": "Mã nhân viên không hợp lệ.",
                "valid_files": [],
                "rejected_files": {},
            }

        if len(files) < 3:
            return {
                "ok": False,
                "employee_id": emp_id,
                "num_valid": 0,
                "mean_intra_similarity": 0.0,
                "message": f"Cần tối thiểu 3 ảnh để đăng ký (nhận được {len(files)} ảnh). Chuẩn là 5 góc ảnh.",
                "valid_files": [],
                "rejected_files": {},
            }

        if self.engine is None:
            self.startup(db)
        if self.engine is None:
            return {
                "ok": False,
                "employee_id": emp_id,
                "num_valid": 0,
                "mean_intra_similarity": 0.0,
                "message": f"Mô hình FaceEngine chưa sẵn sàng: {self.error or 'Lỗi khởi tạo'}",
                "valid_files": [],
                "rejected_files": {},
            }

        emp_dir = FACE_RAW_DIR / emp_id
        emp_dir.mkdir(parents=True, exist_ok=True)

        standard_poses = ["front", "left", "right", "up", "under"]
        for idx, (filename, content) in enumerate(files):
            fname_lower = filename.lower()
            if "front" in fname_lower:
                pose_name = "front"
            elif "left" in fname_lower:
                pose_name = "left"
            elif "right" in fname_lower:
                pose_name = "right"
            elif "up" in fname_lower or "nguoc" in fname_lower:
                pose_name = "up"
            elif "under" in fname_lower or "down" in fname_lower or "cui" in fname_lower:
                pose_name = "under"
            elif idx < len(standard_poses):
                pose_name = standard_poses[idx]
            else:
                pose_name = f"pose_{idx}"

            target_file = emp_dir / f"{pose_name}.jpg"
            target_file.write_bytes(content)

        # Trích xuất đặc trưng & kiểm tra chất lượng bằng FaceEngine
        result = self.engine.enroll_from_images(
            emp_dir,
            employee_id=emp_id,
            min_valid_images=3,
            min_intra_similarity=0.35,
            check_quality=True,
        )

        valid_names = [Path(p).name for p in result.valid_files]
        rejected_dict = {Path(k).name: v for k, v in result.rejected_files.items()}

        if not result.success or result.centroid_embedding is None:
            logger.warning(
                "Đăng ký FaceID cho NV %s thất bại: %s (Hợp lệ: %d/%d)",
                emp_id, result.message, len(valid_names), len(files)
            )
            return {
                "ok": False,
                "employee_id": emp_id,
                "num_valid": len(valid_names),
                "mean_intra_similarity": round(float(result.mean_intra_similarity), 3),
                "message": result.message,
                "valid_files": valid_names,
                "rejected_files": rejected_dict,
            }

        # Nạp vector vào RAM (Gallery) để Kiosk nhận diện ngay lập tức
        all_vecs = np.vstack([result.centroid_embedding] + result.embeddings).astype(np.float32)
        self.gallery[emp_id] = all_vecs

        # Lưu bản cache embedding cục bộ
        try:
            np.save(emp_dir / "centroid_embedding.npy", result.centroid_embedding)
        except Exception:
            pass

        # Cập nhật tên hiển thị
        if full_name:
            self.names[emp_id] = full_name
        elif emp_id not in self.names:
            self.names[emp_id] = emp_id

        # Cập nhật trạng thái vào CSDL / employees.csv
        self._update_employee_record(emp_id, full_name=full_name)

        logger.info(
            "Đăng ký FaceID thành công cho NV %s: %d ảnh hợp lệ, độ tương đồng trung bình: %.3f",
            emp_id, len(valid_names), result.mean_intra_similarity
        )

        return {
            "ok": True,
            "employee_id": emp_id,
            "num_valid": len(valid_names),
            "mean_intra_similarity": round(float(result.mean_intra_similarity), 3),
            "message": f"Đã nạp thành công FaceID cho nhân viên {emp_id} ({len(valid_names)}/5 ảnh hợp lệ).",
            "valid_files": valid_names,
            "rejected_files": rejected_dict,
        }


face_service = FaceService()
