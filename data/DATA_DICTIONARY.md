# DATA_DICTIONARY

Mô tả cột của các bảng trong `clean/` và `features/`.

## clean/branches

Danh mục 4 chi nhánh (giả định) tại Đà Nẵng

| column | dtype | description | n_missing |
|---|---|---|---|
| branch_id | object | Mã chi nhánh (CN01..CN04) | 0 |
| branch_name | object | Tên chi nhánh | 0 |
| district | object | Quận | 0 |
| lat | float64 | Vĩ độ (của chi nhánh hoặc của lượt quét) | 0 |
| lon | float64 | Kinh độ (của chi nhánh hoặc của lượt quét) | 0 |
| demand_factor | float64 | Hệ số nhu cầu tương đối của chi nhánh | 0 |
| seats | int64 | Số chỗ ngồi | 0 |
| open_time | object | Giờ mở cửa | 0 |
| close_time | object | Giờ đóng cửa | 0 |

## clean/shifts

Danh mục ca làm việc (giờ bắt đầu/kết thúc, giờ công tính lương)

| column | dtype | description | n_missing |
|---|---|---|---|
| shift_id | object | Mã ca làm | 0 |
| shift_name | object | Tên ca làm | 0 |
| contract_type | object | Loại hợp đồng: FT = chính thức, PT = bán thời gian | 0 |
| start_time | object | Giờ bắt đầu ca | 0 |
| end_time | object | Giờ kết thúc ca | 0 |
| paid_hours | float64 | Số giờ công tính lương của ca | 0 |

## clean/holidays

Ngày nghỉ lễ 2025-2026 (Tết, Giỗ Tổ, 30/4, 1/5, Quốc khánh) và cờ đóng cửa

| column | dtype | description | n_missing |
|---|---|---|---|
| date | datetime64[ns] | Ngày | 0 |
| holiday_name | object | Tên ngày lễ | 0 |
| is_closed_for_business | bool | 1 = cửa hàng đóng cửa cả ngày | 0 |
| note | object | Ghi chú | 0 |

## clean/weather_daily

Cờ có mưa theo ngày (mô phỏng theo mùa)

| column | dtype | description | n_missing |
|---|---|---|---|
| date | datetime64[ns] | Ngày | 0 |
| is_rain | int64 | 1 = ngày có mưa | 0 |

## clean/employees

Hồ sơ nhân viên (kể cả người đã nghỉ việc và người được tuyển thay thế)

| column | dtype | description | n_missing |
|---|---|---|---|
| employee_id | object | Mã nhân viên | 0 |
| full_name | object | Họ tên (giả định) | 0 |
| branch_id | object | Mã chi nhánh (CN01..CN04) | 0 |
| role | object | Vai trò: quan_ly/pha_che/thu_ngan/phuc_vu | 0 |
| contract_type | object | Loại hợp đồng: FT = chính thức, PT = bán thời gian | 0 |
| primary_shift | object | Ca làm chính | 0 |
| hire_date | datetime64[ns] | Ngày vào làm | 0 |
| termination_date | datetime64[ns] | Ngày nghỉ việc (rỗng = còn làm) | 48 |
| termination_reason | object | Lý do nghỉ việc | 48 |
| is_student | int64 | 1 = sinh viên | 0 |
| birth_year | int64 | Năm sinh | 0 |
| base_salary | float64 | Lương cơ bản tháng (VND), chỉ FT | 67 |
| hourly_rate | float64 | Lương theo giờ (VND), chỉ PT | 33 |
| is_real_face | int64 | 1 = ô vị trí dành cho thành viên nhóm (sẽ thay bằng dữ liệu khuôn mặt thật) | 0 |
| data_source | object | Nguồn dữ liệu: simulated / real_member_placeholder | 0 |

## clean/leave_requests

Đơn xin nghỉ phép và kết quả duyệt

| column | dtype | description | n_missing |
|---|---|---|---|
| leave_id | object | Mã đơn nghỉ | 0 |
| employee_id | object | Mã nhân viên | 0 |
| branch_id | object | Mã chi nhánh (CN01..CN04) | 0 |
| leave_type | object | Loại nghỉ: phep_nam/om/viec_rieng_khong_luong | 0 |
| start_date | datetime64[ns] | Ngày bắt đầu nghỉ | 0 |
| end_date | datetime64[ns] | Ngày kết thúc nghỉ | 0 |
| days_requested | int64 | Số ngày xin nghỉ | 0 |
| submitted_date | datetime64[ns] | Ngày nộp đơn | 0 |
| status | object | approved / rejected | 0 |

## clean/attendance_events

Lượt quét chấm công thô (khuôn mặt/QR/thủ công), gồm cả lượt bị từ chối và lượt bất thường

| column | dtype | description | n_missing |
|---|---|---|---|
| event_id | int64 | Mã lượt quét | 0 |
| employee_id | object | Mã nhân viên | 0 |
| branch_id | object | Mã chi nhánh (CN01..CN04) | 0 |
| device_id | object | Mã thiết bị chấm công | 0 |
| ts | datetime64[ns] | Thời điểm lượt quét | 0 |
| event_type | object | check_in / check_out | 0 |
| method | object | Phương thức: face / qr / manual | 0 |
| status | object | accepted / rejected (lượt quét bị từ chối) | 0 |
| face_similarity | float64 | Độ giống khuôn mặt (0-1), rỗng nếu không quét mặt | 4333 |
| liveness_score | float64 | Điểm chống giả mạo (0-1, cao = người thật) | 4333 |
| lat | float64 | Vĩ độ (của chi nhánh hoặc của lượt quét) | 0 |
| lon | float64 | Kinh độ (của chi nhánh hoặc của lượt quét) | 0 |
| gps_distance_m | float64 | Khoảng cách từ vị trí quét đến chi nhánh (mét) | 0 |
| is_manual | int64 | 1 = quản lý chấm tay | 0 |

## clean/attendance_daily

Bảng công theo ngày (sự thật nền, không chứa bất thường chèn vào lượt quét)

| column | dtype | description | n_missing |
|---|---|---|---|
| employee_id | object | Mã nhân viên | 0 |
| branch_id | object | Mã chi nhánh (CN01..CN04) | 0 |
| work_date | datetime64[ns] | Ngày làm việc | 0 |
| shift_id | object | Mã ca làm | 0 |
| planned_start | datetime64[ns] | Giờ bắt đầu theo lịch | 0 |
| planned_end | datetime64[ns] | Giờ kết thúc theo lịch | 0 |
| status | object | present / absent_unapproved / leave_annual / leave_sick / leave_unpaid | 0 |
| check_in_ts | datetime64[ns] | Giờ vào thực tế | 1108 |
| check_out_ts | datetime64[ns] | Giờ ra thực tế | 1108 |
| late_minutes | int64 | Số phút đi trễ | 0 |
| early_leave_minutes | int64 | Số phút về sớm | 0 |
| worked_hours | float64 | Tổng giờ có mặt | 1108 |
| regular_hours | float64 | Giờ trong ca | 0 |
| ot_hours | float64 | Giờ tăng ca (làm tròn 0,5 giờ, từ 30 phút) | 0 |
| day_type | object | normal / holiday / rest_extra (làm thêm ngày nghỉ tuần) | 0 |
| is_holiday | int64 | 1 = ngày lễ | 0 |
| is_manual_fix | int64 | 1 = quên chấm ra, quản lý sửa tay | 0 |

## clean/payroll

Bảng lương tháng cho từng nhân viên

| column | dtype | description | n_missing |
|---|---|---|---|
| payroll_id | object | Mã dòng lương | 0 |
| employee_id | object | Mã nhân viên | 0 |
| branch_id | object | Mã chi nhánh (CN01..CN04) | 0 |
| month | object | Kỳ lương YYYY-MM | 0 |
| contract_type | object | Loại hợp đồng: FT = chính thức, PT = bán thời gian | 0 |
| days_scheduled | float64 | Số ngày có lịch | 0 |
| days_worked | float64 | Số ngày đi làm | 0 |
| days_leave_annual | float64 | Ngày phép năm | 0 |
| days_leave_unpaid | float64 | Ngày nghỉ không lương | 0 |
| days_leave_sick | float64 | Ngày nghỉ ốm | 0 |
| days_absent_unapproved | float64 | Ngày vắng không phép | 0 |
| holiday_paid_days | int64 | Số ngày lễ hưởng lương trong tháng | 0 |
| regular_hours_normal | float64 | Giờ trong ca ngày thường | 0 |
| ot_hours_normal | float64 | Giờ tăng ca ngày thường | 0 |
| premium_hours_holiday | float64 | Giờ làm ngày lễ (hệ số 300%) | 0 |
| premium_hours_rest | float64 | Giờ làm ngày nghỉ tuần (hệ số 200%) | 0 |
| late_count | float64 | Số lần trễ quá thời gian ân hạn | 0 |
| late_minutes_deducted | float64 | Số phút trễ bị trừ | 0 |
| base_pay | float64 | Lương theo công | 0 |
| ot_pay | float64 | Tiền tăng ca/làm ngày lễ | 0 |
| late_deduction | float64 | Trừ đi trễ | 0 |
| allowance_meal | float64 | Phụ cấp ăn | 0 |
| allowance_other | float64 | Phụ cấp khác (quản lý) | 0 |
| bonus_attendance | float64 | Thưởng chuyên cần | 0 |
| bonus_sales | float64 | Thưởng đạt doanh số chi nhánh | 0 |
| gross_pay | float64 | Tổng thu nhập | 0 |
| employee_insurance | float64 | Bảo hiểm người lao động đóng | 0 |
| employer_insurance | float64 | Bảo hiểm doanh nghiệp đóng | 0 |
| taxable_income | float64 | Thu nhập tính thuế (sau giảm trừ) | 0 |
| pit | float64 | Thuế thu nhập cá nhân | 0 |
| net_pay | float64 | Thực nhận | 0 |

## clean/branch_sales_hourly

Đơn hàng và doanh thu theo giờ của từng chi nhánh

| column | dtype | description | n_missing |
|---|---|---|---|
| branch_id | object | Mã chi nhánh (CN01..CN04) | 0 |
| date | datetime64[ns] | Ngày bán hàng | 0 |
| hour | int64 | Giờ trong ngày (0-23) | 0 |
| orders | int64 | Số đơn hàng | 0 |
| revenue_vnd | int64 | Doanh thu (VND) | 0 |

## clean/labels_anomaly

Nhãn bất thường theo event_id (chỉ chứa các lượt bất thường)

| column | dtype | description | n_missing |
|---|---|---|---|
| event_id | int64 | Mã lượt quét | 0 |
| anomaly_type | object | Loại bất thường (rỗng = bình thường). KHÔNG đưa vào đặc trưng, đây là nhãn | 0 |

## features/features_anomaly

Đặc trưng cho model phát hiện gian lận chấm công (1 dòng = 1 lượt quét được chấp nhận)

| column | dtype | description | n_missing |
|---|---|---|---|
| event_id | int64 | Mã lượt quét | 0 |
| ts | datetime64[ns] | Thời điểm lượt quét | 0 |
| employee_id | object | Mã nhân viên | 0 |
| branch_id | object | Mã chi nhánh (CN01..CN04) | 0 |
| role | object | Vai trò: quan_ly/pha_che/thu_ngan/phuc_vu | 0 |
| contract_type | object | Loại hợp đồng: FT = chính thức, PT = bán thời gian | 0 |
| tenure_days | int64 | Số ngày đã làm việc | 0 |
| hour | int32 | Giờ của lượt quét | 0 |
| dow | int32 | Thứ trong tuần (0 = Thứ Hai) | 0 |
| is_weekend | int64 | 1 = cuối tuần | 0 |
| is_holiday | int64 | 1 = ngày lễ | 0 |
| event_is_checkout | int64 | 1 = lượt check-out | 0 |
| method_qr | int64 | 1 = quét QR | 0 |
| is_manual | int64 | 1 = quản lý chấm tay | 0 |
| has_face_score | int64 | 1 = có điểm khuôn mặt | 0 |
| face_similarity | float64 | Độ giống khuôn mặt (0-1), rỗng nếu không quét mặt | 4333 |
| liveness_score | float64 | Điểm chống giả mạo (0-1, cao = người thật) | 4333 |
| gps_distance_m | float64 | Khoảng cách từ vị trí quét đến chi nhánh (mét) | 0 |
| scheduled_present | int64 | 1 = hôm đó có lịch và đi làm | 0 |
| minutes_from_plan | float64 | Phút lệch so với giờ theo lịch | 16 |
| secs_since_prev_emp_event | float64 | Giây kể từ lượt quét trước của cùng nhân viên | 100 |
| secs_since_prev_device_event | float64 | Giây kể từ lượt quét trước trên cùng thiết bị | 5 |
| events_same_day_so_far | int64 | Số lượt quét trong ngày tính đến lúc này | 0 |
| minute_dev_vs_own_30 | float64 | Lệch giờ quét so với trung bình 30 lượt gần nhất của chính nhân viên (phút) | 988 |
| minute_z_vs_own_30 | float64 | Z-score của độ lệch trên | 988 |
| sim_dev_vs_own_30 | float64 | Lệch độ giống khuôn mặt so với mức thường ngày | 5317 |
| is_anomaly | int64 | Nhãn: 1 = bất thường | 0 |
| anomaly_type | object | Loại bất thường (rỗng = bình thường). KHÔNG đưa vào đặc trưng, đây là nhãn | 0 |
| split | object | Tập dữ liệu: train / val / test (/ embargo) | 0 |

## features/features_attrition

Đặc trưng cho model dự báo nghỉ việc trong 60 ngày (1 dòng = nhân viên x mốc cuối tháng)

| column | dtype | description | n_missing |
|---|---|---|---|
| snapshot_date | datetime64[ns] | Mốc quan sát (cuối tháng) | 0 |
| employee_id | object | Mã nhân viên | 0 |
| branch_id | object | Mã chi nhánh (CN01..CN04) | 0 |
| role | object | Vai trò: quan_ly/pha_che/thu_ngan/phuc_vu | 0 |
| contract_type | object | Loại hợp đồng: FT = chính thức, PT = bán thời gian | 0 |
| is_student | int64 | 1 = sinh viên | 0 |
| tenure_days | int64 | Số ngày đã làm việc | 0 |
| wage_ratio | float64 | Lương / lương trung vị cùng vai trò và loại hợp đồng | 0 |
| sched_90d | int64 | Số ngày có lịch trong 90 ngày | 0 |
| present_90d | int64 | Số ngày đi làm trong 90 ngày | 0 |
| late_rate_90d | float64 | Tỷ lệ đi trễ 90 ngày | 0 |
| late_rate_30d | float64 | Tỷ lệ đi trễ 30 ngày | 0 |
| avg_late_minutes_90d | float64 | Số phút trễ trung bình 90 ngày | 0 |
| absent_90d | int64 | Số ngày vắng không phép 90 ngày | 0 |
| leave_days_90d | int64 | Số ngày nghỉ phép 90 ngày | 0 |
| ot_hours_90d | float64 | Giờ tăng ca 90 ngày | 0 |
| avg_weekly_hours_90d | float64 | Giờ làm trung bình mỗi tuần | 0 |
| manual_fix_90d | int64 | Số lần phải sửa công tay | 0 |
| branch_turnover_90d | float64 | Tỷ lệ nghỉ việc của chi nhánh trong 90 ngày | 0 |
| month_of_year | int64 | Tháng trong năm | 0 |
| is_real_face | int64 | 1 = ô vị trí dành cho thành viên nhóm (sẽ thay bằng dữ liệu khuôn mặt thật) | 0 |
| left_next_60d | int64 | Nhãn: 1 = nghỉ việc trong 60 ngày sau mốc quan sát | 0 |
| split | object | Tập dữ liệu: train / val / test (/ embargo) | 0 |

## features/features_staffing_hourly

Đặc trưng cho model dự báo nhu cầu nhân sự theo giờ

| column | dtype | description | n_missing |
|---|---|---|---|
| branch_id | object | Mã chi nhánh (CN01..CN04) | 0 |
| date | datetime64[ns] | Ngày | 0 |
| hour | int64 | Giờ bán hàng | 0 |
| dow | int32 | Thứ trong tuần (0 = Thứ Hai) | 0 |
| month | int32 | Tháng trong năm | 0 |
| is_holiday | int64 | 1 = ngày lễ | 0 |
| is_rain | int64 | 1 = ngày có mưa | 0 |
| orders_lag_7d | float64 | Số đơn cùng giờ cách 7 ngày | 1156 |
| scheduled_staff | float64 | Số người theo lịch (quy đổi theo giờ) | 0 |
| present_staff | float64 | Số người có mặt thực tế (quy đổi theo giờ) | 0 |
| orders | int64 | Số đơn hàng | 0 |
| revenue_vnd | int64 | Doanh thu (VND) | 0 |
| required_staff_est | int64 | Số người cần ước tính từ số đơn | 0 |
| orders_per_present_staff | float64 | Số đơn trên mỗi người có mặt | 251 |
| split | object | Tập dữ liệu: train / val / test (/ embargo) | 0 |
