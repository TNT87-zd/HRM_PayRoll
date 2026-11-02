import shutil
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
import numpy as np
import pandas as pd

import sys
src_path = Path(__file__).resolve().parents[1] / "src"
if str(src_path) not in sys.path:
    sys.path.append(str(src_path))

from main import app
from services.face_service import face_service, FACE_RAW_DIR, EMPLOYEES_CSV


class TestFaceEnrollment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)

    def test_01_enroll_html_page(self):
        """Kiểm tra trang giao diện enroll.html được phục vụ chính xác."""
        response = self.client.get("/enroll.html")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Đăng ký khuôn mặt FaceID", response.text)
        self.assertIn("Studio Chụp Ảnh FaceID", response.text)
        self.assertIn("5 góc ảnh đã thu thập", response.text)

    def test_02_list_employees(self):
        """Kiểm tra API danh sách nhân sự trả về đầy đủ các trường FaceID."""
        response = self.client.get("/api/employees")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 28)

        emp1 = next((e for e in data if e["employee_id"] == "NV0001"), None)
        self.assertIsNotNone(emp1)
        self.assertTrue(emp1["has_face"])
        self.assertEqual(emp1["photo_count"], 5)
        self.assertEqual(emp1["role_vn"], "Quản lý")

    def test_03_get_employee_detail(self):
        """Kiểm tra API thông tin chi tiết một nhân viên."""
        response = self.client.get("/api/employees/NV0001")
        self.assertEqual(response.status_code, 200)
        emp = response.json()
        self.assertEqual(emp["employee_id"], "NV0001")
        self.assertEqual(emp["full_name"], "Thành viên nhóm 1 (thật)")
        self.assertTrue(emp["has_face"])

    def test_04_enroll_missing_consent(self):
        """Kiểm tra từ chối đăng ký nếu chưa có cam kết đồng ý sinh trắc học."""
        nv1_dir = FACE_RAW_DIR / "NV0001"
        files = [
            ("files", ("front.jpg", (nv1_dir / "front.jpg").read_bytes(), "image/jpeg")),
        ]
        response = self.client.post(
            "/api/employees/NV_TEST/face/enroll",
            files=files,
            data={"consent": "false"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("đồng ý", response.json()["detail"].lower())

    def test_05_enroll_missing_files(self):
        """Kiểm tra từ chối đăng ký nếu không gửi ảnh nào."""
        response = self.client.post(
            "/api/employees/NV_TEST/face/enroll",
            data={"consent": "true"}
        )
        self.assertIn(response.status_code, (400, 422))

    def test_06_full_enrollment_and_instant_kiosk_matching(self):
        """
        Test toàn trình Module 1:
        1. Đăng ký nhân viên mới NV_AUTO với 5 góc ảnh.
        2. API lưu 5 file vào data/face/raw/NV_AUTO/*.jpg.
        3. Trích xuất đặc trưng ArcFace 512D và tính độ đồng nhất > 0.35.
        4. Nạp tức thì vào bộ nhớ FaceService Gallery.
        5. Kiểm tra trạng thái chi tiết nhân viên.
        """
        test_emp_id = "NV_AUTO"
        raw_nv1 = FACE_RAW_DIR / "NV0001"
        self.assertTrue(raw_nv1.is_dir(), "NV0001 sample directory must exist")

        files_data = [
            ("files", ("front.jpg", (raw_nv1 / "front.jpg").read_bytes(), "image/jpeg")),
            ("files", ("left.jpg", (raw_nv1 / "left.jpg").read_bytes(), "image/jpeg")),
            ("files", ("right.jpg", (raw_nv1 / "right.jpg").read_bytes(), "image/jpeg")),
            ("files", ("up.jpg", (raw_nv1 / "up.jpg").read_bytes(), "image/jpeg")),
            ("files", ("under.jpg", (raw_nv1 / "under.jpg").read_bytes(), "image/jpeg")),
        ]

        try:
            resp = self.client.post(
                f"/api/employees/{test_emp_id}/face/enroll",
                files=files_data,
                data={
                    "full_name": "Nhân Viên Tự Động Hóa",
                    "consent": "true"
                }
            )
            self.assertEqual(resp.status_code, 200, f"Enroll failed: {resp.text}")
            data = resp.json()
            self.assertTrue(data["ok"])
            self.assertEqual(data["employee_id"], test_emp_id)
            self.assertEqual(data["num_valid"], 5)
            self.assertGreaterEqual(data["mean_intra_similarity"], 0.35)

            # Kiểm tra file đã được ghi trên đĩa
            target_dir = FACE_RAW_DIR / test_emp_id
            self.assertTrue(target_dir.is_dir())
            self.assertTrue((target_dir / "front.jpg").is_file())
            self.assertTrue((target_dir / "left.jpg").is_file())
            self.assertTrue((target_dir / "right.jpg").is_file())
            self.assertTrue((target_dir / "up.jpg").is_file())
            self.assertTrue((target_dir / "under.jpg").is_file())

            # Kiểm tra vector đã được nạp vào FaceService Gallery
            self.assertIn(test_emp_id, face_service.gallery)
            self.assertEqual(face_service.gallery[test_emp_id].shape[1], 512)

            # Kiểm tra API chi tiết nhân viên cập nhật has_face=True
            detail_resp = self.client.get(f"/api/employees/{test_emp_id}")
            self.assertEqual(detail_resp.status_code, 200)
            detail = detail_resp.json()
            self.assertTrue(detail["has_face"])
            self.assertEqual(detail["photo_count"], 5)

        finally:
            cleanup_dir = FACE_RAW_DIR / test_emp_id
            if cleanup_dir.exists():
                shutil.rmtree(cleanup_dir)
            if test_emp_id in face_service.gallery:
                del face_service.gallery[test_emp_id]
            if EMPLOYEES_CSV.is_file():
                df = pd.read_csv(EMPLOYEES_CSV)
                df = df[df["employee_id"] != test_emp_id]
                df.to_csv(EMPLOYEES_CSV, index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    unittest.main()
