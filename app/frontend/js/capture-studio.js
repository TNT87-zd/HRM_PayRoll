/* Presentation-only enhancements. Enrollment capture remains in enroll.mjs. */
(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  if (document.body.classList.contains('cafe-kiosk')) {
    const video = byId('cam');
    const updateCamera = () => {
      const ready = video.readyState >= 2 && video.videoWidth > 0;
      video.toggleAttribute('data-ready', ready);
      byId('cameraPlaceholder').hidden = ready;
      byId('cameraState').textContent = ready ? '● Camera đang mở' : 'Chờ camera';
      byId('cameraDetail').textContent = ready ? 'Đã kết nối' : 'Chưa có hình ảnh';
    };
    ['loadeddata','playing','emptied','error'].forEach(e => video.addEventListener(e, updateCamera));
    updateCamera();
    const updateHistory = () => { byId('historyEmpty').hidden = byId('history').children.length > 0; };
    new MutationObserver(updateHistory).observe(byId('history'), {childList:true});
    updateHistory();
    const updateGPS = () => {
      // Read the existing GPS state; do not start another location watcher.
      if (typeof LAT !== 'undefined' && typeof LON !== 'undefined') {
        byId('gpsState').textContent = LAT !== null && LON !== null ? 'Đã nhận tọa độ' : 'Chưa nhận tọa độ';
      }
    };
    updateGPS(); setInterval(updateGPS, 2000);
    fetch('/api/health').then(r => {if (!r.ok) throw new Error(); return r.json();}).then(h => {
      byId('modelState').textContent = h.engine_ready ? 'Model sẵn sàng' : 'Model chưa sẵn sàng';
    }).catch(() => { byId('modelState').textContent = 'Không kết nối được'; });
  }
})();
