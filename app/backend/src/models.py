"""Persistent employee profiles, face templates and revocable access sessions."""
import time
from sqlalchemy import Boolean, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class Employee(Base):
    __tablename__ = "employees"
    employee_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    branch_id: Mapped[str] = mapped_column(String(32))
    role: Mapped[str] = mapped_column(String(32))
    contract_type: Mapped[str] = mapped_column(String(2))
    primary_shift: Mapped[str] = mapped_column(String(32))
    hire_date: Mapped[str] = mapped_column(String(10))
    base_salary: Mapped[float | None] = mapped_column(Float, nullable=True)
    hourly_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    employment_status: Mapped[str] = mapped_column(String(16), default="active")
    active_template_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    is_real_face: Mapped[bool] = mapped_column(Boolean, default=False)
    create_key: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
    create_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class Counter(Base):
    __tablename__ = "counters"
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16), default="hr")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[float] = mapped_column(Float)


class EnrollmentSession(Base):
    __tablename__ = "face_enrollment_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.employee_id"), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(24), default="capturing")
    consent_version: Mapped[str] = mapped_column(String(80))
    consent_at: Mapped[float] = mapped_column(Float, default=time.time)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    expires_at: Mapped[float] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String(120))
    preprocessing_version: Mapped[str] = mapped_column(String(120))
    baseline_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    create_key: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)


class FaceSample(Base):
    __tablename__ = "face_samples"
    __table_args__ = (UniqueConstraint("session_id", "checksum"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("face_enrollment_sessions.id"), index=True)
    pose: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64))
    captured_at: Mapped[float] = mapped_column(Float)
    quality_json: Mapped[str] = mapped_column(Text)
    embedding: Mapped[bytes] = mapped_column(LargeBinary)
    image_hash: Mapped[bytes] = mapped_column(LargeBinary)


class FaceTemplate(Base):
    __tablename__ = "face_templates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.employee_id"), index=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("face_enrollment_sessions.id"), unique=True, nullable=True)
    vectors: Mapped[bytes] = mapped_column(LargeBinary)
    vector_count: Mapped[int] = mapped_column(Integer)
    model_version: Mapped[str] = mapped_column(String(120))
    preprocessing_version: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    retired_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.employee_id"), index=True)
    device_id: Mapped[str] = mapped_column(String(80))
    scan_type: Mapped[str] = mapped_column(String(3))
    timestamp: Mapped[float] = mapped_column(Float, default=time.time)
    similarity: Mapped[float] = mapped_column(Float)


class MigrationRecord(Base):
    __tablename__ = "migration_records"
    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    detail: Mapped[str] = mapped_column(Text)
