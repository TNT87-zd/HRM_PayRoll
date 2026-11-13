# Dữ liệu của HRM hiện tại

## Nguồn chính
- SQLite: `Settings().database_url`; mặc định `data/private/hrm.sqlite3`.
- `attendance_records`: từng lượt quét IN/OUT. `timestamp` là Unix giây UTC.
- `attendance_assignments`: liên kết `attendance_id` với ca; có nguồn và lý do.
- `hrm_records`: lịch ca (`kind=shifts`), nghỉ phép (`leaves`), kỳ lương (`payroll`), lịch sử tính (`payroll_runs`), cấu hình kỳ (`payroll_config`).
- `employees`: hồ sơ đang sử dụng. `clean/employees.csv` chỉ là danh sách khởi tạo một lần, không tự cập nhật SQLite khi sửa CSV.

## Danh mục đang sử dụng
`clean/branches.csv`, `devices.csv`, `shifts.csv` vẫn giữ nguyên theo bản gửi.
`shifts.csv` là danh mục 5 loại ca; ca phân công theo ngày nằm trong SQLite, không phải tệp này.
Mã ca chính cũ trong hồ sơ nhân viên không được tự chuyển sang ca khác. Khi sửa hồ sơ trên trang đăng ký, chọn lại một trong 5 ca hiện có; lịch ca theo ngày mới là đầu vào tính công.

## Lưu lịch sử và xuất tháng
- `legacy_dataset/raw/`, `legacy_dataset/clean/`: bản dữ liệu cũ được bảo toàn; không dùng làm bảng công/lương trực tiếp. Dữ liệu doanh thu, thời tiết, nhãn bất thường chỉ thuộc bộ nghiên cứu cũ.
- `raw/operational/YYYY-MM/<snapshot>/`: lượt quét, liên kết ca, lịch ca, nhân viên hiện tại, nghỉ phép.
- `clean/operational/YYYY-MM/<snapshot>/`: công tính theo cùng `core.timesheet` của Portal; lượt chưa gắn ca; kỳ lương đã lưu.
- `reports/payroll/YYYY-MM/<run_id>/draft hoặc finalized/`: báo cáo Excel/JSON do chức năng tính/chốt lương hiện tại lưu.

Chạy từ gốc dự án:
```powershell
.\.venv\Scripts\python.exe .\app\backend\scripts\export_month.py --month 2026-11
```
Xuất là thao tác đọc CSDL, không tạo ca, không giả lập lượt quét, không tính/chốt lương và không sửa lịch sử. Mỗi lần xuất tạo thư mục mới để kiểm tra lại. Khi chấm công thêm, Portal đọc CSDL; muốn CSV mới thì chạy lại lệnh này. Không cần tạo hàm riêng theo tháng.

`raw/attendance_events.csv` trong snapshot chứa cả lượt chưa gắn ca và OUT đầu tháng sau của ca cuối tháng. Cột `calendar_month` là tháng thực tế quét; `work_month` là tháng ca được phân công. Không cộng toàn bộ các snapshot với nhau vì chúng là các bản chụp, không phải các đợt dữ liệu mới.
`clean/attendance_daily.csv` chỉ tính ca của tháng đã chọn, giống Portal. `unassigned_events.csv` cần quản lý đối soát/gắn ca trước khi tính lương.
Nguồn `GENERATED_TEST` của dữ liệu tháng 10 được giữ nguyên. Không được coi nó là lượt chấm công thực tế.
`payroll.csv` lấy kỳ lương đã lưu, không tự tính lại từ công mới; kiểm tra trạng thái `draft/finalized` và thời điểm trong `manifest.json`/`payroll_saved.json`. Nếu chưa tính, CSV chỉ có tiêu đề và trạng thái `NOT_CALCULATED`, không phải lương 0.

Các tệp CSV có UTF-8 BOM để mở Excel tiếng Việt; ô chuỗi có dấu công thức được bảo vệ. Đây là tệp đối soát, không phải định dạng nhập lại CSDL.

## Xem trực tiếp SQLite
Dùng phần mềm duyệt SQLite ở chế độ chỉ đọc, mở đúng đường dẫn in ra từ lệnh xuất. Xem bảng `attendance_records` và `attendance_assignments`. Không có bảng SQLite `attendance_daily`/`attendance_events` trong phiên bản models.py đã gửi; đó là tên CSV.
Truy vấn tháng 11 theo giờ Việt Nam:
```sql
SELECT r.id, r.employee_id, r.device_id, r.scan_type,
       datetime(r.timestamp, 'unixepoch', '+7 hours') AS scan_time_vn,
       a.event_id, a.shift_id, a.source, a.reason
FROM attendance_records AS r
LEFT JOIN attendance_assignments AS a ON a.attendance_id = r.id
WHERE r.timestamp >= strftime('%s', '2026-11-01T00:00:00+07:00') + 0
  AND r.timestamp <  strftime('%s', '2026-12-01T00:00:00+07:00') + 0
ORDER BY r.timestamp, r.id;
```
Đây là lọc theo thời điểm quét. Công theo tháng ca vẫn do Portal tính (có thể chứa OUT đầu tháng sau).

## Script nghiên cứu cũ
`preprocess.py` và `build_data_folder.py` bị chặn ghi vào thư mục data hoạt động. Đích mặc định mới là `data/legacy_dataset`. Bộ sinh cũ và tính lương cũ chỉ phục vụ nghiên cứu; không được dùng chúng để sửa công hoặc tính lương cho CSDL. Bản vá này không nâng cấp mô hình ML hoặc luật tính lương của bộ nghiên cứu.
