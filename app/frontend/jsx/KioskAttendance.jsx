import React from 'react';

/* Giao diện kiosk chấm công (chỉ hiển thị). Mọi id khớp /js/kiosk.js; logic nhận diện, GPS, WebSocket
   chạy trong js/kiosk.js và được nạp SAU khi giao diện dựng xong (xem kiosk.html). */
const KioskAttendance = () => (
  <main className="kx" ref={el => { if (el && window.__uiReady) window.__uiReady(); }}>
    <header className="kx-head">
      <div className="kx-head-l"><span className="kx-ico" aria-hidden="true">▣</span><div>
        <p className="kx-eyebrow">Điểm danh kiosk · <span id="device"></span> <span className="kx-pill" id="srvPill">Đang kiểm tra</span></p>
        <h1>Cafe 5TN · Chấm công khuôn mặt</h1></div></div>
      <div className="kx-clock"><p id="clock">--:--:--</p><p id="today"></p></div>
    </header>
    <div className="kx-grid">
      <div className="kx-col">
        <section className="kx-card" aria-label="Camera chấm công">
          <div className="kx-row"><h2>Camera nhận diện khuôn mặt</h2>
            <div className="kx-stages" aria-label="Giai đoạn"><span id="st1" className="on">1. Đang quét</span><span id="st2">2. Đã xác nhận</span><span id="st3">3. Cảnh báo</span></div></div>
          <div className="kx-cam">
            <video id="cam" autoPlay muted playsInline aria-label="Camera trực tiếp"></video><canvas id="overlay"></canvas>
            <i className="kx-corner tl"></i><i className="kx-corner tr"></i><i className="kx-corner bl"></i><i className="kx-corner br"></i>
            <span className="kx-chip tl">NHẬN DIỆN KHUÔN MẶT</span><span className="kx-chip tr" id="gpsChip">GPS: đang lấy…</span>
            <span className="kx-chip bl" id="camHint">Nhìn thẳng vào camera</span><span className="kx-chip br">Quét mỗi 1 giây</span>
          </div>
          <div id="card" className="kx-who" role="status" aria-live="polite">
            <span className="kx-avatar" id="kAvatar">?</span>
            <div><p><b id="title">Đang chờ quét VÀO…</b><span className="kx-id" id="kId" hidden></span></p>
              <p id="sub">Nhìn thẳng vào camera</p>
              <p className="kx-sim">Độ giống khuôn mặt <b id="simTxt"></b></p>
              <div className="kx-bar"><div id="simBar" style={{width:"0%"}}></div><div className="kx-mark" style={{left:"55%"}}></div></div></div>
            <div className="kx-who-r"><small>THỜI GIAN GHI NHẬN</small><p id="time"></p></div>
          </div>
          <p className="kx-note">Điểm tương đồng để đối chiếu, không phải xác suất nhận diện đúng.</p>
        </section>
        <div className="kx-modes" aria-label="Loại chấm công">
          <button type="button" id="btnIn" className="kx-mode" aria-pressed="true" onClick={() => window.setMode && window.setMode('IN')}><span className="ic">↦</span><strong>Vào ca</strong><small>Bắt đầu ca làm việc</small></button>
          <button type="button" id="btnOut" className="kx-mode" aria-pressed="false" onClick={() => window.setMode && window.setMode('OUT')}><span className="ic">↤</span><strong>Ra ca</strong><small>Hoàn thành ca làm</small></button>
          <button type="button" className="kx-mode" disabled title="Chưa có chức năng ghi nhận nghỉ giữa ca"><span className="ic">☕</span><strong>Nghỉ giữa ca</strong><small>Chưa hỗ trợ</small></button>
          <button type="button" className="kx-mode" disabled title="Chưa tích hợp chấm công bằng QR"><span className="ic">▦</span><strong>Quét mã QR</strong><small>Chưa hỗ trợ</small></button>
        </div>
      </div>
      <aside className="kx-col">
        <section className="kx-card"><h2>Phiên hiện tại</h2><p className="kx-sub">Tính từ lúc mở trang này</p>
          <div className="kx-cnt"><div><b id="cntOk">0</b><span>Đã ghi nhận</span></div><div><b id="cntBad">0</b><span>Bị từ chối</span></div></div></section>
        <section className="kx-card"><div className="kx-row"><h2>Nhật ký điểm danh</h2><button id="btnSound" className="kx-link" type="button">Âm thanh: Tắt</button></div>
          <p className="kx-sub">5 lượt quét gần nhất</p><ul id="history" aria-live="polite"></ul></section>
        <section className="kx-tip"><h3>Mẹo chấm công nhanh</h3><p>Đứng thẳng, nhìn vào camera, giữ yên khuôn mặt trong khung. Tránh ngược sáng, che mặt hoặc cúi đầu.</p></section>
      </aside>
    </div>
  </main>
);

export default KioskAttendance;