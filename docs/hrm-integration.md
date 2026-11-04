# Bản tích hợp HRM trên nền main — 04/11/2026

Nền main: e939bd804f30ac5eec1583a2bd17e66ed7db8045.
Nghiệp vụ tham khảo từ NhatTruong: 6e0971de25f6bc6df6a7050e8e952db0880b1a1c.
Đây là nhánh tích hợp để nhóm kiểm tra, chưa push hoặc gộp lên GitHub.

## Những phần được giữ và nối lại

- Giữ create_app, SQLAlchemy, Employee, FaceTemplate, AttendanceRecord, đăng ký mặt theo phiên và các module cv của main.
- Giữ nguyên thuật toán cv/face_engine.py và các module nhận diện của main.
- Portal dùng cùng cookie, bảng User/LoginSession và API đăng nhập với trang đăng ký mặt. Manager được coi như HR trên Portal; employee chỉ xem dữ liệu của mình; kiosk chỉ quét công.
- Tạo/sửa nhân viên và đăng ký mặt ở enroll.html. Portal đọc cùng bảng Employee, không tạo danh sách nhân viên thứ hai.
- Lịch ca, nghỉ phép, bảng lương chốt và nhật ký được lưu trong các bảng mới ở cùng database của main. Bảng hrm_records chứa JSON nghiệp vụ; có thể chuẩn hóa thành các bảng quan hệ riêng ở giai đoạn sau.
- Mỗi lượt kiosk lưu đúng một AttendanceRecord; AttendanceAssignment gắn lượt đó với lịch ca. Dashboard và bảng công đọc cùng nguồn chấm công.
- Giữ cách main nhận 3–5 frame để xác nhận một lượt quét. Chống trùng theo nhân viên + IN/OUT trong 60 giây; chỉ thông báo thành công sau commit database.
- Bắt buộc có đúng một ca phù hợp, nhân viên hoạt động, thiết bị đăng ký đúng chi nhánh và GPS trong bán kính 50 m. Chưa có ca hoặc nhiều ca phù hợp: trả 409, không ghi công và không tính lương.
- Kiosk lấy GPS thực từ trình duyệt, không còn tọa độ cố định. Khi thử ở nhà, dùng chi nhánh thử có tọa độ đúng địa điểm thử; đừng sửa tọa độ chi nhánh thật chỉ để vượt kiểm tra.
- Portal có mục lượt công cũ chưa gắn ca: HR chọn ca và nhập lý do. Việc gắn ca không tạo thêm bản ghi AttendanceRecord.
- Bảng công tự cập nhật mỗi 3 giây khi Portal đang mở. Thuế/bảo hiểm vẫn do HR nhập theo chính sách demo, không tự tính theo luật.

## 1. Nhận nhánh tích hợp, giữ nguyên thư mục đang làm

Giải nén gói tải về. Trong thư mục đó có hrm-integration.bundle (gói Git), integration.patch (để review) và hướng dẫn.
Mở File Explorer vào đúng thư mục có hrm-integration.bundle, bấm thanh địa chỉ, gõ powershell rồi Enter. Chạy:

```powershell
$bundle = (Resolve-Path .\hrm-integration.bundle).Path
git -C "D:\ZiDan\HRM_Payroll" fetch origin
git -C "D:\ZiDan\HRM_Payroll" bundle verify "$bundle"
git -C "D:\ZiDan\HRM_Payroll" fetch "$bundle" integrate-hrm:integrate-hrm
git -C "D:\ZiDan\HRM_Payroll" worktree add "D:\ZiDan\HRM_Payroll_Integrated" integrate-hrm
```

Nếu báo nhánh/thư mục đã tồn tại, dừng để kiểm tra, không dùng -f. Lệnh worktree tạo thư mục riêng, không chuyển nhánh hay ghi đè file tại HRM_Payroll. Nếu thư mục cũ còn merge dở, vẫn giữ đó để xử lý sau; không chạy git add -A tại thư mục merge dở.
Gói bundle chỉ chứa commit mới và cần commit nền main ở trên (git fetch origin cung cấp nền đó).

## 2. Cài và chạy trên Windows

```powershell
cd "D:\ZiDan\HRM_Payroll_Integrated"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r app/backend/requirements.txt
.\.venv\Scripts\python.exe app/backend/scripts/setup_face_assets.py
```

Model nhận diện ONNX vẫn dùng buffalo_l của main. Nếu đã có thư mục models chạy tốt ở dự án cũ, copy thư mục đó sang thư mục mới, giữ nguyên cấu trúc. setup_face_assets.py chuẩn bị model hướng mặt và tài nguyên web; xem thêm employee-registration-implementation.md để đặt model nhận diện. Không cần cài lại installer/payload của bản sửa trước.

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --app-dir app/backend/src --host 127.0.0.1 --port 8000 --reload
```

Đóng server cũ trước khi dùng cổng 8000. Mở http://127.0.0.1:8000/api/health để kiểm tra engine_ready và pose_model_available.

- http://127.0.0.1:8000/enroll.html: tạo tài khoản quản lý đầu tiên trên localhost, quản lý nhân viên và đăng ký mặt.
- http://127.0.0.1:8000/portal.html: dùng cùng tài khoản để phân ca, duyệt phép, xem công và tính lương.
- http://127.0.0.1:8000/kiosk.html: dùng cùng trình duyệt đã đăng nhập; cấp quyền camera/GPS.
- http://127.0.0.1:8000/admin.html: dashboard của main, cần tài khoản HR/manager.

Database mặc định ở data/private/hrm.sqlite3 của thư mục mới. Không trỏ HRM_DB_URL trực tiếp vào database JSON cũ data/live/hrm.sqlite3; hai schema khác nhau.
Đăng ký mặt giữ luồng main: hai mẫu đạt yêu cầu cho mỗi hướng front/left/right/up/down; không dùng form upload 5 ảnh cũ.

## 3. Giữ dữ liệu hiện có

Không tự động sửa database cũ. Dừng cả hai server trước khi sao chép/chuyển dữ liệu.
Nếu đã có database của main và dữ liệu đăng ký mặt ở data/private, sao chép cả thư mục data/private từ dự án cũ sang bản chạy thử TRƯỚC lần khởi động đầu. Giữ bản gốc làm dự phòng.
Ảnh nhận diện cũ trong data/face/raw có thể được main nhập lúc startup; ảnh không đủ điều kiện hoặc nhân viên chưa tồn tại cần đăng ký lại trên enroll.html.

Để đưa lịch ca, nghỉ phép, bảng lương và tài khoản từ database HRM cũ sang bản tích hợp:
1. Khởi động bản tích hợp một lần để tạo schema, rồi dừng server.
2. Chạy xem trước (chỉ đọc nguồn, rollback các thay đổi ở đích):

```powershell
.\.venv\Scripts\python.exe app/backend/scripts/migrate_legacy_hrm.py --source "D:\ZiDan\HRM_Payroll\data\live\hrm.sqlite3"
```

Nếu báo hồ sơ khác nhau, đối chiếu trước. Có thể chọn rõ `--employee-policy keep-main` để giữ tên/chi nhánh/lương của main; dữ liệu lương nháp phải tính lại sau đó. Nhân viên chỉ có ở nguồn được thêm với chức vụ mặc định phuc_vu, chưa có ca mẫu/ngày vào làm: cần hoàn thiện trên enroll.html.
3. Sau khi xem báo cáo, chạy lại thêm `--apply` để ghi. Nếu đã chọn keep-main, giữ tham số đó ở lệnh apply.

```powershell
.\.venv\Scripts\python.exe app/backend/scripts/migrate_legacy_hrm.py --source "D:\ZiDan\HRM_Payroll\data\live\hrm.sqlite3" --apply
```

Script sao lưu database đích trước commit, không sửa nguồn, không nhập phiên đăng nhập đang hoạt động, không ghi đè tài khoản trùng tên. Tài khoản trùng tên vẫn dùng mật khẩu của main. Tài khoản mới nhập giữ mật khẩu cũ qua bộ kiểm tra hash tương thích. Trùng dữ liệu nghiệp vụ khác nội dung sẽ dừng và rollback. Nguồn y hệt đã nhập sẽ không nhập lại.
Lịch sử audit cũ vẫn ở database nguồn, không chuyển vào bảng audit mới; thao tác nhập được ghi trong audit mới.

Tạo thêm tài khoản từ CLI tại thư mục bản tích hợp:

```powershell
.\.venv\Scripts\python.exe app/backend/scripts/create_user.py --username kiosk01 --role kiosk
.\.venv\Scripts\python.exe app/backend/scripts/create_user.py --username nv0002 --role employee --employee-id NV0002
```

Không có mật khẩu mặc định; nhập qua terminal. Hồ sơ nhân viên phải có trước khi liên kết tài khoản.

## 4. Kiểm tra trước khi gộp vào main

```powershell
.\.venv\Scripts\python.exe -m pip install -r app/backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest app/backend/tests -q
node --test app/frontend/tests/face-capture.test.mjs
```

Kết quả kiểm tra bản tích hợp: 42 kiểm thử Python và 5 kiểm thử JavaScript đạt.
Bao gồm đăng ký mặt của main, dùng chung hồ sơ, phân quyền, đi công vào/ra không ghi đôi, thiếu ca không ghi công, tính lương 8 giờ + 1 OT = 475.000 với mức giờ 50.000, thay lương làm vô hiệu bản nháp, khóa kỳ, nghỉ phép, gắn ca cho log cũ, chuyển dữ liệu xem trước/áp dụng/idempotent.
Các bài test dùng database tạm và engine giả lập; không ghi dữ liệu thực của nhóm.
Đã kiểm tra cú pháp JavaScript của Portal/Kiosk. Không chạy được trình duyệt tự động trong môi trường bàn giao vì gói Chromium tải về bị lỗi; webcam/GPS/model thật cần kiểm tra trên máy nhóm.

Kịch bản thực tế: tạo/sửa hồ sơ → đăng ký mặt → phân ca đúng ngày giờ → kiosk IN → Portal hiện thiếu OUT → kiosk OUT → bảng công đủ vào/ra → tính nháp → đối chiếu → chốt → xuất Excel.
Kiểm tra thêm ca đêm, nhiều ca, đi muộn, quên OUT, nhân viên nghỉ việc, mạng/GPS mất, đăng xuất và phân quyền.

## 5. Đưa lên GitHub sau khi nhóm đã kiểm tra

Ở thư mục HRM_Payroll_Integrated:

```powershell
git status
git push -u origin integrate-hrm
```

Tạo Pull Request integrate-hrm → main. Chưa push trực tiếp main. Nếu main có commit mới, cập nhật và xử lý tiếp trên nhánh tích hợp trước khi merge PR.
Giữ database, .venv, models, dữ liệu mặt và bản backup ở máy. Repo nền vốn đã theo dõi một số ảnh mặt; .gitignore không tự bỏ các ảnh đó khỏi lịch sử Git. Nhóm cần kiểm tra riêng trước khi công khai/chia sẻ thêm.
