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

    def enroll(self, employee_id: str, imgs: list[np.ndarray], db) -> dict:
        # TODO: engine.enroll_from_images -> lưu DB -> load_gallery
        raise NotImplementedError


face_service = FaceService()
