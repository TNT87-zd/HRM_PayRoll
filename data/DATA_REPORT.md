# DATA_REPORT

- Chuỗi: Cafe 2TNQC; giai đoạn 2024-10-01 → 2026-09-30; seed 42.
- Đây là dữ liệu MÔ PHỎNG; tên người và các tham số lương/bảo hiểm/thuế là giả định phục vụ đồ án.

## 1. Số dòng, số cột

| nhóm | bảng | số dòng | số cột |
|---|---|---|---|
| clean | branches | 4 | 9 |
| clean | shifts | 6 | 6 |
| clean | holidays | 23 | 4 |
| clean | weather_daily | 730 | 2 |
| clean | employees | 100 | 15 |
| clean | leave_requests | 820 | 9 |
| clean | attendance_events | 52,754 | 14 |
| clean | attendance_daily | 26,361 | 17 |
| clean | payroll | 1,267 | 31 |
| clean | branch_sales_hourly | 48,960 | 5 |
| clean | labels_anomaly | 653 | 2 |
| features | features_anomaly | 50,838 | 29 |
| features | features_attrition | 4,416 | 23 |
| features | features_staffing_hourly | 48,960 | 15 |

## 2. Tỷ lệ thiếu

| bảng | cột | % thiếu |
|---|---|---|
| employees | termination_date | 48.0% |
| employees | termination_reason | 48.0% |
| employees | base_salary | 67.0% |
| employees | hourly_rate | 33.0% |
| attendance_events | face_similarity | 8.2% |
| attendance_events | liveness_score | 8.2% |
| attendance_daily | check_in_ts | 4.2% |
| attendance_daily | check_out_ts | 4.2% |
| attendance_daily | worked_hours | 4.2% |
| features_anomaly | face_similarity | 8.5% |
| features_anomaly | liveness_score | 8.5% |
| features_anomaly | minutes_from_plan | 0.0% |
| features_anomaly | secs_since_prev_emp_event | 0.2% |
| features_anomaly | secs_since_prev_device_event | 0.0% |
| features_anomaly | minute_dev_vs_own_30 | 1.9% |
| features_anomaly | minute_z_vs_own_30 | 1.9% |
| features_anomaly | sim_dev_vs_own_30 | 10.5% |
| features_staffing_hourly | orders_lag_7d | 2.4% |
| features_staffing_hourly | orders_per_present_staff | 0.5% |

Phần lớn giá trị thiếu là có chủ đích (chưa nghỉ việc, chỉ FT có lương tháng / chỉ PT có lương giờ, lượt QR hoặc chấm tay không có điểm khuôn mặt, ngày nghỉ không có giờ vào/ra).

## 3. Phân phối

### 3.1 Biến số

| bảng | cột | mean | std | min | median | max |
|---|---|---|---|---|---|---|
| branches | lat | 16.05 | 0.03 | 16.0 | 16.06 | 16.07 |
| branches | lon | 108.23 | 0.03 | 108.19 | 108.23 | 108.26 |
| branches | demand_factor | 0.94 | 0.21 | 0.7 | 0.92 | 1.2 |
| branches | seats | 31.0 | 6.83 | 24.0 | 30.0 | 40.0 |
| shifts | paid_hours | 6.67 | 1.47 | 5.0 | 6.75 | 8.0 |
| weather_daily | is_rain | 0.2 | 0.4 | 0.0 | 0.0 | 1.0 |
| employees | is_student | 0.52 | 0.5 | 0.0 | 1.0 | 1.0 |
| employees | birth_year | 2001.27 | 4.01 | 1993.0 | 2002.0 | 2007.0 |
| employees | base_salary | 8600000.0 | 1936007.49 | 6600000.0 | 8000000.0 | 14000000.0 |
| employees | hourly_rate | 28604.48 | 1945.35 | 26000.0 | 28000.0 | 33500.0 |
| employees | is_real_face | 0.05 | 0.22 | 0.0 | 0.0 | 1.0 |
| leave_requests | days_requested | 1.46 | 0.67 | 1.0 | 1.0 | 3.0 |
| attendance_events | face_similarity | 0.73 | 0.09 | 0.3 | 0.74 | 0.99 |
| attendance_events | liveness_score | 0.91 | 0.06 | 0.05 | 0.92 | 1.0 |
| attendance_events | lat | 16.05 | 0.03 | 15.96 | 16.07 | 16.14 |
| attendance_events | lon | 108.23 | 0.03 | 108.13 | 108.22 | 108.3 |
| attendance_events | gps_distance_m | 14.71 | 220.59 | 0.0 | 4.1 | 7924.0 |
| attendance_events | is_manual | 0.01 | 0.08 | 0.0 | 0.0 | 1.0 |
| attendance_daily | late_minutes | 2.19 | 6.05 | 0.0 | 0.0 | 90.0 |
| attendance_daily | early_leave_minutes | 1.03 | 1.98 | 0.0 | 0.0 | 15.0 |
| attendance_daily | worked_hours | 7.17 | 1.58 | 3.41 | 7.93 | 10.81 |
| attendance_daily | regular_hours | 6.59 | 1.97 | 0.0 | 7.85 | 9.0 |
| attendance_daily | ot_hours | 0.14 | 0.34 | 0.0 | 0.0 | 1.5 |
| attendance_daily | is_holiday | 0.02 | 0.13 | 0.0 | 0.0 | 1.0 |
| attendance_daily | is_manual_fix | 0.01 | 0.1 | 0.0 | 0.0 | 1.0 |
| payroll | days_scheduled | 20.81 | 5.62 | 0.0 | 20.0 | 29.0 |
| payroll | days_worked | 19.93 | 5.52 | 0.0 | 20.0 | 29.0 |
| payroll | days_leave_annual | 0.22 | 0.62 | 0.0 | 0.0 | 5.0 |
| payroll | days_leave_unpaid | 0.34 | 0.74 | 0.0 | 0.0 | 5.0 |
| payroll | days_leave_sick | 0.21 | 0.57 | 0.0 | 0.0 | 4.0 |
| payroll | days_absent_unapproved | 0.1 | 0.33 | 0.0 | 0.0 | 3.0 |
| payroll | holiday_paid_days | 0.93 | 1.46 | 0.0 | 0.0 | 5.0 |
| payroll | regular_hours_normal | 133.78 | 59.91 | 0.0 | 104.29 | 242.23 |
| payroll | ot_hours_normal | 2.92 | 2.5 | 0.0 | 2.5 | 12.5 |
| payroll | premium_hours_holiday | 2.39 | 4.86 | 0.0 | 0.0 | 28.38 |
| payroll | premium_hours_rest | 0.99 | 3.12 | 0.0 | 0.0 | 24.94 |
| payroll | late_count | 2.75 | 3.5 | 0.0 | 2.0 | 24.0 |
| payroll | late_minutes_deducted | 20.14 | 33.84 | 0.0 | 6.0 | 278.0 |
| payroll | base_pay | 5063527.23 | 3273548.15 | 0.0 | 3069000.0 | 14000000.0 |
| payroll | ot_pay | 509913.97 | 756468.13 | 0.0 | 184000.0 | 6419000.0 |
| payroll | late_deduction | 8751.38 | 21954.15 | 0.0 | 0.0 | 180000.0 |
| payroll | allowance_meal | 336913.97 | 372672.59 | 0.0 | 0.0 | 870000.0 |
| payroll | allowance_other | 37884.77 | 132366.75 | 0.0 | 0.0 | 500000.0 |
| payroll | bonus_attendance | 44514.6 | 106685.58 | 0.0 | 0.0 | 300000.0 |
| payroll | bonus_sales | 50749.8 | 75658.18 | 0.0 | 0.0 | 200000.0 |
| payroll | gross_pay | 6034766.38 | 4213248.68 | 0.0 | 3340000.0 | 20461000.0 |
| payroll | employee_insurance | 395685.87 | 465400.58 | 0.0 | 0.0 | 1470000.0 |
| payroll | employer_insurance | 810312.55 | 953084.71 | 0.0 | 0.0 | 3010000.0 |
| payroll | taxable_income | 129140.49 | 649887.1 | 0.0 | 0.0 | 5876000.0 |
| payroll | pit | 6534.33 | 33157.64 | 0.0 | 0.0 | 338000.0 |
| payroll | net_pay | 5632520.92 | 3752724.57 | 0.0 | 3340000.0 | 18836000.0 |
| branch_sales_hourly | hour | 14.0 | 4.9 | 6.0 | 14.0 | 22.0 |
| branch_sales_hourly | orders | 14.91 | 7.52 | 0.0 | 14.0 | 63.0 |
| branch_sales_hourly | revenue_vnd | 716759.11 | 375591.26 | 0.0 | 667000.0 | 3605000.0 |
| features_anomaly | tenure_days | 625.38 | 460.0 | 0.0 | 527.0 | 1823.0 |
| features_anomaly | hour | 13.64 | 5.4 | 1.0 | 14.0 | 23.0 |
| features_anomaly | dow | 3.19 | 2.05 | 0.0 | 3.0 | 6.0 |
| features_anomaly | is_weekend | 0.34 | 0.47 | 0.0 | 0.0 | 1.0 |
| features_anomaly | is_holiday | 0.02 | 0.13 | 0.0 | 0.0 | 1.0 |
| features_anomaly | event_is_checkout | 0.5 | 0.5 | 0.0 | 0.0 | 1.0 |
| features_anomaly | method_qr | 0.08 | 0.27 | 0.0 | 0.0 | 1.0 |
| features_anomaly | is_manual | 0.01 | 0.08 | 0.0 | 0.0 | 1.0 |
| features_anomaly | has_face_score | 0.91 | 0.28 | 0.0 | 1.0 | 1.0 |
| features_anomaly | face_similarity | 0.74 | 0.07 | 0.45 | 0.74 | 0.99 |
| features_anomaly | liveness_score | 0.91 | 0.06 | 0.05 | 0.92 | 1.0 |
| features_anomaly | gps_distance_m | 15.11 | 224.7 | 0.0 | 4.1 | 7924.0 |
| features_anomaly | scheduled_present | 1.0 | 0.02 | 0.0 | 1.0 | 1.0 |
| features_anomaly | minutes_from_plan | 4.15 | 37.68 | -1251.0 | 0.1 | 99.0 |
| features_anomaly | secs_since_prev_emp_event | 62900.89 | 68598.31 | 1.01 | 34589.91 | 929523.53 |
| features_anomaly | secs_since_prev_device_event | 6194.45 | 25106.33 | 0.0 | 626.94 | 1468800.0 |
| features_anomaly | events_same_day_so_far | 1.52 | 0.55 | 1.0 | 2.0 | 7.0 |
| features_anomaly | minute_dev_vs_own_30 | 0.19 | 133.61 | -1228.6 | -3.0 | 690.3 |
| features_anomaly | minute_z_vs_own_30 | 0.03 | 6.04 | -213.98 | -0.08 | 220.0 |
| features_anomaly | sim_dev_vs_own_30 | -0.0 | 0.06 | -0.33 | 0.0 | 0.26 |
| features_anomaly | is_anomaly | 0.01 | 0.11 | 0.0 | 0.0 | 1.0 |
| features_attrition | is_student | 0.4 | 0.49 | 0.0 | 0.0 | 1.0 |
| features_attrition | tenure_days | 598.29 | 440.22 | 0.0 | 501.0 | 1757.0 |
| features_attrition | wage_ratio | 1.0 | 0.07 | 0.8 | 1.0 | 1.13 |
| features_attrition | sched_90d | 60.52 | 17.0 | 1.0 | 58.0 | 81.0 |
| features_attrition | present_90d | 57.93 | 16.51 | 0.0 | 56.0 | 80.0 |
| features_attrition | late_rate_90d | 0.14 | 0.16 | 0.0 | 0.09 | 1.0 |
| features_attrition | late_rate_30d | 0.14 | 0.17 | 0.0 | 0.08 | 1.0 |
| features_attrition | avg_late_minutes_90d | 2.25 | 2.31 | 0.0 | 1.67 | 30.5 |
| features_attrition | absent_90d | 0.3 | 0.6 | 0.0 | 0.0 | 4.0 |
| features_attrition | leave_days_90d | 2.29 | 1.97 | 0.0 | 2.0 | 13.0 |
| features_attrition | ot_hours_90d | 8.91 | 6.56 | 0.0 | 7.0 | 32.5 |
| features_attrition | avg_weekly_hours_90d | 33.9 | 13.75 | 0.0 | 25.32 | 67.48 |
| features_attrition | manual_fix_90d | 0.63 | 0.82 | 0.0 | 0.0 | 4.0 |
| features_attrition | branch_turnover_90d | 0.12 | 0.12 | 0.0 | 0.08 | 0.55 |
| features_attrition | month_of_year | 5.99 | 3.44 | 1.0 | 6.0 | 12.0 |
| features_attrition | is_real_face | 0.1 | 0.3 | 0.0 | 0.0 | 1.0 |
| features_attrition | left_next_60d | 0.06 | 0.24 | 0.0 | 0.0 | 1.0 |
| features_staffing_hourly | hour | 14.0 | 4.9 | 6.0 | 14.0 | 22.0 |
| features_staffing_hourly | dow | 3.0 | 2.0 | 0.0 | 3.0 | 6.0 |
| features_staffing_hourly | month | 6.59 | 3.42 | 1.0 | 7.0 | 12.0 |
| features_staffing_hourly | is_holiday | 0.02 | 0.13 | 0.0 | 0.0 | 1.0 |
| features_staffing_hourly | is_rain | 0.2 | 0.4 | 0.0 | 0.0 | 1.0 |
| features_staffing_hourly | orders_lag_7d | 14.95 | 7.54 | 0.0 | 14.0 | 63.0 |
| features_staffing_hourly | scheduled_staff | 3.73 | 1.72 | 0.0 | 4.0 | 11.0 |
| features_staffing_hourly | present_staff | 3.68 | 1.7 | 0.0 | 3.71 | 11.61 |
| features_staffing_hourly | orders | 14.91 | 7.52 | 0.0 | 14.0 | 63.0 |
| features_staffing_hourly | revenue_vnd | 716759.11 | 375591.26 | 0.0 | 667000.0 | 3605000.0 |
| features_staffing_hourly | required_staff_est | 3.02 | 1.13 | 2.0 | 3.0 | 11.0 |
| features_staffing_hourly | orders_per_present_staff | 4.99 | 8.84 | 0.0 | 4.0 | 1300.0 |

### 3.2 Biến phân loại (tối đa 8 giá trị)

| bảng | cột | phân phối |
|---|---|---|
| branches | branch_id | CN01: 25.0%; CN02: 25.0%; CN03: 25.0%; CN04: 25.0% |
| branches | branch_name | Chi nhánh Hải Châu: 25.0%; Chi nhánh Thanh Khê: 25.0%; Chi nhánh Sơn Trà: 25.0%; Chi nhánh Ngũ Hành Sơn: 25.0% |
| branches | district | Hải Châu: 25.0%; Thanh Khê: 25.0%; Sơn Trà: 25.0%; Ngũ Hành Sơn: 25.0% |
| shifts | shift_id | CA_SANG: 16.7%; CA_CHIEU: 16.7%; HANH_CHINH: 16.7%; PT_SANG: 16.7%; PT_CHIEU: 16.7%; PT_TOI: 16.7% |
| shifts | shift_name | Ca sáng: 16.7%; Ca chiều: 16.7%; Hành chính (quản lý): 16.7%; Bán thời gian - sáng: 16.7%; Bán thời gian - chiều: 16.7%; Bán thời gian - tối: 16.7% |
| shifts | contract_type | FT: 50.0%; PT: 50.0% |
| shifts | start_time | 06:30: 33.3%; 14:30: 16.7%; 08:00: 16.7%; 12:00: 16.7%; 17:30: 16.7% |
| shifts | end_time | 22:30: 33.3%; 14:30: 16.7%; 17:00: 16.7%; 12:00: 16.7%; 17:30: 16.7% |
| employees | branch_id | CN03: 27.0%; CN04: 26.0%; CN01: 25.0%; CN02: 22.0% |
| employees | role | pha_che: 39.0%; phuc_vu: 36.0%; thu_ngan: 20.0%; quan_ly: 5.0% |
| employees | contract_type | PT: 67.0%; FT: 33.0% |
| employees | primary_shift | PT_TOI: 25.0%; PT_CHIEU: 21.0%; PT_SANG: 21.0%; CA_SANG: 17.0%; CA_CHIEU: 11.0%; HANH_CHINH: 5.0% |
| employees | termination_reason | nghi_viec_tu_nguyen: 88.5%; het_hop_dong: 7.7%; cho_thoi_viec: 3.8% |
| employees | data_source | simulated: 95.0%; real_member_placeholder: 5.0% |
| leave_requests | branch_id | CN03: 26.8%; CN04: 24.6%; CN01: 24.3%; CN02: 24.3% |
| leave_requests | leave_type | viec_rieng_khong_luong: 45.1%; om: 27.4%; phep_nam: 27.4% |
| leave_requests | status | approved: 92.9%; rejected: 7.1% |
| attendance_events | branch_id | CN02: 25.4%; CN01: 25.1%; CN04: 24.9%; CN03: 24.7% |
| attendance_events | device_id | CN02-TB01: 25.2%; CN01-TB01: 24.9%; CN04-TB01: 24.7%; CN03-TB01: 24.6%; MANAGER_PORTAL: 0.5% |
| attendance_events | event_type | check_out: 50.0%; check_in: 50.0% |
| attendance_events | method | face: 91.8%; qr: 7.7%; manual: 0.5% |
| attendance_events | status | accepted: 96.4%; rejected: 3.6% |
| attendance_daily | branch_id | CN02: 25.4%; CN01: 25.1%; CN03: 24.9%; CN04: 24.7% |
| attendance_daily | shift_id | CA_SANG: 27.6%; CA_CHIEU: 19.3%; PT_CHIEU: 16.2%; PT_TOI: 14.0%; PT_SANG: 13.5%; HANH_CHINH: 9.4% |
| attendance_daily | status | present: 95.8%; leave_unpaid: 1.6%; leave_annual: 1.1%; leave_sick: 1.0%; absent_unapproved: 0.5% |
| attendance_daily | day_type | normal: 97.7%; holiday: 1.7%; rest_extra: 0.6% |
| payroll | branch_id | CN03: 25.2%; CN01: 25.1%; CN02: 24.9%; CN04: 24.9% |
| payroll | contract_type | PT: 54.3%; FT: 45.7% |
| branch_sales_hourly | branch_id | CN01: 25.0%; CN02: 25.0%; CN03: 25.0%; CN04: 25.0% |
| labels_anomaly | anomaly_type | burst_duplicate: 43.3%; gps_mismatch: 17.2%; long_session: 11.0%; spoof_attempt: 10.9%; low_similarity_manual: 10.1%; off_hours: 7.5% |
| features_anomaly | branch_id | CN02: 25.4%; CN01: 25.1%; CN03: 24.8%; CN04: 24.6% |
| features_anomaly | role | pha_che: 40.7%; phuc_vu: 25.0%; thu_ngan: 24.9%; quan_ly: 9.4% |
| features_anomaly | contract_type | FT: 56.3%; PT: 43.7% |
| features_anomaly | anomaly_type | : 98.7%; burst_duplicate: 0.6%; gps_mismatch: 0.2%; long_session: 0.1%; spoof_attempt: 0.1%; low_similarity_manual: 0.1%; off_hours: 0.1% |
| features_anomaly | split | train: 62.6%; val: 20.4%; test: 17.0% |
| features_attrition | branch_id | CN02: 25.3%; CN01: 24.9%; CN03: 24.9%; CN04: 24.8% |
| features_attrition | role | pha_che: 38.3%; phuc_vu: 30.5%; thu_ngan: 23.3%; quan_ly: 7.8% |
| features_attrition | contract_type | PT: 53.2%; FT: 46.8% |
| features_attrition | split | train: 55.1%; embargo: 20.5%; test: 15.1%; val: 9.3% |
| features_staffing_hourly | branch_id | CN01: 25.0%; CN02: 25.0%; CN03: 25.0%; CN04: 25.0% |
| features_staffing_hourly | split | train: 62.8%; val: 20.3%; test: 16.9% |

## 4. Cách làm sạch (raw → clean)

- Đọc CSV từ `raw/`, ép kiểu ngày/giờ, cắt khoảng trắng ở cột chữ.
- Xóa dòng trùng hoàn toàn ở mọi bảng, TRỪ `attendance_events`: các lượt quét trùng (`burst_duplicate`) là bất thường có nhãn để model học, nên giữ lại và để model phát hiện.
- Không điền giá trị thiếu và không loại ngoại lai: các bất thường được gắn nhãn thay vì bị xóa.

| bảng | dòng raw | dòng sau làm sạch | dòng bị loại |
|---|---|---|---|
| branches | 4 | 4 | 0 |
| shifts | 6 | 6 | 0 |
| holidays | 23 | 23 | 0 |
| weather_daily | 730 | 730 | 0 |
| employees | 100 | 100 | 0 |
| leave_requests | 820 | 820 | 0 |
| attendance_events | 52754 | 52754 | 0 |
| attendance_daily | 26361 | 26361 | 0 |
| payroll | 1267 | 1267 | 0 |
| branch_sales_hourly | 48960 | 48960 | 0 |
| labels_anomaly | 653 | 653 | 0 |

## 5. Chia tập (theo thời gian, không xáo trộn)

| bảng | split | số dòng | mẫu dương | tỷ lệ dương |
|---|---|---|---|---|
| features_anomaly | test | 8,641 | 107 | 1.24% |
| features_anomaly | train | 31,826 | 400 | 1.26% |
| features_anomaly | val | 10,371 | 146 | 1.41% |
| features_attrition | embargo | 907 | 48 | 5.29% |
| features_attrition | test | 667 | 35 | 5.25% |
| features_attrition | train | 2,433 | 136 | 5.59% |
| features_attrition | val | 409 | 41 | 10.02% |
| features_staffing_hourly | test | 8,296 | - | - |
| features_staffing_hourly | train | 30,736 | - | - |
| features_staffing_hourly | val | 9,928 | - | - |

## 6. Kiểm tra toàn vẹn

Đạt 30/30 kiểm tra.

| check | passed | detail |
|---|---|---|
| employee_id là duy nhất | ĐẠT |  |
| event_id là duy nhất | ĐẠT |  |
| payroll: (employee_id, month) là duy nhất | ĐẠT |  |
| attendance_daily: (employee_id, work_date) là duy nhất | ĐẠT |  |
| FK employee_id trong attendance_daily | ĐẠT |  |
| FK branch_id trong attendance_daily | ĐẠT |  |
| FK employee_id trong attendance_events | ĐẠT |  |
| FK branch_id trong attendance_events | ĐẠT |  |
| FK employee_id trong payroll | ĐẠT |  |
| FK branch_id dalam payroll | ĐẠT |  |
| FK employee_id trong leave_requests | ĐẠT |  |
| FK branch_id trong leave_requests | ĐẠT |  |
| FK shift_id trong attendance_daily | ĐẠT |  |
| labels_anomaly ⊂ attendance_events | ĐẠT |  |
| số nhãn bất thường khớp features_anomaly | ĐẠT | 653 vs 653 |
| ngày present đều có giờ vào/ra | ĐẠT |  |
| giờ ra > giờ vào | ĐẠT |  |
| late/early/ot không âm | ĐẠT |  |
| giờ tăng ca là bội số của 0,5 | ĐẠT |  |
| không có ngày công ngoài thời gian làm việc của nhân viên | ĐẠT | vi phạm: 0 |
| không có ngày công vào ngày đóng cửa | ĐẠT |  |
| gross_pay, net_pay >= 0 | ĐẠT | net<0: 0 |
| net = gross - bảo hiểm - thuế (sai số làm tròn <= 2.000đ) | ĐẠT | sai lệch lớn nhất 1,000 |
| PT không có bảo hiểm và thuế | ĐẠT |  |
| FT có base_salary, PT có hourly_rate | ĐẠT |  |
| features_anomaly: train < val < test theo thời gian | ĐẠT |  |
| features_attrition: train < val < test theo mốc | ĐẠT |  |
| mỗi tập anomaly đều có mẫu dương | ĐẠT | {'test': 107, 'train': 400, 'val': 146} |
| mỗi tập attrition đều có mẫu dương | ĐẠT | {'embargo': 48, 'test': 35, 'train': 136, 'val': 41} |
| tỷ lệ bất thường trong khoảng 0,5%-3% | ĐẠT | 0.0128 |