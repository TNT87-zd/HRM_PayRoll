import {accountHome, loginPage, requestJSON} from './session.mjs';

const $ = id => document.getElementById(id);
const day = $('report-day');
const range = $('report-range');
const key = '/api/analytics/branch-dashboard';
const currency = new Intl.NumberFormat('vi-VN', {style: 'currency', currency: 'VND'});
const number = new Intl.NumberFormat('vi-VN', {maximumFractionDigits: 2});
const clock = new Intl.DateTimeFormat('vi-VN', {timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit'});
const dt = new Intl.DateTimeFormat('vi-VN', {timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'});
const isoDate = new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit'});
const toISO = value => {
  const p = Object.fromEntries(isoDate.formatToParts(value).map(part => [part.type, part.value]));
  return p.year + '-' + p.month + '-' + p.day;
};
const shortDate = value => value.slice(8, 10) + '/' + value.slice(5, 7);
const displayDate = value => shortDate(value) + '/' + value.slice(0, 4);
const hour = value => value ? clock.format(new Date(value)) : '—';
const timeStamp = value => value ? dt.format(new Date(value)) : '—';
const hours = value => value == null ? '—' : number.format(value) + ' giờ';
const set = (id, value) => { $(id).textContent = value; };
const states = {
  present: 'Đủ lượt vào/ra', absent: 'Vắng', incomplete: 'Thiếu lượt vào/ra', invalid: 'Ca cần kiểm tra',
  scheduled: 'Ca chưa kết thúc', in_progress: 'Đã vào, chờ ra', paid_leave: 'Phép có lương', unpaid_leave: 'Phép không lương',
};
const sources = {FACE: 'Kiosk Face ID', MANUAL: 'Bổ sung thủ công', RECONCILED: 'Gắn ca sau đối soát', LEGACY_FACE: 'Tệp Kiosk cũ'};
const needsReview = row => ['absent', 'incomplete', 'invalid'].includes(row.status)
  || row.flags.includes('leave_and_work_conflict');
let report, currentRequest;
let today = toISO(new Date());
const initial = new URL(location.href).searchParams;
const requestedDay = initial.get('day');
day.max = today;
day.value = /^\d{4}-\d{2}-\d{2}$/.test(requestedDay || '') && requestedDay <= today ? requestedDay : today;
range.value = ['1','7','30'].includes(initial.get('days')) ? initial.get('days') : '1';

function table(id, titles, rows, empty) {
  const root = $(id);
  root.replaceChildren();
  if (!rows.length) {
    const note = document.createElement('p');
    note.className = 'admin-muted';
    note.textContent = empty;
    root.append(note);
    return;
  }
  const table = document.createElement('table');
  const header = table.createTHead().insertRow();
  for (const label of titles) {
    const cell = document.createElement('th');
    cell.scope = 'col';
    cell.textContent = label;
    header.append(cell);
  }
  const body = table.createTBody();
  for (const row of rows) {
    const line = body.insertRow();
    for (const value of row) line.insertCell().textContent = value;
  }
  root.append(table);
}

function chart(data) {
  const root = $('attendance-chart');
  root.replaceChildren();
  if (!data.checkins) {
    const empty = document.createElement('div');
    empty.className = 'admin-chart-empty';
    const note = document.createElement('p');
    note.textContent = 'Chưa có lượt chấm vào trong khoảng này.';
    empty.append(note);
    if (data.latest_date && data.latest_date !== data.date) {
      const shortcut = document.createElement('button');
      shortcut.type = 'button';
      shortcut.textContent = 'Xem ngày chấm gần nhất · ' + shortDate(data.latest_date);
      shortcut.onclick = () => showDay(data.latest_date);
      empty.append(shortcut);
    }
    root.append(empty);
    return;
  }
  const plot = document.createElement('div');
  plot.className = 'admin-chart';
  plot.setAttribute('role', 'img');
  plot.setAttribute('aria-label', data.checkins + ' lượt chấm vào trong khoảng báo cáo');
  const peak = Math.max(1, ...data.chart.map(point => point.count));
  const stride = data.days === 1 ? 3 : data.days === 7 ? 1 : 5;
  data.chart.forEach(({label, count}, index) => {
    const column = document.createElement('div');
    const bar = document.createElement('span');
    const tick = document.createElement('small');
    const caption = data.days === 1 ? label.slice(0, 2) + 'h' : shortDate(label);
    bar.style.height = count / peak * 100 + '%';
    column.title = caption + ' · ' + count + ' lượt';
    tick.textContent = index % stride === 0 ? caption : '';
    column.append(bar, tick);
    plot.append(column);
  });
  root.append(plot);
}

function renderShiftSummary(data, dates) {
  const root = $('shift-summary');
  root.replaceChildren();
  set('shift-summary-period', dates);
  const total = data.attendance.length;
  set('shift-summary-count', total + ' ca');
  if (!total) {
    root.textContent = 'Chưa có ca làm trong khoảng báo cáo.';
    return;
  }
  const groups = new Map([
    ['Đủ lượt vào/ra', 0], ['Đã vào, chờ ra', 0], ['Ca chưa kết thúc', 0],
    ['Nghỉ đã duyệt', 0], ['Cần đối chiếu', 0],
  ]);
  const categories = {
    present: 'Đủ lượt vào/ra', in_progress: 'Đã vào, chờ ra', scheduled: 'Ca chưa kết thúc',
    paid_leave: 'Nghỉ đã duyệt', unpaid_leave: 'Nghỉ đã duyệt',
  };
  for (const shift of data.attendance) {
    const category = needsReview(shift) ? 'Cần đối chiếu' : categories[shift.status];
    if (category) groups.set(category, groups.get(category) + 1);
  }
  let index = 0;
  for (const [label, count] of groups) {
    const item = document.createElement('div');
    const caption = document.createElement('label');
    const title = document.createElement('span');
    const value = document.createElement('strong');
    const bar = document.createElement('progress');
    bar.id = 'shift-category-' + ++index;
    caption.htmlFor = bar.id;
    title.textContent = label;
    value.textContent = count + ' ca';
    bar.max = total;
    bar.value = count;
    caption.append(title, value);
    item.append(caption, bar);
    root.append(item);
  }
}

function renderAttendance() {
  if (!report) return;
  const term = $('search-attendance').value.trim().toLocaleLowerCase('vi');
  const filter = $('status-filter').value;
  const selected = report.attendance.filter(row => {
    const matches = !filter || (filter === 'issue' ? needsReview(row)
      : filter === 'leave' ? ['paid_leave','unpaid_leave'].includes(row.status) : row.status === filter);
    return matches && (row.employee_id + ' ' + row.full_name).toLocaleLowerCase('vi').includes(term);
  });
  set('attendance-results', selected.length + '/' + report.attendance.length + ' ca hiển thị');
  table('attendance-table', ['Ngày', 'Nhân viên', 'Lịch ca', 'Vào', 'Ra', 'Giờ thường', 'OT', 'Trạng thái'],
    selected.map(row => [
      shortDate(row.work_date), row.full_name + ' · ' + row.employee_id,
      hour(row.scheduled_start) + ' – ' + hour(row.scheduled_end), timeStamp(row.check_in), timeStamp(row.check_out),
      hours(row.regular_hours), hours(row.ot_hours),
      row.flags.includes('leave_and_work_conflict') ? 'Phép trùng công' : states[row.status],
    ]), 'Chưa có ca phù hợp trong khoảng đã chọn.');
}

function updateLinks(data) {
  const query = new URLSearchParams({month: data.date.slice(0, 7), branch: data.branch.id});
  for (const link of document.querySelectorAll('[data-destination]')) {
    const destination = link.dataset.destination;
    const params = new URLSearchParams(query);
    if (destination === 'new-shift') {
      params.set('month', data.today.slice(0, 7));
      params.set('newShift', data.today);
    }
    const section = destination === 'new-shift' ? 'schedule' : destination;
    link.href = '/portal.html?' + params + '#' + section;
  }
  const params = new URLSearchParams({day: data.date, days: data.days});
  $('export-attendance').href = key + '/export?' + params;
  $('export-attendance').hidden = false;
}

function render(data) {
  report = data;
  today = data.today;
  day.max = today;
  data.latest_date ? $('latest').removeAttribute('hidden') : $('latest').setAttribute('hidden', '');
  set('branch-code', 'Vận hành cửa hàng · ' + data.branch.id);
  const dates = data.days === 1 ? displayDate(data.date) : displayDate(data.start_date) + ' – ' + displayDate(data.date);
  set('report-caption', data.branch.name + ' · ' + dates);
  set('chart-period', dates + (data.days === 1 ? ' · theo giờ' : ' · theo ngày'));
  set('attendance-period', dates + ' · ' + data.branch.name);
  set('active-count', data.active_employees);
  set('check-in-count', data.checked_in_employees + '/' + data.scheduled_employees);
  set('check-in-detail', 'Nhân viên có ca ngày ' + shortDate(data.date));
  set('overtime-hours', hours(data.ot_hours));
  set('overtime-detail', dates);
  set('payroll-title', 'Chi phí nhân sự tháng ' + data.date.slice(5, 7));
  set('payroll-cost', data.payroll.cost == null ? '—' : currency.format(data.payroll.cost));
  set('payroll-note', {unavailable: 'Chưa có bảng lương chi nhánh', test_data: 'Kỳ này chỉ có bảng lương thử',
    draft: 'Bản nháp · Lương gộp + BH doanh nghiệp', finalized: 'Đã chốt · Lương gộp + BH doanh nghiệp'}[data.payroll.status]);
  set('check-in-events', data.checkins + ' lượt');
  for (const [section, nav, count] of [
    ['account-requests', 'nav-accounts', data.pending_accounts], ['leave-requests', 'nav-leaves', data.pending_leaves],
  ]) {
    set(section, count);
    set(nav, count);
    $(nav).hidden = !count;
  }
  set('attendance-issues', data.issues);
  chart(data);
  renderShiftSummary(data, dates);
  table('event-table', ['Thời điểm', 'Nhân viên', 'Lượt', 'Nguồn'], data.events.map(event => [
    timeStamp(event.ts), event.full_name + ' · ' + event.employee_id, event.scan_type === 'IN' ? 'Vào ca' : 'Ra ca',
    sources[event.source] || event.source,
  ]), 'Chưa có lượt chấm công trong khoảng này.');
  updateLinks(data);
  renderAttendance();
  renderView();
}

function renderView() {
  const attendance = location.hash === '#chuyen-can';
  $('overview-view').hidden = attendance;
  $('attendance-view').hidden = !attendance;
  set('admin-title', attendance ? 'Thống kê chuyên cần' : 'Tổng quan vận hành');
  for (const link of document.querySelectorAll('.cafe-sidebar nav a[href^="#"]')) {
    if (link.hash === (attendance ? '#chuyen-can' : '#tong-quan')) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
}

async function load({silent = false} = {}) {
  if (!day.reportValidity()) return;
  currentRequest?.abort();
  const controller = new AbortController();
  currentRequest = controller;
  const params = new URLSearchParams({day: day.value, days: range.value});
  const url = new URL(location.href);
  url.search = params.toString();
  history.replaceState(null, '', url);
  if (!silent) {
    set('admin-status', 'Đang tải dữ liệu chi nhánh…');
    $('export-attendance').hidden = true;
    $('admin-content').hidden = true;
  }
  try {
    const data = await requestJSON(key + '?' + params, {signal: controller.signal});
    if (controller.signal.aborted) return;
    render(data);
    $('admin-content').hidden = false;
    set('admin-status', '');
  } catch (error) {
    if (controller.signal.aborted) return;
    if (error.status === 401) location.replace(loginPage());
    else set('admin-status', error.message);
  }
}

function showDay(value) {
  if (!value) return;
  day.max = toISO(new Date());
  day.value = value;
  range.value = '1';
  load();
}

$('today').onclick = () => showDay(toISO(new Date()));
$('yesterday').onclick = () => showDay(new Date(Date.parse(today + 'T12:00:00Z') - 864e5).toISOString().slice(0, 10));
$('latest').onclick = () => showDay(report?.latest_date);
$('refresh-admin').onclick = load;
day.onchange = load;
range.onchange = load;
$('search-attendance').oninput = renderAttendance;
$('status-filter').onchange = renderAttendance;
$('show-issues').onclick = () => { $('status-filter').value = 'issue'; renderAttendance(); };
window.addEventListener('hashchange', () => { renderView(); window.scrollTo(0, 0); });
window.addEventListener('focus', () => { if (report) load({silent: true}); });

function watchAttendance() {
  if (!window.WebSocket) return;
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const socket = new WebSocket(protocol + '//' + location.host + '/ws/events');
  socket.addEventListener('message', event => {
    try {
      if (!document.hidden && JSON.parse(event.data).event === 'attendance') load({silent: true});
    } catch {
      // Other messages do not change the attendance report.
    }
  });
  window.addEventListener('pagehide', () => socket.close(), {once: true});
}

try {
  const account = await requestJSON('/api/auth/me');
  if (['manager', 'hr'].includes(account.role)) {
    set('admin-account', account.username + ' · ' + (account.role === 'manager' ? 'Quản lý' : 'Nhân sự'));
    renderView();
    await load();
    watchAttendance();
  } else location.replace(accountHome(account));
} catch (error) {
  if (error.status === 401) location.replace(loginPage());
  else set('admin-status', error.message);
}
