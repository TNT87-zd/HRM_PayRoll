"""Enrollment session lifecycle. Files are private; activation is a DB pointer swap."""
from collections import Counter
from dataclasses import asdict
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import shutil
import threading
import time
import uuid
import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError
from fastapi import HTTPException
from sqlalchemy import delete, select, update
from config import CONSENT_VERSION, POSES
from cv.head_pose import classify_pose, relative_pose
from cv.matching import l2_normalize, match, validate_embeddings
from models import Employee, EnrollmentSession, FaceSample, FaceTemplate
from repository import employee_or_404

logger = logging.getLogger("uvicorn.error")


def decode_image(data, settings):
    if not data or len(data) > settings.max_image_bytes:
        raise ValueError("image_size_limit")
    try:
        with Image.open(io.BytesIO(data)) as header:
            if header.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("invalid_image_type")
            width, height = header.size
            if width * height > settings.max_image_pixels or min(width, height) < 80:
                raise ValueError("image_dimensions")
        image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("invalid_image")
        return image
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("invalid_image") from exc


def consistent_vectors(vectors, threshold=0.35):
    vectors = l2_normalize(validate_embeddings(vectors, batch=True), axis=1)
    other_centroids = l2_normalize(vectors.sum(axis=0) - vectors, axis=1)
    cross = np.sum(vectors * other_centroids, axis=1)
    graph = vectors @ vectors.T >= threshold
    visited, pending = {0}, [0]
    while pending:
        neighbors = set(np.flatnonzero(graph[pending.pop()])) - visited
        visited.update(neighbors)
        pending.extend(neighbors)
    return bool(np.min(cross) >= threshold and len(visited) == len(vectors))


def ensure_uuid(value):
    try:
        parsed = str(uuid.UUID(value))
        if parsed != value:
            raise ValueError()
        return parsed
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, "ID mẫu/phiên không hợp lệ")


class EnrollmentService:
    def __init__(self, settings, session_factory, face_service, pose_estimator):
        self.settings, self.session_factory = settings, session_factory
        self.face, self.pose = face_service, pose_estimator
        self.lock = threading.RLock()

    def path(self, relative):
        root = self.settings.storage_dir.resolve()
        target = (root / relative).resolve()
        if root not in target.parents:
            raise RuntimeError("Invalid private storage path")
        return target

    def get_session(self, db, employee_id, session_id, owner_id, allow_committed=False):
        ensure_uuid(session_id)
        session = db.get(EnrollmentSession, session_id)
        if not session or session.employee_id != employee_id or session.owner_id != owner_id:
            raise HTTPException(404, "Không tìm thấy phiên đăng ký")
        if session.status != "committed" and session.expires_at <= time.time():
            self.discard(db, session, "expired")
            raise HTTPException(410, "Phiên đã hết hạn. Hồ sơ và FaceID đang dùng vẫn được giữ")
        if session.status in {"cancelled", "expired", "failed"}:
            raise HTTPException(409, f"Phiên không còn hoạt động: {session.status}")
        if session.status == "committed" and not allow_committed:
            raise HTTPException(409, "Phiên đã hoàn tất")
        return session

    def create(self, db, employee_id, owner_id, payload, key):
        employee = employee_or_404(db, employee_id)
        if employee.employment_status != "active":
            raise HTTPException(409, "Kích hoạt hồ sơ nhân viên trước khi đăng ký khuôn mặt")
        if not payload.consent or payload.consent_version != CONSENT_VERSION:
            raise HTTPException(422, "Cần xác nhận nội dung đồng ý hiện hành")
        scoped_key = f"face:{owner_id}:{employee_id}:{key}"
        with self.lock:
            existing = db.scalar(select(EnrollmentSession).where(EnrollmentSession.create_key == scoped_key))
            if existing:
                return self.get_session(db, employee_id, existing.id, owner_id, allow_committed=True)
            self.cleanup(db)
            active = db.scalars(select(EnrollmentSession).where(EnrollmentSession.owner_id == owner_id,
                EnrollmentSession.status.in_(["capturing", "ready_to_commit"]))).all()
            if len(active) >= 3:
                raise HTTPException(409, "Hủy các phiên cũ trước khi tạo thêm phiên")
            session = EnrollmentSession(id=str(uuid.uuid4()), employee_id=employee_id, owner_id=owner_id,
                consent_version=CONSENT_VERSION, expires_at=time.time() + self.settings.session_ttl,
                model_version=self.settings.model_version, preprocessing_version=self.settings.preprocessing_version,
                create_key=scoped_key)
            db.add(session)
            db.commit()
            return session

    def view(self, db, session):
        samples = db.scalars(select(FaceSample).where(FaceSample.session_id == session.id).order_by(FaceSample.captured_at)).all()
        counts = Counter(sample.pose for sample in samples)
        ready = session.status == "committed" and self.face.template_ids.get(session.employee_id) == session.template_id
        return {
            "session_id": session.id, "employee_id": session.employee_id, "status": session.status,
            "server_time": time.time(),
            "pose_counts": {pose: counts[pose] for pose in POSES}, "expires_at": session.expires_at,
            "samples": [{"sample_id": sample.id, "pose": sample.pose,
                         "quality": json.loads(sample.quality_json)} for sample in samples],
            "error": session.error, "model_version": session.model_version,
            "preprocessing_version": session.preprocessing_version,
            "gallery_version": self.face.gallery_version, "ready": ready,
            "baseline": json.loads(session.baseline_json),
        }

    def add_samples(self, db, session, uploads):
        if self.face.engine is None:
            raise HTTPException(503, "FaceEngine chưa sẵn sàng")
        accepted, rejected = [], []
        with self.lock:
            db.refresh(session)
            if session.status not in {"capturing", "ready_to_commit"} or session.expires_at <= time.time():
                raise HTTPException(409, "Phiên không còn nhận ảnh")
            if session.model_version != self.settings.model_version or session.preprocessing_version != self.settings.preprocessing_version:
                raise HTTPException(409, "Cấu hình đã thay đổi; cần bắt đầu phiên mới")
            for meta, data in uploads:
                sample_id = ensure_uuid(meta.get("sample_id"))
                pose_name = meta.get("pose")
                if pose_name not in POSES:
                    raise HTTPException(422, "Hướng mặt không hợp lệ")
                try:
                    self._add_one(db, session, sample_id, pose_name, meta.get("captured_at"), data)
                    accepted.append(sample_id)
                except ValueError as exc:
                    rejected.append({"sample_id": sample_id, "pose": pose_name, "reasons": [str(exc)]})
                except RuntimeError as exc:
                    logger.exception("Không thể kiểm tra hướng mặt")
                    db.rollback()
                    raise HTTPException(503, "Bộ kiểm tra hướng mặt chưa sẵn sàng; vui lòng kiểm tra model") from exc
            db.flush()
            counts = Counter(db.scalars(select(FaceSample.pose).where(FaceSample.session_id == session.id)).all())
            session.status = "ready_to_commit" if all(counts[pose] == 2 for pose in POSES) else "capturing"
            session.error = None
            db.commit()
        return {**self.view(db, session), "accepted_samples": accepted, "rejected_samples": rejected}

    def _add_one(self, db, session, sample_id, pose_name, captured_at, data):
        checksum = hashlib.sha256(data).hexdigest()
        existing = db.get(FaceSample, sample_id)
        if existing:
            if existing.session_id != session.id or existing.checksum != checksum or existing.pose != pose_name:
                raise ValueError("sample_id_conflict")
            return
        samples = db.scalars(select(FaceSample).where(FaceSample.session_id == session.id)).all()
        same_pose = [s for s in samples if s.pose == pose_name]
        if len(same_pose) >= 2:
            raise ValueError("pose_complete")
        if any(s.checksum == checksum for s in samples):
            raise ValueError("duplicate_image")
        if not isinstance(captured_at, (float, int)) or not np.isfinite(captured_at) or not session.created_at - 5 <= captured_at <= time.time() + 5:
            raise ValueError("invalid_capture_time")
        if any(abs(s.captured_at - captured_at) < 0.3 for s in same_pose):
            raise ValueError("frames_too_close")
        image = decode_image(data, self.settings)
        with self.face.lock:
            face, report = self.face.engine.extract_single_face(image, require_single_face=True,
                check_quality=True, allow_pose_variation=True, min_secondary_face_area_ratio=0.0)
        if face is None or not report.is_valid or face.embedding is None:
            raise ValueError(",".join(report.reasons) or "invalid_face")
        if report.det_score < 0.6:
            raise ValueError("low_det_score")
        height, width = image.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in face.bbox]
        if min(x1, y1) < 2 or x2 > width - 2 or y2 > height - 2:
            raise ValueError("face_clipped")
        if min(x2 - x1, y2 - y1) < 100:
            raise ValueError("face_too_small")
        absolute = self.pose.analyze(image)
        baseline = json.loads(session.baseline_json)
        if not baseline:
            if pose_name != "front" or abs(absolute.yaw) > 15 or abs(absolute.pitch) > 25 or abs(absolute.roll) > 12:
                raise ValueError("front_required")
            baseline = asdict(absolute)
        relative = relative_pose(absolute, baseline)
        if classify_pose(relative) != pose_name:
            raise ValueError("wrong_pose")
        aligned = face.aligned_face
        if aligned is None:
            from cv.alignment import align_face_5p
            aligned = align_face_5p(image, face.kps)
        fingerprint = cv2.resize(cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY), (32, 32), interpolation=cv2.INTER_AREA)
        for previous in same_pose:
            old = np.frombuffer(previous.image_hash, np.uint8).reshape(32, 32)
            old_pose = json.loads(previous.quality_json)
            angle_delta = abs(old_pose["yaw"] - relative.yaw) + abs(old_pose["pitch"] - relative.pitch)
            if float(np.abs(fingerprint.astype(float) - old).mean()) < 1.5 and angle_delta < 3:
                raise ValueError("duplicate_image")
        vector = l2_normalize(validate_embeddings(face.embedding))
        quality = asdict(report)
        quality.update(asdict(relative))
        quality["score"] = round(0.4 * min(report.blur_score / 150, 1) + 0.25 * max(0, 1 - abs(report.brightness - 128) / 128)
                                 + 0.2 * min(min(x2 - x1, y2 - y1) / 250, 1) + 0.15 * report.det_score, 4)
        quality["original_size"] = [width, height]
        margin_x, margin_y = int((x2 - x1) * 0.2), int((y2 - y1) * 0.2)
        crop = image[max(0, y1-margin_y):min(height, y2+margin_y), max(0, x1-margin_x):min(width, x2+margin_x)]
        if max(crop.shape[:2]) > 512:
            scale = 512 / max(crop.shape[:2])
            crop = cv2.resize(crop, (round(crop.shape[1] * scale), round(crop.shape[0] * scale)), interpolation=cv2.INTER_AREA)
        ok, encoded = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not ok:
            raise RuntimeError("Cannot encode face crop")
        relative_path = f"face/staging/{session.id}/{sample_id}.jpg"
        path = self.path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        with temporary.open("wb") as image_file:
            image_file.write(encoded.tobytes())
            image_file.flush()
            os.fsync(image_file.fileno())
        temporary.replace(path)
        db.add(FaceSample(id=sample_id, session_id=session.id, pose=pose_name, path=relative_path,
            checksum=checksum, captured_at=captured_at, quality_json=json.dumps(quality),
            embedding=vector.astype(np.float32).tobytes(), image_hash=fingerprint.tobytes()))
        session.baseline_json = json.dumps(baseline)
        db.flush()

    def remove_sample(self, db, session, sample_id):
        ensure_uuid(sample_id)
        with self.lock:
            sample = db.get(FaceSample, sample_id)
            if not sample or sample.session_id != session.id:
                raise HTTPException(404, "Không tìm thấy ảnh")
            self.path(sample.path).unlink(missing_ok=True)
            db.delete(sample)
            session.status = "capturing"
            db.commit()
        return self.view(db, session)

    def commit(self, db, session):
        with self.lock:
            db.refresh(session)
            if session.status == "committed":
                self.face.load_gallery(db)
                return self.view(db, session)
            if session.expires_at <= time.time():
                self.discard(db, session, "expired")
                raise HTTPException(410, "Phiên đã hết hạn")
            if session.model_version != self.settings.model_version or session.preprocessing_version != self.settings.preprocessing_version:
                raise HTTPException(409, "Cấu hình đã thay đổi; cần bắt đầu phiên mới")
            if employee_or_404(db, session.employee_id).employment_status != "active":
                raise HTTPException(409, "Hồ sơ nhân viên đã ngừng hoạt động")
            samples = db.scalars(select(FaceSample).where(FaceSample.session_id == session.id).order_by(FaceSample.pose, FaceSample.captured_at)).all()
            counts = Counter(s.pose for s in samples)
            if session.status != "ready_to_commit" or len(samples) != 10 or not all(counts[p] == 2 for p in POSES):
                raise HTTPException(422, "Cần đúng hai ảnh đạt chất lượng cho mỗi hướng trong năm hướng")
            vectors = np.vstack([np.frombuffer(s.embedding, np.float32) for s in samples])
            if not consistent_vectors(vectors):
                session.error = "inconsistent_identity"
                db.commit()
                raise HTTPException(422, {"code": "inconsistent_identity", "message": "Các mẫu không đồng nhất; kiểm tra lại nhân viên và quét lại phiên"})
            centroid = l2_normalize(vectors.mean(axis=0))
            self.face.load_gallery(db)
            others = {key: value for key, value in self.face.gallery.items() if key != session.employee_id}
            candidate = match(centroid, others, threshold=0.80, min_margin=0.0)
            if candidate.matched:
                raise HTTPException(409, {"code": "duplicate_identity", "employee_id": candidate.employee_id,
                    "message": "Khuôn mặt rất giống hồ sơ đã có. Kiểm tra lại danh tính trước khi đăng ký"})
            staging = self.path(f"face/staging/{session.id}")
            final = self.path(f"face/enrollments/{session.employee_id}/{session.id}")
            final.parent.mkdir(parents=True, exist_ok=True)
            # A previous crash may already have moved the immutable folder.
            source = staging if staging.exists() else final
            if not source.is_dir() or any(not (source / f"{s.id}.jpg").is_file() for s in samples):
                raise HTTPException(409, "Thiếu ảnh tạm; cần thu lại phiên")
            if source == staging:
                staging.rename(final)
            template_id = str(uuid.uuid4())
            matrix = np.vstack([centroid, vectors]).astype(np.float32)
            employee = employee_or_404(db, session.employee_id)
            old_id = employee.active_template_id
            try:
                db.add(FaceTemplate(id=template_id, employee_id=employee.employee_id, session_id=session.id,
                    vectors=matrix.tobytes(), vector_count=11, model_version=session.model_version,
                    preprocessing_version=session.preprocessing_version))
                for sample in samples:
                    sample.path = f"face/enrollments/{employee.employee_id}/{session.id}/{sample.id}.jpg"
                if old_id:
                    old = db.get(FaceTemplate, old_id)
                    if old:
                        old.retired_at = time.time()
                employee.active_template_id, employee.is_real_face = template_id, True
                employee.updated_at = time.time()
                session.status, session.template_id, session.error = "committed", template_id, None
                db.commit()
            except Exception:
                db.rollback()
                if final.exists() and not staging.exists():
                    staging.parent.mkdir(parents=True, exist_ok=True)
                    final.rename(staging)
                raise
            self.face.load_gallery(db)
            return self.view(db, session)

    def discard(self, db, session, status="cancelled"):
        if session.status == "committed":
            raise HTTPException(409, "Không thể hủy bộ FaceID đã hoàn tất bằng thao tác hủy phiên")
        with self.lock:
            session.status = status
            for relative in (f"face/staging/{session.id}", f"face/enrollments/{session.employee_id}/{session.id}"):
                shutil.rmtree(self.path(relative), ignore_errors=True)
            db.execute(delete(FaceSample).where(FaceSample.session_id == session.id))
            db.commit()

    def cleanup(self, db):
        now = time.time()
        for session in db.scalars(select(EnrollmentSession).where(EnrollmentSession.status.in_(["capturing", "ready_to_commit"]), EnrollmentSession.expires_at < now)).all():
            self.discard(db, session, "expired")
        # Recover interrupted file moves for still-open sessions.
        for session in db.scalars(select(EnrollmentSession).where(EnrollmentSession.status.in_(["capturing", "ready_to_commit"]))).all():
            final, staging = self.path(f"face/enrollments/{session.employee_id}/{session.id}"), self.path(f"face/staging/{session.id}")
            if final.exists() and not staging.exists():
                staging.parent.mkdir(parents=True, exist_ok=True)
                final.rename(staging)
            if staging.exists():
                kept = {sample.id for sample in db.scalars(select(FaceSample).where(FaceSample.session_id == session.id)).all()}
                for path in staging.iterdir():
                    if path.is_file() and path.stem not in kept:
                        path.unlink()
        retention = now - self.settings.old_template_retention_days * 86400
        active = set(db.scalars(select(Employee.active_template_id).where(Employee.active_template_id.is_not(None))).all())
        for template in db.scalars(select(FaceTemplate).where(FaceTemplate.retired_at < retention)).all():
            if template.id in active:
                continue
            if template.session_id:
                shutil.rmtree(self.path(f"face/enrollments/{template.employee_id}/{template.session_id}"), ignore_errors=True)
                db.execute(delete(FaceSample).where(FaceSample.session_id == template.session_id))
            db.delete(template)
        db.commit()
