**Kế hoạch xây dựng chức năng đăng ký nhân viên và thu nhận khuôn mặt liên tục**

Ngày lập: 02/11/2026. Trạng thái: thiết kế đề xuất để triển khai. Các ngưỡng, tốc độ và thời gian dưới đây là cấu hình khởi đầu cần kiểm thử, chưa phải kết quả đo của hệ thống.

**1. Mục tiêu và phạm vi**

HR hoặc quản lý tạo hồ sơ nhân viên, nhân viên xác nhận đồng ý thu nhận khuôn mặt, sau đó thực hiện một lượt quét liên tục theo hướng dẫn. Ứng dụng tự nhận biết năm hướng: chính diện, trái, phải, ngước, cúi; chọn hai ảnh đạt chất lượng mỗi hướng; tạo và lưu bộ vector để Kiosk nhận diện.

Kết quả cần đạt:

- Người dùng bấm “Bắt đầu quét” một lần; tiến trình tự chuyển hướng khi đủ mẫu đạt yêu cầu.
- Mỗi mẫu chứa vùng khuôn mặt ở hướng tương ứng; không yêu cầu chụp riêng từng bộ phận.
- Thu nhận đủ 5 hướng × 2 ảnh = 10 ảnh thật. Chỉ hoàn tất sau khi backend kiểm tra đủ từng hướng.
- Lưu hồ sơ độc lập với phiên quét. Camera hoặc FaceEngine lỗi vẫn giữ hồ sơ để tiếp tục sau.
- Nhân viên có thể quét thử ngay sau khi bộ FaceID được lưu và kích hoạt thành công.
- Ưu tiên giảm nhận nhầm người; khi kết quả mơ hồ, yêu cầu quét lại. Không cam kết đúng 100% trong mọi điều kiện.
- Điểm cosine được ghi là “Độ tương đồng: 0,78”; giao diện chính hiển thị tên/trạng thái, không biến điểm này thành phần trăm xác suất đúng.

**2. Hiện trạng cần xử lý**

| Thành phần | Hiện trạng | Thay đổi cần làm |
|---|---|---|
| Giao diện đăng ký | Wizard đếm ngược rồi chụp từng slot | Thay bằng theo dõi hướng đầu, chất lượng và tiến độ thu nhận từ video |
| Tạo nhân viên | FaceService thêm dòng CSV với chi nhánh, chức vụ, lương mặc định | Tạo hồ sơ qua nghiệp vụ nhân viên với dữ liệu được nhập và kiểm tra |
| Trạng thái FaceID | Có thể suy ra thành công từ số ảnh trong thư mục | Dựa trên bộ mẫu đã kiểm tra, lưu và kích hoạt |
| Hướng mặt | Ước lượng độ lệch dùng trị tuyệt đối | Bổ sung góc có dấu và quy ước trái/phải, trên/dưới nhất quán |
| Lưu ảnh | Tên cố định theo hướng có thể ghi đè ảnh cùng hướng | Định danh phiên và mẫu riêng, lưu hai mẫu mỗi hướng |
| Vector | Toàn bộ mẫu ở RAM; file cache chỉ chứa centroid | Lưu đầy đủ vector mẫu và centroid, nạp lại trực tiếp khi khởi động |
| Ghi dữ liệu | Ghi ảnh trước khi biết đăng ký có thành công | Vùng tạm, phiên bản bất biến và bước kích hoạt có kiểm soát |
| Chiều ảnh | Trang đăng ký lật ngang ảnh; Kiosk lấy ảnh không lật | Giữ pixel gửi backend cùng một quy ước; ảnh gương chỉ dùng cho phần hiển thị |
| Đồng ý thu nhận | Checkbox và tham số API đang mặc định đồng ý | Mặc định chưa đồng ý, bắt buộc xác nhận và ghi nhận thời điểm |
| Tích hợp | Kiosk ghi công ở app/data, analytics đọc data tại gốc dự án | Thống nhất cấu hình đường dẫn và hợp đồng dữ liệu khi kiểm tra tích hợp |

Tái sử dụng FaceEngine, bộ phát hiện mặt, căn chỉnh năm điểm, ArcFace ONNX, kiểm tra chất lượng và logic so khớp hiện có. SQLite/SQLAlchemy đã có cấu hình nhưng chưa có model nhân viên hoàn chỉnh.

**3. Luồng sử dụng**

1. HR/quản lý mở “Thêm nhân viên”, nhập và lưu hồ sơ.
2. Hệ thống cấp mã nhân viên duy nhất; hiển thị “Chưa đăng ký khuôn mặt”.
3. Nhân viên/HR ghi nhận xác nhận đồng ý theo nội dung được hiển thị. Cho phép đăng ký khuôn mặt sau.
4. Kiểm tra camera, ánh sáng, mặt trong khung và model sẵn sàng; lấy tư thế nhìn thẳng làm mốc.
5. Bấm “Bắt đầu quét”; làm theo hướng dẫn chính diện → trái → phải → ngước → cúi.
6. Vòng tiến độ hiển thị từng hướng chưa đạt/đang thu/đủ hai mẫu. Nhắc “Giữ yên”, “Quay nhẹ hơn”, “Đến gần camera” hoặc “Cần thêm ánh sáng” theo lỗi thực tế.
7. Frontend gửi các mẫu đã chọn. Backend kiểm tra lại; nếu một hướng thiếu mẫu đạt chất lượng, chỉ yêu cầu thu bổ sung hướng đó.
8. Khi phát hiện thay người hoặc bộ mẫu không đồng nhất nghiêm trọng, dừng phiên để kiểm tra danh tính trước khi quét lại.
9. Backend lưu bộ mẫu, vector và metadata; kích hoạt phiên bản mới rồi trả thành công.
10. Mở “Quét thử” bằng frame mới; hiển thị kết quả đối chiếu với toàn bộ gallery, không ghi bản chấm công từ thao tác thử.

Đổi nhân viên giữa lượt quét phải hủy bộ đệm/phiên hiện tại; không được gắn ảnh vừa thu của người trước sang hồ sơ mới. Mất mặt, nhiều mặt, đổi camera hoặc mất tracking phải tạm dừng và lấy lại mốc ổn định. Quét lại một hướng không xóa các hướng vẫn hợp lệ trong cùng phiên còn hiệu lực.

**4. Thu nhận và phân loại năm hướng**

Frontend dùng MediaPipe Face Landmarker ở chế độ VIDEO. Xử lý suy luận trong Web Worker nếu môi trường hỗ trợ; giới hạn số frame đang chờ và giảm tốc độ phân tích nếu thiết bị chậm. Nạp thư viện, WASM và model theo phiên bản cố định.

Theo dõi yaw (quay ngang), pitch (ngước/cúi), roll (nghiêng sang vai) và độ ổn định. Góc tính tương đối với tư thế nhìn thẳng; trái/phải theo phía nhân viên. Kiểm tra quy ước trên camera có ảnh gương bằng test riêng. Các tỷ lệ độ lệch hiện tại không được dùng trực tiếp như số đo độ.

| Hướng | Khoảng góc đề xuất ban đầu | Điều kiện bổ sung |
|---|---|---|
| Chính diện | Lệch yaw và pitch trong khoảng 10° | Mặt trong khung, roll nhỏ |
| Trái | Quay trái khoảng 15–30° | Giữ pitch gần mốc |
| Phải | Quay phải khoảng 15–30° | Giữ pitch gần mốc |
| Ngước | Ngước khoảng 10–20° | Giữ yaw gần mốc |
| Cúi | Cúi khoảng 10–20° | Giữ yaw gần mốc |

Cấu hình đầu tiên: phân tích mục tiêu 10 FPS; giữ tư thế ổn định khoảng 300–500 ms; thời gian hai mẫu được chọn cách nhau ít nhất khoảng 300 ms, kèm kiểm tra ảnh trùng. Thu hai mẫu có khác biệt nhỏ trong khoảng góc cho phép. Mục tiêu trải nghiệm là khoảng 10–20 giây trong điều kiện tốt; cho phép thu lại và có nút hủy.

Ví dụ một lượt 15 giây: camera 30 FPS cung cấp khoảng 450 frame, ứng dụng phân tích khoảng 150 frame và giữ 10 ảnh. Trình duyệt không cần ghi thành video. Chỉ giữ bộ đệm nhỏ các ứng viên, giải phóng frame và URL ảnh không dùng.

Metadata hướng do frontend gửi chỉ là gợi ý. Backend xác nhận lại hướng trên ảnh, bằng bộ landmark/head-pose cùng quy ước đã kiểm chứng; không tin tên file để xác định góc. Có thể dùng Face Landmarker phía Python cho bước này. Ảnh tĩnh gửi lên không đủ chứng minh toàn bộ chuyển động liên tục đã diễn ra.

**5. Lọc chất lượng và chọn ảnh**

Trước khi xếp hạng, loại ảnh không đạt các điều kiện bắt buộc: một khuôn mặt, đúng hướng cần thu, kích thước đủ, không cắt mất vùng mặt, độ tin cậy phát hiện đủ, không nhòe nặng hoặc mất chi tiết do thiếu/cháy sáng. Khi đăng ký, cấu hình phát hiện nhiều mặt cần chặt hơn cơ chế bỏ qua mặt nhỏ ở hậu cảnh hiện tại.

Sau đó chấm điểm trên vùng mặt theo độ nét, ánh sáng, độ phù hợp góc, kích thước và độ ổn định. Đo trên các vùng cắt có quy mô tương đương; chuẩn hóa điểm thành phần trước khi kết hợp. Không dùng riêng điểm phát hiện mặt hoặc phương sai Laplacian làm điểm chất lượng tổng.

Mỗi hướng giữ một số ứng viên tốt nhất trong RAM, chọn hai ảnh không trùng. Kiểm tra trùng bằng ảnh/vùng mặt đã căn chỉnh và khoảng cách thời gian; dùng embedding để kiểm tra cùng người, không coi mọi embedding gần nhau là ảnh trùng. Nếu backend loại một mẫu, hướng đó quay lại trạng thái cần bổ sung.

Ngưỡng hiện có như blur 35, độ sáng 40–225 và kích thước mặt 80 px chỉ dùng làm baseline để đối chiếu. Cần hiệu chỉnh lại theo camera, kích thước crop và chính sách tiền xử lý; không xem chúng là ngưỡng phổ quát.

**6. Quy trình xử lý ảnh và tạo vector**

Áp dụng cho từng ảnh đã chọn:

1. Kiểm tra ảnh gốc và xác định vùng mặt/landmark; giữ tọa độ và tỷ lệ khi crop.
2. Chọn vùng mặt có lề phù hợp, không cắt các điểm cần căn chỉnh. Lưu bản màu trước các hiệu chỉnh sáng/nét để có thể tạo lại vector.
3. Áp dụng chính sách hiệu chỉnh ảnh đã được kiểm thử, nếu bật.
4. Căn chỉnh theo hai mắt, mũi và hai khóe miệng bằng phép biến đổi 2D, tạo đầu vào 112 × 112 cho model hiện tại. Không dựng lại phần mặt bị khuất hoặc ép ảnh nghiêng thành mặt chính diện bằng ảnh sinh.
5. Chuẩn hóa màu và giá trị pixel đúng yêu cầu model; dùng cùng thứ tự, model và phiên bản xử lý khi đăng ký/chấm công.
6. Tạo vector 512 chiều float32, kiểm tra hữu hạn, khác vector zero và chuẩn hóa L2.
7. Kiểm tra đồng nhất giữa các mẫu bằng so khớp chéo; không chỉ so với centroid có chứa chính mẫu đó. Giữ logic kiểm tra hiện có làm nền tảng và bổ sung thống kê theo hướng.
8. Kiểm tra trùng nghi vấn với hồ sơ khác: yêu cầu HR kiểm tra lại việc gắn danh tính, không tự ghép/xóa hồ sơ theo điểm giống mặt.
9. Tạo centroid đã chuẩn hóa từ các mẫu hợp lệ, với số mẫu cân bằng giữa năm hướng. Lưu cả 10 vector mẫu và centroid.

| Chính sách ảnh | Cách áp dụng |
|---|---|
| Baseline | Giữ màu tự nhiên, căn chỉnh và chuẩn hóa theo model; chưa bật bộ lọc tăng cường |
| Sáng/gamma | Thử hiệu chỉnh nhẹ với giới hạn; không dùng để cứu ảnh đã mất chi tiết |
| CLAHE | Thử trên kênh độ sáng, giới hạn tương phản; không áp dụng độc lập mạnh lên các kênh RGB |
| Cân bằng trắng | Thử khi camera bị ám màu; đánh giá ảnh hưởng tới vector |
| Tăng nét/giảm nhiễu | Mặc định tắt; chỉ bật khi thử nghiệm chứng minh có lợi. Đánh giá độ mờ trên ảnh gốc trước |
| Biến thể nhân tạo | Dùng để thử độ bền/huấn luyện khi cần; không tính là các mẫu thật bổ sung để hoàn tất hướng |

So sánh baseline với từng biến đổi trên bộ dữ liệu hiệu chỉnh, sau đó xác nhận bằng bộ kiểm thử độc lập. Chỉ chọn chính sách có lợi cho nhận diện; lưu preprocessing_version và thông số. Nếu đổi model/chính sách tạo vector, tạo lại toàn bộ gallery liên quan trước khi kích hoạt và hiệu chỉnh lại ngưỡng; không trộn các phiên bản không tương thích.

**7. Hồ sơ, dữ liệu và lưu trữ**

Hồ sơ bắt buộc: employee_id tự sinh, full_name, branch_id, role, contract_type, primary_shift, hire_date và mức lương tương ứng. FT yêu cầu lương tháng hợp lệ; PT yêu cầu lương giờ hợp lệ. Danh mục chi nhánh/ca lấy từ dữ liệu tham chiếu; không tự gán chi nhánh hoặc lương. Quyền truy cập HR/quản lý tách khỏi chức vụ công việc.

SQLite là nguồn chính cho hồ sơ và vector; import CSV hiện có một lần có báo cáo mã trùng/số lượng. API nhân viên, FaceService và phần tra tên/tổng nhân sự của analytics dùng chung repository. CSV còn dùng cho xuất báo cáo và các phần lịch sử hiện có, tránh hai nguồn nhân viên cùng được ghi.

| Bảng đề xuất | Nội dung chính |
|---|---|
| employees | Hồ sơ, trạng thái làm việc, thời gian tạo/cập nhật, phiên bản FaceID đang dùng |
| face_enrollment_sessions | UUID, employee_id, người thao tác, đồng ý và phiên bản nội dung, trạng thái, hạn sử dụng, lỗi, model_version, preprocessing_version |
| face_samples | sample_id, session_id, pose, đường dẫn ảnh, checksum, thời điểm lấy, góc backend đo, điểm chất lượng, vector float32 512 chiều |
| face_templates | Phiên bản bộ mẫu, centroid, số mẫu, phiên bản model/xử lý, trạng thái kích hoạt và gallery_version |

Các đường dẫn dưới đây là khóa lưu trữ tương đối được ghép với một storage root riêng của backend, nằm ngoài thư mục frontend công khai:

```text
face/staging/<session_uuid>/<sample_uuid>.jpg
face/enrollments/<employee_id>/<session_uuid>/front_01.jpg
face/enrollments/<employee_id>/<session_uuid>/front_02.jpg
face/enrollments/<employee_id>/<session_uuid>/left_01.jpg
... đủ 10 mẫu của 5 hướng
```

Ảnh lưu chính thức là crop khuôn mặt có lề, trước hiệu chỉnh sáng/nét, giữ đủ độ phân giải và metadata cần tạo lại vector; không mặc định lưu cả video hoặc thêm một bản ảnh aligned. Chọn kích thước crop/JPEG sau thử nghiệm, không phóng ảnh mặt nhỏ để làm tăng chất lượng giả. Các ảnh tạm chưa đạt bị xóa khi thay mẫu, hủy hoặc hết hạn phiên. Phiên bản cũ được giữ trong thời hạn phục hồi có cấu hình; khi hết hạn cần dọn cả file và dữ liệu mẫu, có xử lý bản sao lưu tương ứng.

Nếu mỗi ảnh sau crop/nén khoảng 50–150 KB, 10 ảnh chiếm 0,5–1,5 MB. Mười một vector có phần dữ liệu thô 11 × 512 × 4 = 22.528 byte, tức 22 KiB. Tổng khoảng 0,52–1,52 MB/nhân viên, chưa tính metadata, phiên cũ và backup; đây là ước lượng có điều kiện, cần đo thực tế.

Ảnh và vector chỉ truy cập qua API có quyền; không đưa vào Git hoặc static mount. Giới hạn số mẫu, dung lượng, loại ảnh và kích thước sau giải mã. Tên file/employee_id từ người dùng không được dùng trực tiếp để tạo đường dẫn. Cấu hình HTTPS khi dùng camera từ thiết bị khác; localhost phục vụ phát triển.

**8. Hoàn tất phiên và khôi phục lỗi**

Trạng thái phiên: created → capturing → validating → ready_to_commit → committed; nhánh lỗi failed/cancelled/expired. Trong MVP, phiên chưa gửi hoặc hết hạn cần quét lại; hồ sơ và bộ FaceID đang dùng vẫn được giữ. Không hứa tự phục hồi toàn bộ lượt quét sau khi đóng trình duyệt.

Bộ FaceID mới chỉ được kích hoạt khi đủ hai mẫu đạt chuẩn ở cả năm hướng, vector hợp lệ, bộ mẫu đồng nhất và đã lưu đủ dữ liệu. Khi đăng ký lại, bộ cũ tiếp tục hoạt động trong lúc xử lý.

Trình tự commit:

1. Ghi ảnh vào vùng tạm và kiểm tra toàn bộ mẫu, vector, metadata.
2. Chuẩn bị thư mục phiên bản mới bất biến trên cùng filesystem để chuyển tên an toàn.
3. Hoàn tất file trước; dùng transaction DB ghi mẫu/template và đổi con trỏ active_template. Commit lặp phải trả lại cùng kết quả, không tạo bản sao.
4. Nạp bộ mẫu mới vào gallery bằng snapshot hoàn chỉnh; trả trạng thái sẵn sàng khi worker nhận diện đã đồng bộ gallery_version.
5. Nếu lỗi trước commit DB, bộ cũ không đổi; tác vụ dọn rác xóa file chưa được DB tham chiếu. Nếu lỗi sau commit, nạp lại từ DB và trả trạng thái đang đồng bộ/thử lại.

Filesystem, DB và RAM không có chung một transaction. Cần cơ chế đối soát khi khởi động, ghi lỗi rõ ràng và kiểm thử các điểm dừng đột ngột. MVP triển khai một worker nhận diện; nhiều worker cần cơ chế phát sự kiện hoặc kiểm tra phiên bản gallery trước khi báo đã sẵn sàng ở mọi worker.

**9. Hợp đồng API đề xuất**

| API | Mục đích |
|---|---|
| POST /api/employees | Tạo hồ sơ, hỗ trợ khóa chống gửi lặp, cấp mã trong transaction |
| GET /api/employees | Tìm kiếm/lọc/phân trang và trạng thái FaceID |
| GET /api/employees/{id} | Chi tiết hồ sơ theo quyền; mã không tồn tại trả 404 |
| PATCH /api/employees/{id} | Cập nhật hồ sơ theo quyền |
| POST /api/employees/{id}/face/sessions | Tạo phiên gắn cố định với hồ sơ và xác nhận đồng ý |
| POST /api/employees/{id}/face/sessions/{session_id}/samples | Nhận batch ảnh và manifest sample_id/pose/timestamp; trả lỗi theo mẫu/hướng |
| GET /api/employees/{id}/face/sessions/{session_id} | Lấy trạng thái, số mẫu đạt mỗi hướng và lỗi cần khắc phục |
| POST /api/employees/{id}/face/sessions/{session_id}/commit | Kiểm tra lại và kích hoạt bộ mẫu; xử lý idempotent và phiên hết hạn |
| DELETE /api/employees/{id}/face/sessions/{session_id} | Hủy phiên chưa hoàn tất và dọn dữ liệu tạm |
| POST /api/employees/{id}/face/verify-preview | Quét thử bằng mẫu mới với gallery đang dùng, không ghi công và không tác động cửa sổ chống quét trùng |

Mẫu phản hồi phiên gồm status, pose_counts, rejected_samples với mã lỗi cụ thể, model_version và gallery_version. Frontend dịch mã lỗi thành hướng dẫn; không suy đoán thành công từ số file trên đĩa. Khóa API và quyền áp dụng cho cả tạo/sửa nhân viên, đăng ký lại, đọc ảnh và xem lương. Nếu chưa có đăng nhập, bổ sung xác thực tối thiểu cùng vai trò HR/quản lý trong giai đoạn API.

Endpoint enroll hiện tại được chuyển thành adapter gọi cùng nghiệp vụ mới; giữ nó có thời hạn cho client cũ nhưng vẫn tuân thủ kiểm tra phiên/quyền/đủ hướng. Client cũ gửi ba ảnh không được tự tạo bộ FaceID mới ở trạng thái ready.

**10. Tích hợp nhận diện và đo độ chính xác**

Kiosk lấy ảnh theo cùng chiều pixel, quy trình crop/căn chỉnh/chuẩn hóa và model như đăng ký. Khởi động nạp vector từ DB, kiểm tra phiên bản thay vì trích lại mọi ảnh ở mỗi lần chạy.

Quyết định nhận diện kết hợp chất lượng, ngưỡng top-1, khoảng cách với nhân viên top-2 và kết quả của một nhóm frame. Bắt đầu thử nhóm 3–5 frame tốt trong cùng lượt, yêu cầu danh tính nhất quán; khi mơ hồ thì thu lại. Các frame gần nhau có tương quan, không coi chúng là các bằng chứng độc lập để suy ra xác suất 100%.

Giữ cách lấy điểm cao nhất giữa các mẫu làm baseline; đo ảnh hưởng khi chuyển sang 10 mẫu/nhân viên và so sánh với cách tổng hợp nhiều mẫu. Không tự tăng số mẫu nhân tạo vì có thể thay đổi phân bố điểm. Ngưỡng 0,55 và margin 0,08 hiện tại cần hiệu chỉnh trên gallery và chính sách xử lý mới, không nâng thành 1,0 để biểu thị chắc chắn.

Chia dữ liệu theo các lần quay độc lập: đăng ký, hiệu chỉnh ngưỡng và kiểm thử cuối. Không chia ngẫu nhiên các frame của cùng video vào cả ba tập. Có nhân viên đã đăng ký, người lạ và trường hợp dễ nhầm; kiểm tra trên quy mô gallery dự kiến. Đo riêng nhận sai danh tính, chấp nhận người lạ, từ chối đúng người và thời gian xử lý; báo cáo số lượt thử và khoảng tin cậy khi phù hợp.

Quay đầu theo hướng dẫn là thao tác thu nhận. Kiểm tra người thật/chống ảnh hoặc video phát lại là hạng mục riêng, không được báo “đã xác minh người thật” chỉ dựa vào việc đủ góc. Nếu yêu cầu vận hành gồm chống chấm công bằng ảnh/video, bổ sung PAD/liveness ở cả đăng ký và Kiosk, đánh giá riêng trước khi đưa vào sử dụng; thời gian nghiên cứu hạng mục này không nằm trong ước lượng MVP dưới đây.

**11. Các giai đoạn và sản phẩm bàn giao**

| Giai đoạn | Công việc | Bàn giao/điều kiện chuyển bước | Ngày công |
|---|---|---|---:|
| 1. Chốt cấu hình và baseline | Kiểm tra đường dẫn, chiều ảnh, schema; thu bộ thử đầu, xác định hợp đồng mẫu | Tài liệu cấu hình và số đo baseline | 1 |
| 2. Hồ sơ, DB và API | Model, migration/import CSV, repository, xác thực/quyền, phiên và khóa gửi lặp | Tạo/sửa hồ sơ, kiểm tra quyền và vòng đời phiên qua API | 3 |
| 3. Quét liên tục | Camera, landmark, head-pose, trạng thái hướng, chọn hai mẫu, UI tiến độ và lỗi | Hoàn tất 5 hướng trên camera thật bằng một lần bắt đầu | 3 |
| 4. Xử lý và kiểm định mẫu | Backend xác nhận hướng, chất lượng, trùng, đồng nhất, vector và thử hiệu chỉnh ảnh | Bộ 10 mẫu hợp lệ; từ chối đúng các trường hợp lỗi | 2–3 |
| 5. Lưu trữ và Kiosk | Commit/rollback, lưu đủ vector, reload gallery, quét thử, giao diện điểm | Nhận diện ngay và sau restart; thất bại không hỏng bộ cũ | 2 |
| 6. Kiểm thử và hiệu chỉnh | Test tự động, kiểm tra camera, đánh giá độc lập, chọn ngưỡng/chính sách | Báo cáo nghiệm thu, cấu hình đã đo, hướng dẫn chạy | 2–3 |

Tổng 13–15 ngày công cho một lập trình viên, giả định FaceEngine hiện có hoạt động ổn định. Chưa tính thời gian chờ người tham gia thu bộ kiểm thử, thay đổi yêu cầu xác thực hoặc nghiên cứu PAD chuyên biệt. Thực hiện theo thứ tự trên; bắt đầu thu dữ liệu kiểm thử từ giai đoạn 1 để giảm thời gian chờ.

**12. Phạm vi thay đổi mã nguồn**

| Vị trí hiện có | Thay đổi chính |
|---|---|
| [enroll.html](/Users/nguyennhan18/Documents/DS445_KHDL/HRM_PayRoll/app/frontend/enroll.html) | Form hồ sơ, wizard video, tiến độ theo hướng, quản lý phiên và lỗi |
| [employees.py](/Users/nguyennhan18/Documents/DS445_KHDL/HRM_PayRoll/app/backend/src/routers/employees.py) | API hồ sơ/phiên, kiểm tra quyền và mã lỗi |
| [schemas.py](/Users/nguyennhan18/Documents/DS445_KHDL/HRM_PayRoll/app/backend/src/schemas.py) và [models.py](/Users/nguyennhan18/Documents/DS445_KHDL/HRM_PayRoll/app/backend/src/models.py) | Hợp đồng dữ liệu và bảng lưu trữ |
| [face_service.py](/Users/nguyennhan18/Documents/DS445_KHDL/HRM_PayRoll/app/backend/src/services/face_service.py) | Điều phối đăng ký, bỏ tự tạo nhân viên mặc định, snapshot gallery |
| [quality.py](/Users/nguyennhan18/Documents/DS445_KHDL/HRM_PayRoll/app/backend/src/cv/quality.py), [alignment.py](/Users/nguyennhan18/Documents/DS445_KHDL/HRM_PayRoll/app/backend/src/cv/alignment.py), [enrollment.py](/Users/nguyennhan18/Documents/DS445_KHDL/HRM_PayRoll/app/backend/src/cv/enrollment.py) | Chất lượng, hướng có dấu, đồng nhất và đầy đủ từng hướng |
| [kiosk.html](/Users/nguyennhan18/Documents/DS445_KHDL/HRM_PayRoll/app/frontend/kiosk.html) và [kiosk.py](/Users/nguyennhan18/Documents/DS445_KHDL/HRM_PayRoll/app/backend/src/routers/kiosk.py) | Chiều ảnh, xác nhận nhiều frame, hiển thị trạng thái, ghi công khi đủ điều kiện và chống trùng |
| [analytics.py](/Users/nguyennhan18/Documents/DS445_KHDL/HRM_PayRoll/app/backend/src/routers/analytics.py) | Tra hồ sơ/tổng nhân sự từ repository chung |

Bổ sung module riêng cho repository, dịch vụ phiên/lưu trữ, head-pose và chính sách tiền xử lý khi triển khai để tránh tiếp tục dồn nghiệp vụ vào FaceService. Giữ giao diện công khai của FaceEngine và các test CV hiện có.

**13. Kiểm thử và tiêu chí nghiệm thu**

- Hồ sơ FT/PT được lưu đúng dữ liệu; mã duy nhất khi tạo đồng thời; gửi lặp không tạo nhân viên/phiên bản trùng; API chi tiết trả 404 đúng.
- Chỉ tài khoản có quyền được tạo/sửa hồ sơ, đọc ảnh hoặc đăng ký lại. Thiếu xác nhận đồng ý phải bị từ chối ở backend.
- Có đủ 5 hướng × 2 mẫu thật được backend xác nhận; gửi 10 ảnh cùng hướng hoặc đổi tên file để giả hướng không được hoàn tất.
- Loại ảnh mờ/tối/cháy sáng, mặt nhỏ/cắt, nhiều người, ảnh trùng và bộ mẫu khác người; frontend nhận đúng mã lỗi để thu lại.
- Mất camera, mạng, model không sẵn sàng, hủy/phiên hết hạn đều có trạng thái rõ ràng; đổi nhân viên không tái dùng mẫu cũ.
- Dừng tiến trình tại các điểm lưu file/DB/gallery rồi khởi động lại không mất bộ đang dùng; không báo ready khi gallery chưa nạp được.
- Mười vector mẫu và centroid đều đúng shape 512, float32, hữu hạn và chuẩn hóa; nhận diện vẫn hoạt động sau restart mà không cần trích lại ảnh.
- Thử nghiệm các biến đổi ảnh trên dữ liệu độc lập; chỉ bật chính sách cải thiện chỉ số đã chọn và không làm nhận nhầm tăng ngoài mức chấp nhận.
- Quét thử không ghi công; một lượt chấm công được chấp nhận chỉ ghi một sự kiện theo cơ chế chống trùng.
- Mục tiêu hiệu năng ban đầu: phản hồi quyết định sau khoảng giữ mặt ổn định không quá 2 giây ở P95 trên thiết bị kiểm thử đã ghi rõ; đo riêng thời gian toàn bộ đăng ký.
- Nghiệm thu nhận diện bằng ít nhất 500 lượt thử độc lập có cả nhân viên và người lạ, nhiều buổi/điều kiện; mục tiêu ban đầu không nhận sai danh tính trong bộ thử và nhận đúng ít nhất 95% lượt nhân viên có đầu vào đạt chuẩn. Báo riêng mẫu số từng nhóm, số lần quét lại và thời gian; không suy ra độ chính xác tuyệt đối từ việc không thấy lỗi trong bộ thử hữu hạn.

Test tự động dùng thư mục tạm, DB tạm và giả lập model/camera khi thích hợp; không ghi vào dữ liệu nhân viên thật. Test với model thật và camera là bộ riêng. Giữ một tập kiểm thử cuối không dùng để chọn ngưỡng; nếu thất bại, báo rõ và thu thập dữ liệu mới khi cần đánh giá lại.

**14. Nguồn kỹ thuật đã đối chiếu**

- MediaPipe hỗ trợ video, landmark và ma trận khuôn mặt; dùng các đầu ra này để xây dựng ước lượng hướng và UI thu nhận. [Google Face Landmarker Web](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/web_js).
- Căn chỉnh năm điểm và chuẩn hóa đầu vào cần theo đúng model. [InsightFace face alignment](https://github.com/deepinsight/insightface/blob/master/python-package/insightface/utils/face_align.py), [ArcFace ONNX](https://github.com/deepinsight/insightface/blob/master/python-package/insightface/model_zoo/arcface_onnx.py).
- CLAHE tăng tương phản cục bộ với giới hạn để giảm khuếch đại nhiễu; hiệu quả cho nhận diện trong dự án vẫn cần đo. [OpenCV histogram equalization/CLAHE](https://docs.opencv.org/4.x/d5/daf/tutorial_py_histogram_equalization.html).
- Điểm giống nhau, ngưỡng và sai số nhận nhầm/từ chối là các khái niệm khác nhau; hệ thống cần đánh giá cả nhận diện 1:N và người lạ. [NIST: A Tale of Two Errors](https://www.nist.gov/blogs/taking-measure/tale-two-errors-measuring-biometric-algorithms).
