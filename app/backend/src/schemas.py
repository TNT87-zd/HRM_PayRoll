from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ROLE_VN = {"quan_ly": "Quản lý", "pha_che": "Pha chế", "thu_ngan": "Thu ngân", "phuc_vu": "Phục vụ", "bao_ve": "Bảo vệ", "tap_vu": "Tạp vụ"}


class EmployeeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    full_name: str = Field(min_length=2, max_length=120)
    branch_id: str = Field(min_length=1, max_length=32)
    role: str
    contract_type: Literal["FT", "PT"]
    primary_shift: str = Field(min_length=1, max_length=32)
    hire_date: date
    base_salary: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    hourly_rate: float | None = Field(default=None, gt=0, allow_inf_nan=False)

    @field_validator("role")
    @classmethod
    def valid_role(cls, value):
        if value not in ROLE_VN:
            raise ValueError("Chức vụ không hợp lệ")
        return value

    @model_validator(mode="after")
    def valid_pay(self):
        if self.contract_type == "FT" and (self.base_salary is None or self.hourly_rate is not None):
            raise ValueError("FT cần lương tháng; bỏ trống lương giờ")
        if self.contract_type == "PT" and (self.hourly_rate is None or self.base_salary is not None):
            raise ValueError("PT cần lương giờ; bỏ trống lương tháng")
        return self


class EmployeePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    branch_id: str | None = None
    role: str | None = None
    contract_type: Literal["FT", "PT"] | None = None
    primary_shift: str | None = None
    hire_date: date | None = None
    base_salary: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    hourly_rate: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    employment_status: Literal["active", "inactive"] | None = None


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=128)


class SessionCreate(BaseModel):
    consent: Literal[True]
    consent_version: str


class RecognizeResponse(BaseModel):
    matched: bool
    employee_id: str | None = None
    full_name: str | None = None
    similarity: float = 0.0
    reason: str = ""
    bbox: list[float] | None = None
    liveness_score: float | None = None
    distance_m: float | None = None
    timestamp: str | None = None
    recorded: bool = False
    gallery_version: str = ""
