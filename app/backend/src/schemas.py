from pydantic import BaseModel

class RecognizeResponse(BaseModel):
    matched: bool
    employee_id: str | None = None
    full_name: str | None = None
    similarity: float = 0.0
    reason: str = ""                 # accepted / below_threshold / no_face / ...
    bbox: list[float] | None = None  # [x1, y1, x2, y2] để Kiosk vẽ khung
    liveness_score: float | None = None
    distance_m: float | None = None
    timestamp: str | None = None

class EnrollResponse(BaseModel):
    ok: bool
    employee_id: str
    num_valid: int = 0
    mean_intra_similarity: float = 0.0
    message: str = ""
    valid_files: list[str] = []
    rejected_files: dict[str, list[str]] = {}

class EmployeeItem(BaseModel):
    employee_id: str
    full_name: str
    branch_id: str = ""
    role: str = ""
    role_vn: str = ""
    has_face: bool = False
    photo_count: int = 0
    is_real_face: bool = False
