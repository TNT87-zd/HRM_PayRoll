# HRM Payroll — bản bổ sung luồng nghiệp vụ

Ngày bàn giao: 03/11/2026. Ngôn ngữ: Python + FastAPI + SQLite + HTML/JavaScript.

## 1. Bản này là gì?

Đây là gói code bổ sung cho **HRM_Payroll.zip** đã cung cấp, không phải bộ model AI mới. Giải nén và chép thư mục `HRM_Payroll` vào cùng thư mục dự án gốc. Sao lưu dự án trước khi chép đè các file trùng tên. Gói không chứa model ONNX, ảnh nhân viên, CSDL đang chạy hay mật khẩu; giữ lại `models/` và `data/` từ bản gốc.

Đã đọc cả bản ghi cuộc trao đổi và ZIP gốc. ZIP gốc chưa có thư mục `engines`/`ml` được mô tả trong cuộc trao đổi. Không coi các lệnh đã ghi trong hội thoại là code đã có trên máy bạn. Bản bổ sung triển khai lõi nghiệp vụ độc lập ở `app/backend/src/hrm/`; không tự chạy các lệnh trong bản ghi, không phục hồi những module ML bị thiếu bằng code suy đoán.

Mức hoàn thiện: **MVP tích hợp phục vụ demo nghiệp vụ**. Chưa phải hệ thống trả lương dùng thực tế hoặc toàn bộ phạm vi AI trong `plan.md`.

## 2. Chạy trên Windows / PowerShell

Mở terminal tại thư mục chứa `app`, `data`, `models` của HRM_Payroll. Các lệnh dưới đây chạy trong PowerShell, không nhập vào file Python hoặc ô notebook.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe create_user.py --username admin --role hr
.\.venv\Scripts\python.exe seed_demo.py
.\.venv\Scripts\python.exe -m uvicorn main:app --app-dir app/backend/src --host 127.0.0.1 --port 8000
```

Nếu máy chưa có Python 3.11, dùng một Python >=3.10 đã cài cho phần HRM. Đường dẫn `.venv\Scripts\python.exe` giúp không cần kích hoạt venv, tránh lỗi execution policy. Để cài CV, cần phiên bản Python tương thích các wheel của InsightFace/ONNX Runtime; chưa xác minh cài đặt CV trên máy Windows của bạn.

Mở **http://127.0.0.1:8000/portal.html**. Nhập tài khoản `admin` và mật khẩu bạn vừa tự đặt (ít nhất 12 ký tự). Có thể dùng `run_windows.bat` cho lần chạy sau.

Tạo tài khoản nhân viên sau khi có mã nhân viên:

```powershell
.\.venv\Scripts\python.exe create_user.py --username nv_demo --role employee --employee-id DEMO01
.\.venv\Scripts\python.exe create_user.py --username kiosk01 --role kiosk
```

Mở cửa sổ ẩn danh để đăng nhập nhân viên nếu cần demo cùng lúc với HR. Không tạo sẵn mật khẩu mặc định. Các phiên đăng nhập hết hạn sau 8 giờ; đăng xuất hủy phiên. Mật khẩu được băm scrypt, token phiên được băm trước khi lưu CSDL.

## 3. Demo nhanh

1. `seed_demo.py` thêm `DEMO01`, một ca 08:00–16:00 cách ngày chạy hai ngày, check-in 08:00 và check-out 17:00. Chương trình in kỳ cần chọn, không ghi đè nếu DEMO01 đã tồn tại.
2. Đăng nhập HR → chọn đúng kỳ → **Tải dữ liệu**.
3. Bảng công phải có **8 giờ thường, 1 giờ OT được duyệt**.
4. Nhấn **Tính bản nháp**. Nhân viên PT có lương 50.000 VND/giờ: `8 × 50.000 + 1 × 50.000 × 1,5 = 475.000 VND` trước điều chỉnh.
5. Thêm phụ cấp/thưởng/bảo hiểm/thuế cho mã nhân viên, nhấn **Ghi vào lần tính**, sau đó **Tính bản nháp** lại. Chỉ nhập tiền không âm.
6. Kiểm tra số liệu → đánh dấu đã đối chiếu → **Chốt bảng lương**.
7. Đăng nhập tài khoản nhân viên → chỉ xem phiếu lương đã chốt của mình → tải Excel hoặc in.
8. Demo thêm ca thiếu OUT: hệ thống cho xem nháp nhưng từ chối chốt; HR phải bổ sung OUT có lý do và tính lại.

## 4. Đưa Kiosk vào cùng luồng

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-cv.txt
```

Giữ model tại `models/insightface/models/buffalo_l/` và ảnh tại `data/face/raw/<ma_nv>/` như dự án gốc. Khởi động lại backend. Nếu chưa cài CV hoặc model không tải được, phần HRM vẫn chạy; Kiosk báo chưa sẵn sàng.

- Đăng nhập HR/Kiosk cùng trình duyệt tại `/portal.html`, sau đó mở `/kiosk.html`.
- Tạo nhân viên và lịch ca đúng ngày/giờ/chi nhánh trước khi quét.
- Thiết bị phải có trong `data/clean/devices.csv`; vị trí chi nhánh lấy từ `branches.csv`. GPS phải có và nằm trong bán kính cấu hình hiện hữu.
- Chọn IN/OUT ở Kiosk. Khi nhận diện được chấp nhận, API ghi vào SQLite và gửi thông báo realtime. Không còn suy ca sáng/chiều chỉ từ giờ hiện tại.
- Nếu có nhiều ca phù hợp, hệ thống từ chối để HR kiểm tra, không tự chọn bừa.
- Mục đăng ký khuôn mặt tại portal nhận 3–10 ảnh, tối đa 5 MB/ảnh; dùng engine thật thay endpoint trả `mock` thành công trước đây. **Chưa kiểm chứng độ chính xác/khả năng đăng ký với ảnh thật trong môi trường này.**
- Nhập lại `data/live/scan_log.csv` cũ bằng nút riêng, báo dòng không gắn được ca. Không tự nhập `attendance_events.csv` mô phỏng vì bản gốc thiếu loại IN/OUT.

Liveness vẫn chưa được triển khai. Nhận đủ nhiều khung hình giống nhau không chứng minh chống ảnh/video giả. GPS do trình duyệt gửi lên cũng chưa phải cơ chế chống giả vị trí. Không mô tả những phần này là đã bảo mật hoàn chỉnh trong báo cáo.

## 5. Quy tắc tính công và lương hiện có

- Thời gian chuẩn UTC+07:00; ngày công/kỳ lương lấy theo ngày bắt đầu ca, hỗ trợ ca qua đêm tối đa 16 giờ.
- Lượt vào/ra gắn với một ca cụ thể. Quét cùng loại trong dưới 60 giây được gộp. Chọn IN đầu/OUT cuối sau IN trong ca đó.
- Giờ thường lấy phần giao với lịch ca, trừ một lần số phút nghỉ không lương; không tính giờ vào sớm. Đây là mô hình một khoảng làm/ca, chưa hỗ trợ nhiều lần ra-vào hoặc nhiều khoảng nghỉ thực tế.
- OT chỉ trả trong giới hạn số phút được duyệt trên lịch ca. Hệ số OT do HR cấu hình; giá trị mặc định là giả định demo.
- Trễ/sớm vượt 5 phút mới ghi số phút vi phạm; không tự phạt tiền theo phút. Số giờ thực làm vẫn tính theo thời điểm thực tế.
- Phép PAID được duyệt: cộng giờ ca vào giờ được trả; UNPAID: không cộng. Đơn trùng thời gian đã duyệt bị chặn. Nếu vừa có phép vừa có công, chặn chốt để HR xử lý.
- FT: đơn giá = lương tháng / giờ chuẩn tháng do HR nhập. PT: đơn giá = lương giờ. Lương thường = đơn giá × (giờ thường + giờ phép có lương).
- Tổng thu nhập = lương thường + OT + phụ cấp + thưởng. Thực nhận = tổng thu nhập − bảo hiểm − thuế − khấu trừ khác.
- Thuế/bảo hiểm là khoản đã được HR xác định và nhập, **không phải tính tự động theo luật**. Chưa có bộ chính sách ngày lễ, làm đêm, bảo hiểm/thuế theo ngày hiệu lực, hợp đồng thay đổi giữa kỳ, truy lĩnh hoặc quyết toán năm.
- Kỳ nháp có thể tính lại. Chốt yêu cầu xác nhận rà soát và dữ liệu không thay đổi so với bản nháp, kể cả cấu hình điều chỉnh. Ca tương lai/thiếu IN/OUT/xung đột nghỉ phép không được chốt.
- Kỳ đã chốt là snapshot bất biến; chặn tính lại, đổi lịch, thêm công/duyệt phép ảnh hưởng kỳ. Chưa có nghiệp vụ mở lại/chốt điều chỉnh; không sửa SQLite thủ công để bỏ khóa.
- HR phải kiểm tra lịch đủ cả kỳ: hệ thống không thể biết những ca chưa được nhập. Không có lịch không đồng nghĩa nghỉ không lương.

## 6. Dữ liệu, quyền và vận hành

- CSDL mới: `data/live/hrm.sqlite3`; không thay đổi các CSV mô phỏng.
- Lần đầu chỉ nhập danh mục nhân viên từ `data/clean/employees.csv`; sau đó quản lý tại portal. Mã NV được dùng làm tên tạm nếu CSV không có họ tên. Việc chỉnh CSV sau này không tự ghi đè CSDL.
- CSDL dùng bảng `records(kind,id,payload)` lưu JSON có khóa ghép, cùng bảng users/sessions/audit. Đây là thiết kế MVP, chưa phải schema quan hệ chuẩn hóa đầy đủ để trình bày ERD chính thức.
- HR quản lý toàn hệ thống, nhân viên chỉ thấy dữ liệu cá nhân, Kiosk chỉ vận hành nhận diện. Chưa có vai trò quản lý giới hạn chi nhánh.
- SQLite transaction bảo vệ các thao tác ghi/chốt lương. Chạy **một worker** cho demo vì gallery và phiếu bầu khuôn mặt còn ở RAM.
- Sao lưu: dừng server rồi sao chép `data/live/hrm.sqlite3` và `data/face/raw/` vào nơi an toàn. Không đưa ảnh thật/model/CSDL chứa mật khẩu băm lên GitHub.
- Backend mặc định chỉ nghe trên localhost. Nếu triển khai mạng cần HTTPS (`HRM_HTTPS=1` để cookie Secure), cấu hình origin, reverse proxy, backup/restore, phân quyền chi nhánh và đánh giá bảo vệ dữ liệu sinh trắc học.
- `/admin.html` cũ được giữ nhưng đã gắn nhãn **CSV mô phỏng**, không phải dashboard nghiệp vụ mới. `/portal.html` là nơi xem công/lương từ CSDL. Một số tính năng analytics cũ chưa được sửa trong gói này.

## 7. Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q tests
```

Kiểm thử dùng CSDL tạm, không sửa CSDL của bạn. Phần API Kiosk dùng mock kết quả model/giải mã ảnh để kiểm tra tích hợp, không đo chất lượng nhận diện.

Môi trường đã chạy: Python 3.12, FastAPI 0.162.0, SQLAlchemy 2.1.6, httpx 0.28.1, pytest 9.2.0. Có cảnh báo deprecation từ TestClient/httpx ở môi trường thử, không phải lỗi test. Máy Windows và bộ CV cần kiểm thử riêng.

Xem `DANH_GIA_VA_LO_TRINH.md` để biết những phần còn thiếu cho báo cáo và sản phẩm cuối.
