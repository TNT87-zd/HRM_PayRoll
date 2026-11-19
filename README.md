**Bản tích hợp HRM trên nền main**

Hướng dẫn nhận nhánh, chạy Windows, chuyển dữ liệu cũ và kiểm thử: [docs/hrm-integration.md](docs/hrm-integration.md).

**HRM Payroll**

Chạy `./run.sh`, sau đó mở [đăng ký nhân viên](http://127.0.0.1:8000/enroll.html).

Cài đặt thư viện, model, tài khoản quản lý, kiểm thử và hiệu chỉnh nhận diện: [hướng dẫn triển khai](docs/employee-registration-implementation.md).

Thiết kế chức năng: [kế hoạch đăng ký nhân viên](docs/employee-registration-plan.md).

## Chạy Windows / PowerShell

Chạy tại thư mục gốc dự án, sau khi cài Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r app/backend/requirements.txt
.\.venv\Scripts\python.exe app/backend/scripts/setup_face_assets.py
.\.venv\Scripts\python.exe -m uvicorn main:app --app-dir app/backend/src --host 127.0.0.1 --port 8000 --reload
```

Giữ terminal server mở. Đăng nhập tại http://127.0.0.1:8000/login.html.
Lần đầu chưa có tài khoản: thiết lập quản lý ở /enroll.html.
Xem hướng dẫn triển khai để chuẩn bị model nhận diện và chuyển dữ liệu cũ; không xóa DB cũ.

## Vai trò quản lý / nhân viên

- HR / manager: hồ sơ và đăng ký mặt tại /enroll.html; phân ca, bảng công, duyệt phép, tính và chốt lương tại /portal.html.
- Hồ sơ có thể lưu trước khi xếp ca và điền lương. Quản lý nhập lương tháng FT hoặc đơn giá giờ PT trong **Tính lương → Mức lương & chốt kỳ**.
- Nhân viên: xem lịch làm, bảng chấm công, lương tạm tính theo ngày và phiếu tháng đã chốt tại `/employee.html`. Nhân viên tự đăng ký từ trang đăng nhập. Quản lý mở **Phê duyệt tài khoản** từ Dashboard hoặc Portal (`/portal.html#approvals`).
- Nhân viên gửi đơn ở tab **Nghỉ phép**. Quản lý xử lý từng đơn ở **Duyệt đơn nghỉ** (`/portal.html#leave`).
- Kiosk: đăng nhập bằng tài khoản kiosk để vào `/kiosk.html`.
- `/admin.html` trình bày Tổng quan và chuyên cần của Hải Châu (CN01) từ SQLite. Bộ lọc theo ngày áp dụng cho biểu đồ, nhật ký, bảng chuyên cần và CSV. Các bản ghi được đánh dấu thử nghiệm được loại khỏi chỉ số vận hành.
- Dữ liệu vận hành và danh mục của dự án dùng CN01 Hải Châu. Script `app/backend/scripts/consolidate_hai_chau.py` mặc định chỉ xem trước và sao lưu khi chạy với `--apply`. Tính lại bản nháp lương đã lưu trước khi chốt sau lần chuyển chi nhánh.

## Điều kiện chấm công

Cần phiên đăng nhập hợp lệ, FaceID đã nạp, thiết bị đăng ký, GPS trong bán kính chi nhánh và đúng một ca phù hợp. Kiosk và bổ sung thủ công dùng chung hàm record_event; bổ sung thủ công cần quyền HR và lý do.
Không có ca trả no_shift; nhiều ca phù hợp trả ambiguous_shift. Không lưu lượt chấm công bị từ chối.
GPS dùng tọa độ chi nhánh trong data/clean/branches.csv; không tự tắt kiểm tra vị trí.
Ảnh cũ trong thư mục không đồng nghĩa template đã được nhập thành công; xem /api/health và log khởi động.
