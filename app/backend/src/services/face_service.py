"""Recognition against versioned templates persisted in SQLite."""
import hashlib
import logging
import threading
from datetime import datetime, timezone
import numpy as np
from sqlalchemy import select
from config import PROJECT_ROOT, Settings
from cv.matching import l2_normalize, match, validate_embeddings
from models import Employee, FaceTemplate, MigrationRecord
from services.geofence import GEOFENCE_RADIUS_M, distance_to_branch

logger = logging.getLogger("uvicorn.error")
FACE_RAW_DIR = PROJECT_ROOT / "data/face/raw"
EMPLOYEES_CSV = PROJECT_ROOT / "data/clean/employees.csv"


class FaceService:
    def __init__(self, settings=None, session_factory=None, engine=None):
        self.settings, self.session_factory = settings or Settings(), session_factory
        self.engine = engine
        self.gallery, self.names, self.template_ids = {}, {}, {}
        self.gallery_version = "empty"
        self.error = None
        self.lock = threading.RLock()

    def startup(self, db=None):
        if self.engine is None:
            try:
                from cv.face_engine import FaceEngine
                self.engine = FaceEngine(model_pack="buffalo_l", auto_download=False, providers=["CPUExecutionProvider"])
                self.error = None
            except Exception as exc:
                self.error = str(exc)
                logger.warning("FaceEngine chưa sẵn sàng: %s", exc)
        model_path = getattr(self.engine, "rec_model_path", None)
        if model_path:
            digest = hashlib.sha256()
            with open(model_path, "rb") as model_file:
                for block in iter(lambda: model_file.read(1024 * 1024), b""):
                    digest.update(block)
            self.settings.model_version = f"buffalo_l:{digest.hexdigest()[:16]}"
        if self.session_factory:
            self.load_gallery(db)

    def load_gallery(self, db=None):
        if db is None:
            with self.session_factory() as own:
                return self.load_gallery(own)
        with self.lock:
            return self._load_gallery_locked(db)

    def _load_gallery_locked(self, db):
        gallery, names, template_ids = {}, {}, {}
        employees = db.scalars(select(Employee).where(Employee.employment_status == "active").execution_options(populate_existing=True)).all()
        for employee in employees:
            names[employee.employee_id] = employee.full_name
            template = db.get(FaceTemplate, employee.active_template_id) if employee.active_template_id else None
            if not template or template.model_version != self.settings.model_version or template.preprocessing_version != self.settings.preprocessing_version:
                continue
            try:
                vectors = np.frombuffer(template.vectors, dtype=np.float32).reshape(template.vector_count, 512).copy()
                validate_embeddings(vectors, batch=True)
                gallery[employee.employee_id] = l2_normalize(vectors, axis=1)
                template_ids[employee.employee_id] = template.id
            except (ValueError, TypeError):
                logger.error("Bỏ qua template hỏng: %s", template.id)
        version = hashlib.sha256(repr(sorted(template_ids.items())).encode()).hexdigest()[:16]
        with self.lock:
            self.gallery, self.names, self.template_ids, self.gallery_version = gallery, names, template_ids, version
        return version

    def import_legacy_gallery(self):
        """Preserve already-working faces once, without changing original photos/CSV."""
        if self.engine is None:
            return
        import json
        import uuid
        with self.session_factory() as db:
            if db.get(MigrationRecord, "legacy-face-v1"):
                return
            imported, rejected = [], []
            for directory in sorted((self.settings.data_dir / "face/raw").glob("*")):
                employee = db.get(Employee, directory.name)
                if not directory.is_dir() or not employee or employee.active_template_id:
                    continue
                try:
                    result = self.engine.enroll_from_images(directory, employee_id=employee.employee_id)
                    if not result.success:
                        rejected.append(employee.employee_id)
                        continue
                    vectors = np.vstack([result.centroid_embedding] + result.embeddings).astype(np.float32)
                    validate_embeddings(vectors, batch=True)
                    template_id = str(uuid.uuid4())
                    db.add(FaceTemplate(id=template_id, employee_id=employee.employee_id, vectors=vectors.tobytes(),
                                        vector_count=len(vectors), model_version=self.settings.model_version,
                                        preprocessing_version=self.settings.preprocessing_version))
                    employee.active_template_id, employee.is_real_face = template_id, True
                    imported.append(employee.employee_id)
                except Exception:
                    logger.exception("Không nhập được bộ FaceID cũ: %s", employee.employee_id)
                    rejected.append(employee.employee_id)
            db.add(MigrationRecord(name="legacy-face-v1", detail=json.dumps({"imported": imported, "rejected": rejected})))
            db.commit()
            self.load_gallery(db)

    def get_employee_face_status(self, employee_id, db):
        employee = db.get(Employee, employee_id)
        template = db.get(FaceTemplate, employee.active_template_id) if employee and employee.active_template_id else None
        ready = bool(template and self.template_ids.get(employee_id) == template.id and employee_id in self.gallery)
        status = ("legacy" if template and not template.session_id else "ready") if ready else "needs_refresh" if template else "not_registered"
        return {"ready": ready, "status": status, "photo_count": max(0, template.vector_count - 1) if template else 0}

    def recognize(self, img_bgr, device_id="", lat=None, lon=None):
        result = dict(matched=False, employee_id=None, full_name=None, similarity=0.0, reason="", bbox=None,
                      liveness_score=None, distance_m=None, timestamp=datetime.now(timezone.utc).isoformat(),
                      gallery_version=self.gallery_version, recorded=False)
        if self.engine is None:
            result["reason"] = "engine_unavailable"
            return result
        with self.lock:
            face, report = self.engine.extract_single_face(img_bgr, require_single_face=True, check_quality=True)
            if face is None:
                result["reason"] = "no_face"
                return result
            result["bbox"] = [float(v) for v in face.bbox]
            if not report.is_valid or face.embedding is None:
                result["reason"] = "multiple_faces" if "multiple_faces" in report.reasons else "low_quality"
                return result
            candidate = match(face.embedding, self.gallery, self.settings.threshold, self.settings.min_margin)
            result["similarity"] = round(candidate.similarity, 4)
            result["reason"] = candidate.reason
            if not candidate.matched:
                return result
            distance = distance_to_branch(device_id, lat, lon)
            result["distance_m"] = round(distance, 1) if distance is not None else None
            if distance is not None and distance > GEOFENCE_RADIUS_M:
                result["reason"] = "outside_geofence"
                return result
            result.update(matched=True, employee_id=candidate.employee_id,
                          full_name=self.names.get(candidate.employee_id, candidate.employee_id))
            return result


face_service = FaceService()
