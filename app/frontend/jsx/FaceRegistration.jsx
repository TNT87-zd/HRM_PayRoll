import React from 'react';

/* Giao diện đăng ký khuôn mặt (chỉ hiển thị). Toàn bộ id/class khớp enroll.mjs + enroll.css;
   logic nằm ở /js/enroll.mjs và được nạp SAU khi giao diện dựng xong (xem enroll.html). */
const FaceRegistration = () => (
  <div className="ex-page" ref={el => { if (el && window.__uiReady) window.__uiReady(); }}>
    <header className="topbar">
      <div className="brand"><div className="brand-icon" aria-hidden="true">◎</div><div><h1>Đăng ký nhân viên</h1><div className="muted small">Tạo hồ sơ và đăng ký khuôn mặt trong một luồng</div></div></div>
      <nav><a href="/">Trang chủ</a><a href="/kiosk.html">Kiosk</a><a href="/admin.html">Quản trị</a><span id="account" className="muted small"></span><button id="logout" className="quiet" hidden>Đăng xuất</button></nav>
    </header>
    <div className="ex-head">
      <p className="ex-crumb">Vận hành chi nhánh › Quy trình đăng ký khuôn mặt</p>
      <h1>Thu thập dữ liệu khuôn mặt</h1>
      <p className="ex-note">Hệ thống hiện chưa có bước kiểm tra chống giả mạo (liveness). Ảnh chỉ được lưu khi đạt yêu cầu chất lượng.</p>
    </div>
    <main className="layout" id="mainContent" inert="">
      <aside>
          <section className="panel">
            <div className="row between"><h2>Nhân viên</h2><button id="newEmployee" className="primary small" type="button">+ Thêm mới</button></div>
            <label htmlFor="search">Tìm theo tên hoặc mã</label><input id="search" type="search" placeholder="Nhập tên hoặc NV0001" autoComplete="off" />
            <div className="row" style={{marginTop:"10px"}}><select id="faceFilter" aria-label="Lọc trạng thái FaceID"><option value="">Tất cả trạng thái</option><option value="missing">Chưa có FaceID</option><option value="registered">Đã đăng ký FaceID</option></select></div>
            <div id="employeeList" className="employee-list" aria-live="polite"></div>
            <div className="row between small"><button id="previousPage" type="button" className="quiet">←</button><span id="pageLabel" className="muted"></span><button id="nextPage" type="button" className="quiet">→</button></div>
          </section>
          <section className="panel small"><h3>Cách đăng ký</h3><p className="muted">Lưu hồ sơ, xác nhận đồng ý rồi bấm bắt đầu. Quay mặt nhẹ theo hướng dẫn; hệ thống tự chọn hai ảnh cho mỗi hướng.</p><p className="muted">Nếu quét bị gián đoạn, hồ sơ vẫn được giữ để tiếp tục đăng ký sau.</p></section>
        </aside>
      <div className="ex-main">
        <div className="steps" aria-label="Quy trình đăng ký"><span className="step active" id="stepProfile"><b>1</b>Hồ sơ</span><span className="step" id="stepFace"><b>2</b>Quét khuôn mặt</span><span className="step" id="stepVerify"><b>3</b>Kiểm tra</span></div>
        <div className="ex-grid">
          <section className="panel ex-profile">
                <div className="row between"><h2 id="profileTitle">Hồ sơ nhân viên mới</h2><span id="profileBadge" className="tag pending">Chưa lưu</span></div>
                <form id="profileForm">
                  <div className="form-grid">
                    <label className="span2">Họ và tên<input name="full_name" id="fullName" required minLength="2" maxLength="120" autoComplete="name" placeholder="Nguyễn Văn A" /></label>
                    <label>Ngày vào làm<input name="hire_date" id="hireDate" type="date" required /></label>
                    <label>Chi nhánh<select name="branch_id" id="branchId" required><option value="">Chọn chi nhánh</option></select></label>
                    <label>Chức vụ<select name="role" id="role" required><option value="">Chọn chức vụ</option></select></label>
                    <label>Loại hợp đồng<select name="contract_type" id="contractType" required><option value="FT">FT · Toàn thời gian</option><option value="PT">PT · Bán thời gian</option></select></label>
                    <label>Ca làm chính<select name="primary_shift" id="primaryShift" required><option value="">Chọn ca làm</option></select></label>
                    <label id="salaryLabel">Lương tháng (VND)<input id="salary" type="number" min="1" step="1" required inputMode="numeric" placeholder="Nhập mức lương" /></label>
                    <label id="employmentLabel" hidden>Trạng thái làm việc<select id="employmentStatus"><option value="active">Đang làm việc</option><option value="inactive">Ngừng hoạt động</option></select></label>
                  </div>
                  <div className="row form-actions"><button id="saveProfile" type="submit" className="primary">Lưu hồ sơ</button><span id="profileHelp" className="muted small">Hệ thống cấp mã nhân viên khi lưu.</span></div>
                  <div id="profileMessage" className="notice" role="status" hidden></div>
                </form>
              </section>
          <section className="panel ex-face" id="facePanel">
                <div className="row between"><h2>Quét khuôn mặt liên tục</h2><span id="faceBadge" className="tag pending">Chọn hoặc lưu hồ sơ trước</span></div>
                <div className="capture-grid">
                  <div>
                    <div className="camera"><video id="video" autoPlay playsInline muted aria-label="Camera đăng ký khuôn mặt"></video><div id="cameraEmpty" className="camera-empty">Camera sẽ mở khi bạn bắt đầu quét.</div><div id="oval" className="oval"></div><div id="cameraCaption" className="camera-caption" aria-live="polite">Nhìn thẳng và đưa trọn khuôn mặt vào khung</div></div>
                    <div className="row capture-toolbar"><label htmlFor="cameraSelect" className="small">Camera</label><select id="cameraSelect" aria-label="Chọn camera"><option value="">Camera mặc định</option></select><span id="captureElapsed" className="muted small"></span></div>
                  </div>
                  <div><div id="poseList" className="pose-list"></div><div className="progress" role="progressbar" aria-label="Tiến độ thu nhận" aria-valuemin="0" aria-valuemax="10" aria-valuenow="0" id="progress"><div id="progressBar" style={{width:"0%"}}></div></div><div id="captureCount" className="small muted">0 / 10 ảnh</div></div>
                </div>
                <label className="consent"><input id="consent" type="checkbox" /><span id="consentText">Tôi đồng ý thu nhận và lưu dữ liệu khuôn mặt để đăng ký nhận diện và chấm công.</span></label>
                <div className="row"><button id="startCapture" type="button" className="primary" disabled>Bắt đầu quét</button><button id="cancelCapture" type="button" className="quiet" disabled>Hủy lượt quét</button><button id="commitCapture" type="button" className="success" disabled>Hoàn tất đăng ký</button></div>
                <div id="faceMessage" className="notice" role="status" hidden></div>
                <div id="thumbnails" className="thumbnails" aria-label="Các ảnh đã thu nhận"></div>
              </section>
          <section className="panel ex-verify" id="verifyPanel">
                <h2>Kiểm tra sau đăng ký</h2><p className="muted small">Nhìn thẳng để kiểm tra bộ khuôn mặt đang sử dụng. Thao tác này không ghi chấm công.</p>
                <div className="row"><button id="verifyFace" type="button" disabled>Quét thử</button><a href="/kiosk.html">Mở Kiosk chấm công →</a></div><div id="verifyMessage" className="notice" role="status" hidden></div>
              </section>
        </div>
      </div>
    </main>
    <div className="footer">Ảnh chỉ được lưu khi đạt yêu cầu. Tránh ngược sáng, che mặt hoặc quay đầu quá mạnh.</div>
    <div id="authModal" className="modal" role="dialog" aria-modal="true" aria-labelledby="authTitle"><section className="panel auth-card"><h2 id="authTitle">Đăng nhập quản lý nhân sự</h2><p id="authHelp" className="muted small">Sử dụng tài khoản HR hoặc quản lý.</p><form id="authForm"><label>Tên đăng nhập<input id="username" required minLength="3" maxLength="80" pattern="[a-zA-Z0-9_.-]+" autoComplete="username" /></label><label>Mật khẩu<input id="password" type="password" required minLength="12" maxLength="128" autoComplete="current-password" /></label><button id="authSubmit" className="primary" type="submit">Đăng nhập</button><p id="authError" className="error small" role="alert"></p></form></section></div>
    <p style={{textAlign:"center"}}><a href="/portal.html">Mở lịch ca, bảng công và bảng lương</a></p>
  </div>
);

export default FaceRegistration;