**Đăng ký nhân viên và quét khuôn mặt — hướng dẫn triển khai**

Bản triển khai ngày 03/11/2026 dùng FastAPI, SQLite/SQLAlchemy, ArcFace ONNX và MediaPipe Face Landmarker. Luồng chính ở `/enroll.html`: tạo hồ sơ → xác nhận đồng ý → quét liên tục năm hướng → backend kiểm tra 10 mẫu → hoàn tất → quét thử. Phần tăng cường ảnh đang giữ baseline; có công cụ thử nghiệm riêng, không bật đồng loạt các bộ lọc.

**Chạy ứng dụng**

Từ thư mục gốc dự án:

```sh
.venv/bin/python -m pip install -r app/backend/requirements.txt
.venv/bin/python app/backend/scripts/setup_face_assets.py
./run.sh
```

Mở [trang đăng ký](http://127.0.0.1:8000/enroll.html). Lần đầu tạo tài khoản quản lý tại localhost, mật khẩu ít nhất 12 ký tự. Tài khoản được lưu dưới dạng hash; phiên đăng nhập dùng cookie HttpOnly, SameSite=Strict và có hạn sử dụng. Không có mật khẩu mặc định. API hồ sơ/ảnh/phiên yêu cầu quyền HR hoặc manager; chức vụ nhân viên tách khỏi quyền truy cập.

Model ArcFace/SCRFD cần có ở `models/insightface/models/buffalo_l/` hoặc thư mục `INSIGHTFACE_ROOT` hiện có. Ứng dụng không tự tải bộ model này khi khởi động. Script setup tải model landmark phiên bản 1 và MediaPipe Web 1.2.0, có kiểm tra TLS và lưu checksum; các tài nguyên được phục vụ tại cùng máy chủ lúc quét, không gọi CDN. Backend cần MediaPipe Python 0.10.35. Trên macOS, MediaPipe có thể cần dịch vụ đồ họa của phiên desktop ngay cả khi delegate CPU; kiểm tra model thật ngoài sandbox không có dịch vụ này.

Triển khai một worker nhận diện. Dùng HTTPS cho camera trên thiết bị khác và bật `HRM_SECURE_COOKIE=1` khi phục vụ qua HTTPS. Nếu reverse proxy, cấu hình địa chỉ/Host đúng; tài khoản đầu tiên được tạo trực tiếp qua localhost.

**Cấu hình và dữ liệu**

| Biến | Mặc định/mục đích |
|---|---|
| `HRM_DATA_DIR` | `data/` tại gốc dự án; đọc CSV tham chiếu và dữ liệu cũ |
| `HRM_STORAGE_DIR` | `data/private/`; DB và ảnh riêng tư |
| `HRM_DB_URL` | SQLite trong private storage; có thể chỉ định đường dẫn SQLite riêng |
| `HRM_FACE_THRESHOLD` | `0.55`, ngưỡng baseline cần hiệu chỉnh bằng dữ liệu độc lập |
| `HRM_FACE_MIN_MARGIN` | `0.08`, độ cách biệt giữa hai danh tính đứng đầu |
| `HRM_SECURE_COOKIE` | `0` cho localhost; đặt `1` khi dùng HTTPS |

Lần khởi động đầu, CSV nhân viên được nhập một lần, ghi báo cáo vào `migration_records`. Tạo/sửa nhân viên sau đó ghi vào SQLite. Bộ ảnh FaceID cũ được kiểm tra bằng FaceEngine rồi nhập một lần vào template, giữ nhãn `legacy`; các file gốc không bị ghi đè. Nhân viên có thể đăng ký lại để có 10 mẫu theo quy trình mới.

Ảnh mới lưu ở vùng staging theo UUID; chỉ sau commit mới chuyển vào phiên bản chính thức. SQLite lưu cả 10 vector mẫu và centroid, mỗi vector 512 phần tử float32. Khởi động lại nạp vector từ DB. Phiên bản model nhận diện có fingerprint trọng số để tránh trộn bộ vector của model khác. Ảnh cũ trước hiệu chỉnh được giữ dưới dạng crop có lề, tối đa 512 px cạnh dài; không lưu video hay mọi frame.

Mỗi phiên kéo dài tối đa 30 phút, tối đa ba phiên đang thu nhận cho mỗi người thao tác. Mỗi batch tối đa 10 ảnh, mỗi ảnh tối đa 5 MB và 4 triệu pixel sau giải mã. Phiên hủy/hết hạn được dọn; bộ template đã thay thế có thời hạn giữ 30 ngày để phục hồi. Dọn dữ liệu diễn ra khi khởi động và tạo phiên; cần áp dụng thời hạn phù hợp cho cả bản sao lưu khi vận hành.

GET `/api/health` cho biết model, tài nguyên Web, số template, phiên bản gallery và cấu hình nhận diện. Trạng thái khả dụng của file landmark không thay cho kiểm thử suy luận thật. PAD/liveness chưa bật; ứng dụng không xác nhận người thật chỉ từ đủ hướng mặt.

**Hành vi kiểm tra chất lượng**

Frontend phân tích mục tiêu 10 FPS, kiểm tra tư thế ổn định, xếp hạng ứng viên và giữ hai mẫu khác nhau mỗi hướng. Backend đo lại hướng độc lập và kiểm tra ảnh, timestamp tương đối, độ nét, ánh sáng, kích thước, nhiều mặt, trùng mẫu và đồng nhất vector. Timestamp được frontend điều chỉnh theo thời gian máy chủ để tránh lệch đồng hồ thiết bị.

Kết quả thu nhận chia theo `front`, `left`, `right`, `up`, `down`; tên ảnh không quyết định hướng. Chỉ hoàn tất khi mỗi nhóm có đúng hai mẫu đã được kiểm tra. Nếu thiếu, giao diện giữ các mẫu được chấp nhận và hướng dẫn thu bổ sung. Khi cần lấy lại mốc chính diện đã gửi, bắt đầu phiên mới để giữ hệ tọa độ nhất quán.

Khi đăng ký lại thất bại, con trỏ bộ FaceID đang dùng giữ nguyên. File/DB/RAM không có chung transaction: thao tác commit dùng thư mục phiên bản bất biến, DB transaction và đổi snapshot gallery; khi khởi động có đối soát các lần chuyển file chưa hoàn tất. Endpoint commit hỗ trợ gửi lặp. API cũ `/face/enroll` yêu cầu phiên/manifest/consent và đi qua cùng kiểm tra; ba ảnh không được kích hoạt FaceID mới.

Kiosk gửi ba frame và chỉ chấp nhận nếu cùng nhận một danh tính, đạt ngưỡng và margin trên cả nhóm. Bản ghi công lưu vào SQLite, có chống trùng 60 giây cho cùng nhân viên và loại IN/OUT. Quét thử qua `/face/verify-preview` không ghi công và không ảnh hưởng chống trùng. Điểm hiển thị dạng `0.780`, không phải phần trăm chính xác. Các bảng ngày công/lương lịch sử vẫn thuộc bộ dữ liệu lịch sử; việc tổng hợp ngày công/lương mới thuộc timekeeping/payroll engine.

**Kiểm thử tự động và giao diện**

```sh
.venv/bin/python -m pip install -r app/backend/requirements-dev.txt
.venv/bin/python -m pytest app/backend/tests -q
node --test app/frontend/tests/face-capture.test.mjs
.venv/bin/python app/backend/scripts/browser_smoke.py
```

Browser smoke dùng Chrome tại đường dẫn mặc định macOS, DB tạm, model nhận diện giả lập và video nhiễu tổng hợp. Có thể truyền `--chrome /duong/dan/chrome`. Tham số `--face-image /duong/dan/anh-mau.jpg` bổ sung kiểm tra model MediaPipe Web thật trong worker; ảnh chỉ được phục vụ bởi route xác thực của máy chủ kiểm thử tạm thời. Máy chủ kiểm thử không mở route này trong ứng dụng thật.

Test API bao phủ phân quyền, FT/PT, danh mục tham chiếu, cấp mã đồng thời, idempotency, consent, phiên hết hạn, sai hướng, ảnh trùng, ảnh lỗi, đủ 10 vector + centroid, reload, ảnh riêng tư, rollback khi DB lỗi, đăng ký lại thất bại, preview, nhiều frame và ghi công trùng. Các test không ghi vào CSV hoặc DB nhân viên thực tế.

**Thử nghiệm chính sách ảnh và ngưỡng**

```sh
.venv/bin/python app/backend/scripts/evaluate_face_policies.py /duong/dan/manifest.jsonl --output /duong/dan/report.json
```

Mỗi dòng manifest:

```json
{"path":"images/front_01.jpg","employee_id":"NV0001","capture_id":"enroll-A-day1","split":"enroll","pose":"front"}
{"path":"images/query_01.jpg","employee_id":"NV0001","capture_id":"check-A-day2-01","split":"calibration"}
{"path":"images/unknown_01.jpg","employee_id":null,"capture_id":"unknown-day3-01","split":"test"}
```

Đây chỉ là ví dụ cấu trúc, chưa phải manifest hoàn chỉnh. Mỗi nhân viên ở split `enroll` cần hai ảnh mỗi hướng; mỗi `capture_id` ở calibration/test cần 3–5 frame cùng người. Ảnh enrollment, calibration và test phải đến từ các lần quay độc lập; mỗi tập đánh giá cần cả người đã đăng ký và người lạ. Công cụ từ chối capture_id dùng qua nhiều split và ảnh trùng. Đường dẫn tương đối được tính từ thư mục manifest.

Công cụ so sánh baseline, gamma nhẹ, CLAHE trên độ sáng, cân bằng trắng có giới hạn, tăng nét nhẹ và giảm nhiễu nhẹ. Chọn ứng viên theo calibration, ưu tiên ít nhận sai danh tính/chấp nhận người lạ, sau đó tỷ lệ nhận đúng; khi hòa ưu tiên baseline. Chỉ đánh giá cấu hình đã chọn trên tập test, kèm baseline để đối chiếu. Kết quả ghi số lượt, nhận sai danh tính, chấp nhận người lạ và từ chối đúng người. Chưa tự đổi cấu hình production, và chưa có dữ liệu để khẳng định một bộ lọc tốt hơn baseline.

Nếu chọn chính sách khác để vận hành, cần review báo cáo, đưa cùng chính sách vào hai luồng trích vector, tăng preprocessing_version, tạo lại gallery từ ảnh gốc và chạy nghiệm thu lại trước khi kích hoạt. Không trộn vector của hai phiên bản. Không dùng các bản đổi màu/nét của cùng ảnh làm nhiều mẫu độc lập hoặc tính vào chỉ tiêu 500 lượt kiểm thử.

**Nghiệm thu thực tế còn cần dữ liệu**

Các kiểm tra tự động không thay cho 500 lượt camera độc lập và đánh giá ở cửa hàng. Cần thu dữ liệu đã được đồng ý, tách đăng ký/hiệu chỉnh/kiểm thử theo buổi quay, gồm nhân viên thật và người lạ. Đo tỷ lệ nhận sai danh tính, từ chối đúng người và P95 thời gian phản hồi trên thiết bị dự kiến. Ngưỡng và các khoảng góc hiện tại vẫn là baseline. Kiểm tra chống ảnh/video cần PAD/liveness và một bộ thử riêng.

**Kết quả kiểm tra trong phiên triển khai**

- 36 kiểm thử Python đã qua, gồm 16 kiểm thử CV có sẵn và các kiểm thử API/lưu trữ mới.
- 5 kiểm thử JavaScript đã qua về quy ước góc, chọn mẫu, chống trùng và giữ mẫu backend đã chấp nhận.
- Chrome desktop chạy đủ 10/10 mẫu, commit và quét thử với camera/model nhận diện giả lập; không có lỗi JavaScript. Kiểm tra viewport 390 px không tràn ngang.
- MediaPipe Web thật chạy trong worker trên ảnh chính diện; góc đo khớp gần với MediaPipe Python trên cùng ảnh.
- Smoke test API dùng ArcFace và MediaPipe thật nhận một mẫu chính diện hợp lệ; phiên vẫn chưa ready vì thiếu các hướng còn lại. Kiểm thử dùng DB tạm, không ghi vào dữ liệu gốc.
- Chưa có bộ 500 lượt camera độc lập để kết luận độ chính xác vận hành hoặc chọn bộ lọc tốt hơn baseline. PAD/liveness chưa được triển khai trong MVP.
