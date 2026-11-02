import {POSES, LABELS, anglesFromMatrix, relativePose, classifyPose, faceQuality, bestPair} from './face-capture-core.mjs';

const $ = id => document.getElementById(id);
const state = {
  employee: null, session: null, options: null, health: null, page: 1, total: 0,
  samples: Object.fromEntries(POSES.map(pose => [pose, []])), baseline: null,
  scanning: false, uploading: false, busy: false, generation: 0, timer: null,
  worker: null, pending: null, mainModel: null, stream: null,
  candidates: [], stableSince: null, previousAngles: null, currentPose: 'front',
  profileKey: crypto.randomUUID(), sessionKey: crypto.randomUUID(), setup: false,
};
const captureCanvas = document.createElement('canvas');
const captureContext = captureCanvas.getContext('2d', {willReadFrequently: true});
const messages = {
  no_face: 'Không thấy khuôn mặt. Đưa mặt vào khung.', multiple_faces: 'Chỉ một người đứng trong khung.',
  face_clipped: 'Đưa trọn khuôn mặt vào khung.', face_too_small: 'Đến gần camera hơn.',
  too_blurry: 'Giữ yên và thu lại ảnh rõ nét.', too_dark: 'Cần thêm ánh sáng phía trước mặt.',
  too_bright: 'Tránh ánh sáng quá mạnh.', extreme_pose: 'Quay mặt nhẹ hơn.',
  wrong_pose: 'Hướng mặt chưa đạt. Làm lại theo hướng dẫn.', front_required: 'Bắt đầu bằng tư thế nhìn thẳng.',
  duplicate_image: 'Xoay nhẹ thêm để có hai mẫu khác nhau.', frames_too_close: 'Giữ tư thế thêm một chút.',
  low_det_score: 'Đưa mặt vào khung và cải thiện ánh sáng.', invalid_image: 'Ảnh không đọc được, cần thu lại.',
  inconsistent_identity: 'Các mẫu không đồng nhất. Kiểm tra nhân viên rồi bắt đầu lượt mới.',
  below_threshold: 'Chưa khớp khuôn mặt đã đăng ký.', ambiguous_margin: 'Khó phân biệt, hãy thử lại.',
  unstable_identity: 'Kết quả chưa ổn định, hãy quét lại.', empty_gallery: 'Chưa có bộ khuôn mặt để đối chiếu.',
  engine_unavailable: 'Bộ nhận diện chưa sẵn sàng.', low_quality: 'Ảnh chưa đủ chất lượng, hãy thử lại.',
};

function notice(id, text, type = '') {
  const element = $(id); element.hidden = !text;
  element.textContent = text; element.className = `notice ${type}`;
}

async function api(url, options = {}) {
  const headers = {...options.headers};
  let body = options.body;
  if (body && !(body instanceof FormData)) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(body); }
  const response = await fetch(url, {...options, body, headers, credentials: 'same-origin'});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) { $('authModal').hidden = false; $('mainContent').inert = true; }
    const detail = data.detail;
    const message = Array.isArray(detail) ? detail.map(e => `${e.loc?.at(-1) || ''}: ${e.msg}`).join('; ')
      : typeof detail === 'object' ? detail.message || detail.code : detail;
    const error = new Error(message || `Máy chủ trả lỗi ${response.status}`);
    error.detail = detail; error.status = response.status; throw error;
  }
  return data;
}

function setButtons() {
  const locked = state.scanning || state.uploading || state.busy;
  $('startCapture').disabled = !state.employee || !$('consent').checked || locked;
  $('startCapture').textContent = state.session?.status === 'committed' ? 'Đăng ký lại khuôn mặt' : state.session ? 'Tiếp tục quét' : 'Bắt đầu quét';
  $('cancelCapture').disabled = !state.scanning && (!state.session || state.session.status === 'committed') || state.uploading || state.busy;
  $('commitCapture').disabled = state.session?.status !== 'ready_to_commit' || !$('consent').checked || locked;
  $('consent').disabled = state.uploading || state.busy;
  $('verifyFace').disabled = !state.employee?.has_face || locked;
  $('saveProfile').disabled = locked;
  $('cameraSelect').disabled = locked;
  for (const field of $('profileForm').querySelectorAll('input,select')) field.disabled = locked;
}

function fillSelect(id, rows, key, text, placeholder) {
  const select = $(id); select.replaceChildren(new Option(placeholder, ''));
  for (const row of rows) select.add(new Option(text(row), row[key]));
}

function shifts(selected = '') {
  if (!state.options) return;
  fillSelect('primaryShift', state.options.shifts.filter(s => s.contract_type === $('contractType').value),
    'shift_id', s => `${s.shift_name} · ${s.start_time}–${s.end_time}`, 'Chọn ca làm');
  $('primaryShift').value = selected;
  const label = $('salaryLabel');
  label.firstChild.textContent = $('contractType').value === 'FT' ? 'Lương tháng (VND)' : 'Lương giờ (VND)';
}

async function loadEmployees() {
  const search = new URLSearchParams({q: $('search').value, page: state.page, page_size: 12});
  if ($('faceFilter').value) search.set('face_status', $('faceFilter').value);
  const data = await api(`/api/employees?${search}`);
  state.total = data.total; $('employeeList').replaceChildren();
  for (const employee of data.items) {
    const button = document.createElement('button'); button.type = 'button';
    button.className = `employee ${state.employee?.employee_id === employee.employee_id ? 'selected' : ''}`;
    const name = document.createElement('strong'); name.textContent = employee.full_name;
    const row = document.createElement('div'); row.className = 'row between';
    const meta = document.createElement('span'); meta.className = 'meta'; meta.textContent = `${employee.employee_id} · ${employee.branch_id}`;
    const badge = document.createElement('span'); badge.className = `tag ${employee.has_face ? 'ready' : 'pending'}`;
    badge.textContent = employee.face_status === 'legacy' ? 'FaceID cũ' : employee.has_face ? 'Đã có FaceID' : 'Chưa có FaceID';
    row.append(meta, badge); button.append(name, row);
    button.addEventListener('click', () => selectEmployee(employee.employee_id).catch(e => notice('profileMessage', e.message, 'bad')));
    $('employeeList').append(button);
  }
  if (!data.items.length) { const empty = document.createElement('p'); empty.className = 'muted small'; empty.textContent = 'Không có nhân viên phù hợp.'; $('employeeList').append(empty); }
  $('pageLabel').textContent = `${data.total} nhân viên · Trang ${data.page}`;
  $('previousPage').disabled = state.page <= 1;
  $('nextPage').disabled = state.page * 12 >= data.total;
}

function releaseSamples() {
  for (const sample of Object.values(state.samples).flat()) if (sample.url) URL.revokeObjectURL(sample.url);
  state.samples = Object.fromEntries(POSES.map(pose => [pose, []]));
  for (const candidate of state.candidates) if (candidate.url) URL.revokeObjectURL(candidate.url);
  state.candidates = [];
}

function stopLoop() {
  state.scanning = false; clearTimeout(state.timer);
  state.stableSince = null; state.previousAngles = null;
  $('oval').classList.remove('tracking'); setButtons();
}

function stopCamera() {
  state.stream?.getTracks().forEach(track => track.stop()); state.stream = null;
  $('video').srcObject = null; $('cameraEmpty').hidden = false;
}

async function resetCapture(cancelServer = true) {
  state.generation++; stopLoop();
  if (state.pending) {
    state.pending.reject(new Error('capture_cancelled')); state.pending = null;
    state.worker?.terminate(); state.worker = null;
  }
  const session = state.session, employee = state.employee;
  state.session = null; state.baseline = null; state.sessionKey = crypto.randomUUID();
  if (cancelServer && session && session.status !== 'committed' && employee) {
    await api(`/api/employees/${employee.employee_id}/face/sessions/${session.session_id}`, {method: 'DELETE'}).catch(() => {});
  }
  releaseSamples(); renderProgress();
  $('consent').checked = false; setButtons();
}

async function selectEmployee(id) {
  if (state.uploading || state.busy) return;
  await resetCapture(); stopCamera();
  state.employee = await api(`/api/employees/${encodeURIComponent(id)}`);
  const employee = state.employee;
  $('fullName').value = employee.full_name; $('branchId').value = employee.branch_id;
  $('role').value = employee.role; $('contractType').value = employee.contract_type;
  shifts(employee.primary_shift); $('hireDate').value = employee.hire_date;
  $('salary').value = employee.contract_type === 'FT' ? employee.base_salary || '' : employee.hourly_rate || '';
  $('employmentStatus').value = employee.employment_status; $('employmentLabel').hidden = false;
  $('profileTitle').textContent = employee.full_name; $('profileBadge').textContent = employee.employee_id;
  $('profileBadge').className = 'tag ready'; $('saveProfile').textContent = 'Cập nhật hồ sơ';
  $('profileHelp').textContent = `Đang chọn ${employee.employee_id}`;
  $('faceBadge').textContent = employee.face_status === 'legacy' ? 'Đã có FaceID cũ · có thể đăng ký lại' : employee.has_face ? 'FaceID sẵn sàng' : 'Chưa đăng ký khuôn mặt';
  $('stepFace').classList.add('active'); $('stepVerify').classList.toggle('active', employee.has_face);
  notice('profileMessage', ''); notice('faceMessage', ''); notice('verifyMessage', '');
  setButtons(); await loadEmployees();
}

async function newEmployee() {
  if (state.uploading || state.busy) return;
  await resetCapture(); stopCamera(); state.employee = null;
  state.profileKey = crypto.randomUUID(); $('profileForm').reset();
  $('hireDate').value = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  shifts(); $('employmentLabel').hidden = true;
  $('profileTitle').textContent = 'Hồ sơ nhân viên mới'; $('profileBadge').textContent = 'Chưa lưu'; $('profileBadge').className = 'tag pending';
  $('saveProfile').textContent = 'Lưu hồ sơ'; $('profileHelp').textContent = 'Hệ thống cấp mã nhân viên khi lưu.';
  $('faceBadge').textContent = 'Lưu hồ sơ trước khi quét';
  $('stepFace').classList.remove('active'); $('stepVerify').classList.remove('active');
  for (const id of ['profileMessage', 'faceMessage', 'verifyMessage']) notice(id, '');
  setButtons(); await loadEmployees(); $('fullName').focus();
}

$('profileForm').addEventListener('submit', async event => {
  event.preventDefault(); if (state.busy || state.scanning || state.uploading) return;
  const body = Object.fromEntries(new FormData(event.target));
  body.base_salary = body.contract_type === 'FT' ? Number($('salary').value) : null;
  body.hourly_rate = body.contract_type === 'PT' ? Number($('salary').value) : null;
  const id = state.employee?.employee_id;
  if (id) body.employment_status = $('employmentStatus').value;
  state.busy = true; setButtons();
  try {
    const employee = await api(id ? `/api/employees/${id}` : '/api/employees', {
      method: id ? 'PATCH' : 'POST', body, headers: id ? {} : {'Idempotency-Key': state.profileKey},
    });
    state.busy = false; await selectEmployee(employee.employee_id);
    notice('profileMessage', `Đã lưu hồ sơ ${employee.employee_id}. Có thể bắt đầu đăng ký khuôn mặt.`, 'good');
  } catch (error) { notice('profileMessage', error.message, 'bad'); }
  finally { state.busy = false; setButtons(); }
});

function renderProgress() {
  $('poseList').replaceChildren(); $('thumbnails').replaceChildren();
  let total = 0;
  for (const pose of POSES) {
    const samples = state.samples[pose]; total += samples.length;
    const panel = document.createElement('div'); panel.className = `pose ${samples.length === 2 ? 'complete' : state.scanning && pose === state.currentPose ? 'active' : ''}`;
    const label = document.createElement('strong'); label.textContent = `${samples.length === 2 ? '✓ ' : ''}${LABELS[pose]}`;
    const count = document.createElement('div'); count.className = 'pose-count'; count.textContent = `${samples.length} / 2 ảnh`;
    panel.append(label, count);
    if (samples.length && !state.scanning && !state.uploading && state.session?.status !== 'committed') {
      const retake = document.createElement('button'); retake.type = 'button'; retake.className = 'link'; retake.textContent = 'Thu lại hướng này';
      retake.onclick = () => retakePose(pose).catch(e => notice('faceMessage', e.message, 'bad')); panel.append(retake);
    }
    $('poseList').append(panel);
    for (const sample of samples) {
      if (!sample.url && sample.blob) sample.url = URL.createObjectURL(sample.blob);
      if (sample.url) { const image = document.createElement('img'); image.src = sample.url; image.alt = LABELS[pose]; $('thumbnails').append(image); }
    }
  }
  $('progressBar').style.width = `${total * 10}%`; $('progress').setAttribute('aria-valuenow', total);
  $('captureCount').textContent = `${total} / 10 ảnh · đủ năm hướng`;
}

async function retakePose(pose) {
  if (state.busy || state.uploading || state.scanning) return;
  if (pose === 'front' && Object.values(state.samples).flat().some(s => s.accepted)) {
    await resetCapture(); notice('faceMessage', 'Đã bắt đầu lại để lấy mốc nhìn thẳng mới. Xác nhận đồng ý rồi quét lại.'); return;
  }
  for (const sample of state.samples[pose]) {
    if (sample.accepted && state.session) await api(`${sessionUrl()}/samples/${sample.sample_id}`, {method: 'DELETE'});
    if (sample.url) URL.revokeObjectURL(sample.url);
  }
  state.samples[pose] = []; if (pose === 'front') state.baseline = null;
  if (state.session) state.session.status = 'capturing'; renderProgress(); setButtons();
}

function sessionUrl() { return `/api/employees/${state.employee.employee_id}/face/sessions/${state.session.session_id}`; }

async function ensureCamera() {
  if (state.stream?.getVideoTracks().some(track => track.readyState === 'live')) return;
  if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera cần localhost hoặc kết nối HTTPS.');
  const deviceId = $('cameraSelect').value;
  state.stream = await navigator.mediaDevices.getUserMedia({video: {width: {ideal: 1280}, height: {ideal: 720}, facingMode: 'user', ...(deviceId ? {deviceId: {exact: deviceId}} : {})}, audio: false});
  const video = $('video'); video.srcObject = state.stream; await video.play();
  $('cameraEmpty').hidden = true;
  const cameras = (await navigator.mediaDevices.enumerateDevices()).filter(device => device.kind === 'videoinput');
  const actual = state.stream.getVideoTracks()[0].getSettings().deviceId;
  fillSelect('cameraSelect', cameras, 'deviceId', d => d.label || 'Camera', 'Camera mặc định');
  $('cameraSelect').value = actual || '';
  state.stream.getVideoTracks()[0].onended = () => { stopLoop(); stopCamera(); notice('faceMessage', 'Camera đã ngắt. Kết nối lại để tiếp tục.', 'bad'); };
}

async function ensureAnalyzer() {
  if (state.worker || state.mainModel) return;
  try {
    await new Promise((resolve, reject) => {
      const worker = new Worker('/js/face-worker.js');
      const timeout = setTimeout(() => { worker.terminate(); reject(new Error('Khởi tạo bộ quét quá thời gian')); }, 15000);
      worker.onerror = event => {
        clearTimeout(timeout); worker.terminate();
        state.pending?.reject(new Error('Bộ quét bị gián đoạn. Vui lòng thử lại.')); state.pending = null;
        if (state.worker === worker) state.worker = null;
        reject(new Error(event.message));
      };
      worker.onmessage = ({data}) => {
        if (data.type === 'ready') { clearTimeout(timeout); state.worker = worker; resolve(); }
        else if (data.type === 'error') { if (!state.worker) { clearTimeout(timeout); worker.terminate(); reject(new Error(data.message)); } else { state.pending?.reject(new Error(data.message)); state.pending = null; } }
        else if (data.type === 'frame') { state.pending?.resolve(data); state.pending = null; }
      };
      worker.postMessage({type: 'init'});
    });
  } catch {
    state.worker?.terminate(); state.worker = null;
    const {FaceLandmarker, FilesetResolver} = await import('/vendor/mediapipe/vision_bundle.mjs');
    const files = await FilesetResolver.forVisionTasks('/vendor/mediapipe/wasm');
    state.mainModel = await FaceLandmarker.createFromOptions(files, {
      baseOptions: {modelAssetPath: '/api/face-assets/face_landmarker.task', delegate: 'CPU'},
      runningMode: 'VIDEO', numFaces: 2, outputFacialTransformationMatrixes: true,
      minFaceDetectionConfidence: 0.6, minFacePresenceConfidence: 0.6,
    });
  }
}

function grabCanvas() {
  const video = $('video');
  if (!video.videoWidth) throw new Error('Camera chưa có hình ảnh.');
  const scale = Math.min(1, 1280 / video.videoWidth);
  captureCanvas.width = Math.round(video.videoWidth * scale); captureCanvas.height = Math.round(video.videoHeight * scale);
  captureContext.drawImage(video, 0, 0, captureCanvas.width, captureCanvas.height);
}

async function analyze() {
  if (state.worker) {
    const bitmap = await createImageBitmap(captureCanvas);
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        state.worker?.terminate(); state.worker = null; state.pending = null;
        reject(new Error('Xử lý khung hình quá thời gian. Vui lòng tiếp tục để thử lại.'));
      }, 5000);
      state.pending = {
        resolve: result => { clearTimeout(timeout); resolve(result); },
        reject: error => { clearTimeout(timeout); reject(error); },
      };
      state.worker.postMessage({type: 'frame', image: bitmap, timestamp: performance.now()}, [bitmap]);
    });
  }
  const result = state.mainModel.detectForVideo(captureCanvas, performance.now());
  if (result.faceLandmarks.length !== 1) return {count: result.faceLandmarks.length};
  const points = result.faceLandmarks[0], xs = points.map(p => p.x), ys = points.map(p => p.y);
  return {count: 1, angles: anglesFromMatrix(result.facialTransformationMatrixes[0].data),
    bbox: [Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)]};
}

async function tick(generation) {
  const began = performance.now();
  try {
    if (!state.scanning || generation !== state.generation) return;
    grabCanvas(); const capturedAt = Date.now() / 1000 + (state.clockOffset || 0);
    const frame = await analyze();
    if (!state.scanning || generation !== state.generation) return;
    $('captureElapsed').textContent = `${Math.round((Date.now() - state.scanStarted) / 1000)} giây`;
    if (frame.count !== 1) { state.stableSince = null; state.previousAngles = null; $('cameraCaption').textContent = frame.count ? messages.multiple_faces : messages.no_face; return; }
    const absolute = frame.angles;
    if (!state.baseline) {
      if (Math.abs(absolute.yaw) > 15 || Math.abs(absolute.pitch) > 25 || Math.abs(absolute.roll) > 12) { $('cameraCaption').textContent = 'Nhìn thẳng để bắt đầu'; state.stableSince = null; return; }
      state.baseline = {...absolute};
    }
    const angles = relativePose(absolute, state.baseline);
    const bbox = frame.bbox.map((v, index) => v * (index % 2 === 0 ? captureCanvas.width : captureCanvas.height));
    const quality = faceQuality(captureCanvas, bbox);
    if (!quality.valid) { state.stableSince = null; $('cameraCaption').textContent = quality.reason; return; }
    if (classifyPose(angles) !== state.currentPose) { state.stableSince = null; state.previousAngles = angles; $('cameraCaption').textContent = `${LABELS[state.currentPose]} · quay nhẹ và giữ yên`; return; }
    const movement = state.previousAngles ? Math.abs(angles.yaw - state.previousAngles.yaw) + Math.abs(angles.pitch - state.previousAngles.pitch) : Infinity;
    state.previousAngles = angles;
    if (movement > 4) { state.stableSince = performance.now(); $('cameraCaption').textContent = 'Đúng hướng · giữ yên một chút'; return; }
    state.stableSince ??= performance.now();
    if (performance.now() - state.stableSince < 400) { $('cameraCaption').textContent = 'Giữ yên để ảnh rõ nét'; return; }
    $('oval').classList.add('tracking');
    const blob = await new Promise(resolve => captureCanvas.toBlob(resolve, 'image/jpeg', 0.9));
    if (!blob || !state.scanning || generation !== state.generation) return;
    const candidate = {sample_id: crypto.randomUUID(), pose: state.currentPose, captured_at: capturedAt,
      blob, absolute, angles, score: quality.score, fingerprint: quality.fingerprint};
    state.candidates.push(candidate); state.candidates.sort((a, b) => b.score - a.score); state.candidates = state.candidates.slice(0, 12);
    const locked = state.samples[state.currentPose].filter(sample => sample.accepted);
    const pair = bestPair(state.candidates, state.currentPose, locked);
    if (!pair || performance.now() - state.stableSince < 900) { $('cameraCaption').textContent = 'Đã rõ nét · xoay nhẹ thêm trong hướng này'; return; }
    state.samples[state.currentPose] = pair;
    if (state.currentPose === 'front') state.baseline = {...pair[0].absolute};
    const next = POSES.find(pose => state.samples[pose].length < 2);
    state.candidates = []; state.stableSince = null; state.previousAngles = null;
    if (next) { state.currentPose = next; $('cameraCaption').textContent = LABELS[next]; renderProgress(); }
    else { stopLoop(); renderProgress(); $('cameraCaption').textContent = 'Đã thu đủ năm hướng · đang kiểm tra'; await uploadSamples(); }
  } catch (error) { if (generation === state.generation) { stopLoop(); notice('faceMessage', error.message, 'bad'); } }
  finally { if (state.scanning && generation === state.generation) state.timer = setTimeout(() => tick(generation), Math.max(0, 100 - (performance.now() - began))); }
}

async function uploadSamples() {
  state.uploading = true; setButtons(); notice('faceMessage', 'Đang kiểm tra hướng mặt và chất lượng ở máy chủ…');
  const generation = state.generation;
  try {
    const pending = Object.values(state.samples).flat().filter(sample => !sample.accepted);
    if (!pending.length) return;
    const form = new FormData();
    for (const sample of pending) form.append('files', sample.blob, `${sample.sample_id}.jpg`);
    form.append('manifest', JSON.stringify(pending.map(({sample_id, pose, captured_at}) => ({sample_id, pose, captured_at}))));
    const result = await api(`${sessionUrl()}/samples`, {method: 'POST', body: form});
    if (generation !== state.generation) return;
    state.session = result; const accepted = new Set(result.samples.map(sample => sample.sample_id));
    for (const pose of POSES) state.samples[pose] = state.samples[pose].filter(sample => {
      if (accepted.has(sample.sample_id)) { sample.accepted = true; return true; }
      if (sample.url) URL.revokeObjectURL(sample.url); return false;
    });
    state.baseline = result.baseline;
    if (result.rejected_samples.length) {
      const reasons = [...new Set(result.rejected_samples.flatMap(sample => sample.reasons.flatMap(reason => reason.split(','))).map(reason => messages[reason] || reason))];
      notice('faceMessage', `Cần thu bổ sung các hướng còn thiếu. ${reasons.join(' ')}`, 'bad');
      $('cameraCaption').textContent = 'Bấm tiếp tục để thu bổ sung';
    } else { notice('faceMessage', 'Đủ hai mẫu đạt chất lượng cho mỗi hướng. Bấm “Hoàn tất đăng ký” để lưu bộ khuôn mặt.', 'good'); $('cameraCaption').textContent = 'Đã kiểm tra đủ năm hướng'; }
  } catch (error) {
    notice('faceMessage', `${error.message}. Các ảnh đang được giữ trong lượt này; bấm tiếp tục để thử gửi lại.`, 'bad');
  } finally { state.uploading = false; renderProgress(); setButtons(); }
}

$('startCapture').addEventListener('click', async () => {
  if (!state.employee || !$('consent').checked || state.busy || state.uploading || state.scanning) return;
  state.busy = true; setButtons();
  try {
    state.health = await api('/api/health');
    if (!state.health.engine_ready || !state.health.pose_model_available || !state.health.web_assets_available) throw new Error('Bộ quét chưa sẵn sàng. Liên hệ người quản trị để kiểm tra model.');
    if (state.session?.status === 'committed') { await resetCapture(false); $('consent').checked = true; }
    if (!state.session) state.session = await api(`/api/employees/${state.employee.employee_id}/face/sessions`, {
      method: 'POST', body: {consent: true, consent_version: state.options.consent_version}, headers: {'Idempotency-Key': state.sessionKey},
    });
    else state.session = await api(sessionUrl());
    state.clockOffset = state.session.server_time - Date.now() / 1000;
    if (Object.values(state.samples).flat().length === 10) { state.busy = false; await uploadSamples(); return; }
    notice('faceMessage', 'Đang mở camera và chuẩn bị bộ quét…');
    await ensureCamera(); await ensureAnalyzer();
    state.currentPose = POSES.find(pose => state.samples[pose].length < 2) || 'front';
    state.candidates = []; state.stableSince = null; state.previousAngles = null;
    state.scanning = true; state.scanStarted = Date.now();
    $('cameraCaption').textContent = LABELS[state.currentPose];
    notice('faceMessage', 'Làm theo hướng dẫn. Nếu thiếu mẫu, xoay nhẹ thêm rồi giữ yên.');
    renderProgress(); tick(state.generation);
  } catch (error) {
    if (error.status === 410 || error.status === 409) { await resetCapture(false); }
    notice('faceMessage', error.name === 'NotAllowedError' ? 'Vui lòng cấp quyền camera rồi thử lại.' : error.message, 'bad');
  } finally { state.busy = false; setButtons(); }
});

$('commitCapture').addEventListener('click', async () => {
  state.busy = true; setButtons();
  try {
    const result = await api(`${sessionUrl()}/commit`, {method: 'POST'}); state.session = result;
    if (!result.ready) throw new Error('Bộ mẫu đã lưu, đang chờ đồng bộ nhận diện. Hãy thử lại.');
    state.employee = await api(`/api/employees/${state.employee.employee_id}`);
    $('faceBadge').textContent = 'FaceID sẵn sàng'; $('faceBadge').className = 'tag ready';
    $('stepVerify').classList.add('active'); $('oval').classList.add('complete');
    notice('faceMessage', 'Đăng ký khuôn mặt thành công. Có thể quét thử ngay.', 'good');
    await loadEmployees();
  } catch (error) { notice('faceMessage', error.message, 'bad'); }
  finally { state.busy = false; renderProgress(); setButtons(); }
});

$('verifyFace').addEventListener('click', async () => {
  state.busy = true; setButtons(); notice('verifyMessage', 'Nhìn thẳng và giữ yên để kiểm tra…');
  try {
    await ensureCamera(); const form = new FormData();
    for (let i = 0; i < 3; i++) { grabCanvas(); const blob = await new Promise(resolve => captureCanvas.toBlob(resolve, 'image/jpeg', 0.9)); form.append('files', blob, `verify_${i}.jpg`); await new Promise(resolve => setTimeout(resolve, 200)); }
    const result = await api(`/api/employees/${state.employee.employee_id}/face/verify-preview`, {method: 'POST', body: form});
    if (result.verified_expected) notice('verifyMessage', `Nhận diện: ${result.full_name} (${result.employee_id}). Độ tương đồng: ${result.similarity.toFixed(3)}. Không ghi chấm công.`, 'good');
    else notice('verifyMessage', result.matched ? 'Kết quả khớp hồ sơ khác; kiểm tra lại việc đăng ký.' : messages[result.reason] || 'Chưa đủ điều kiện nhận diện, vui lòng thử lại.', 'bad');
  } catch (error) { notice('verifyMessage', error.message, 'bad'); }
  finally { state.busy = false; setButtons(); }
});

$('cancelCapture').addEventListener('click', async () => { await resetCapture(); stopCamera(); notice('faceMessage', 'Đã hủy lượt quét. Hồ sơ và bộ khuôn mặt đang dùng được giữ.'); });
$('newEmployee').addEventListener('click', () => newEmployee());
$('contractType').addEventListener('change', () => { shifts(); $('salary').value = ''; });
$('cameraSelect').addEventListener('change', () => { stopCamera(); state.baseline = null; if (state.session) resetCapture().then(() => notice('faceMessage', 'Đã đổi camera. Xác nhận đồng ý và bắt đầu lượt mới.')); });
$('consent').addEventListener('change', async () => {
  if (!$('consent').checked && state.session && state.session.status !== 'committed') {
    await resetCapture(); stopCamera(); notice('faceMessage', 'Đã dừng thu nhận và hủy dữ liệu tạm của lượt này.');
  }
  setButtons();
});
let searchTimer;
$('search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { state.page = 1; loadEmployees().catch(e => notice('profileMessage', e.message, 'bad')); }, 250); });
$('faceFilter').addEventListener('change', () => { state.page = 1; loadEmployees().catch(e => notice('profileMessage', e.message, 'bad')); });
for (const [id, delta] of [['previousPage', -1], ['nextPage', 1]]) $(id).addEventListener('click', () => { state.page += delta; loadEmployees().catch(e => notice('profileMessage', e.message, 'bad')); });

async function authenticated(user) {
  $('authModal').hidden = true; $('mainContent').inert = false; $('account').textContent = user.username; $('logout').hidden = false;
  state.options = await api('/api/employees/options');
  fillSelect('branchId', state.options.branches, 'branch_id', row => row.branch_name, 'Chọn chi nhánh');
  fillSelect('role', state.options.roles, 'id', row => row.name, 'Chọn chức vụ');
  $('consentText').textContent = state.options.consent_text;
  await newEmployee();
}

$('authForm').addEventListener('submit', async event => {
  event.preventDefault(); $('authSubmit').disabled = true; $('authError').textContent = '';
  try {
    const user = await api(`/api/auth/${state.setup ? 'setup' : 'login'}`, {method: 'POST', body: {username: $('username').value, password: $('password').value}});
    $('password').value = ''; await authenticated(user);
  } catch (error) { $('authError').textContent = error.message; }
  finally { $('authSubmit').disabled = false; }
});

$('logout').addEventListener('click', async () => {
  await resetCapture(); stopCamera(); await api('/api/auth/logout', {method: 'POST'});
  location.reload();
});
window.addEventListener('pagehide', () => { stopLoop(); stopCamera(); state.worker?.terminate(); state.mainModel?.close(); releaseSamples(); });

async function boot() {
  renderProgress();
  const status = await api('/api/auth/status'); state.setup = status.setup_required;
  if (state.setup) {
    $('authTitle').textContent = 'Thiết lập tài khoản quản lý';
    $('authHelp').textContent = status.local_setup_allowed ? 'Tạo tài khoản đầu tiên trên máy chủ. Mật khẩu tối thiểu 12 ký tự.' : 'Mở trang này từ localhost trên máy chủ để tạo tài khoản đầu tiên.';
    $('authSubmit').textContent = 'Tạo tài khoản'; $('password').autocomplete = 'new-password';
    $('authSubmit').disabled = !status.local_setup_allowed;
  } else {
    try { await authenticated(await api('/api/auth/me')); } catch (error) { if (error.status !== 401) $('authError').textContent = error.message; }
  }
}
boot().catch(error => { $('authError').textContent = error.message; });
