from fastapi import APIRouter, UploadFile, Depends
from sqlalchemy.orm import Session
from database import get_db
from schemas import EnrollResponse

router = APIRouter()

@router.post("/{emp_id}/face/enroll", response_model=EnrollResponse)
def enroll(emp_id: str, files: list[UploadFile], db: Session = Depends(get_db)):
    # MOCK: sau này thay bằng face_service.enroll(...)
    return EnrollResponse(ok=True, employee_id=emp_id.upper(), num_valid=len(files),
                          mean_intra_similarity=0.79, message="mock")