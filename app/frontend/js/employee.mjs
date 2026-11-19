import {loginPage, requestJSON} from './session.mjs';

const $ = id => document.getElementById(id);
const month = $('staff-month');
const currency = new Intl.NumberFormat('vi-VN', {style: 'currency', currency: 'VND'});
const vietnamClock = new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit'});
const time = new Intl.DateTimeFormat('vi-VN', {timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit'});
const date = new Intl.DateTimeFormat('vi-VN', {day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC'});
const localISO = value => {
  const parts = Object.fromEntries(vietnamClock.formatToParts(value).map(part => [part.type, part.value]));
  return parts.year + '-' + parts.month + '-' + parts.day;
};
const showDate = value => date.format(new Date(value.slice(0, 10) + 'T00:00:00Z'));
const timestamp = value => new Date(/[zZ]$|[+-]\d\d:\d\d$/.test(value) ? value : value + '+07:00');
const showTime = value => value ? time.format(timestamp(value)) : '—';
const checkTime = value => value ? showTime(value) + ' · ' + showDate(localISO(timestamp(value))) : '—';
const money = value => value == null ? '—' : currency.format(value);
const hours = value => value == null ? '—' : Number(value).toLocaleString('vi-VN', {maximumFractionDigits: 2}) + ' giờ';
let profile, currentLoad;
const requested = new URLSearchParams(location.search).get('month');
month.value = /^\d{4}-(0[1-9]|1[0-2])$/.test(requested || '') ? requested : localISO(new Date()).slice(0, 7);

function table(id, headings, rows, empty) {
  const container = $(id);
  container.replaceChildren();
  if (!rows.length) {
    const message = document.createElement('p');
    message.className = 'staff-muted';
    message.textContent = empty;
    container.append(message);
    return;
  }
  const grid = document.createElement('table');
  const header = grid.createTHead().insertRow();
  for (const label of headings) {
    const cell = document.createElement('th');
    cell.scope = 'col';
    cell.textContent = label;
    header.append(cell);
  }
  const body = grid.createTBody();
  for (const row of rows) {
    const tr = body.insertRow();
    for (const value of row) tr.insertCell().textContent = value;
  }
  container.append(grid);
}

function amounts(id, values, heading) {
  const container = $(id);
  container.replaceChildren();
  if (heading) {
    const title = document.createElement('h3');
    title.textContent = heading;
    container.append(title);
  }
  const list = document.createElement('dl');
  for (const [label, value] of values) {
    const item = document.createElement('div');
    const name = document.createElement('dt');
    const amount = document.createElement('dd');
    name.textContent = label;
    amount.textContent = money(value);
    item.append(name, amount);
    list.append(item);
  }
  container.append(list);
}

function render(data) {
  profile = data.profile;
  $('staff-name').textContent = profile.full_name;
  $('staff-profile').textContent = [profile.employee_id, profile.branch_id, profile.contract_type === 'FT' ? 'Full-time' : 'Part-time'].join(' · ');
  table('schedule-rows', ['Ngày', 'Bắt đầu', 'Kết thúc', 'Chi nhánh', 'Nghỉ', 'OT đã duyệt'],
    data.shifts.map(shift => [
      showDate(localISO(timestamp(shift.start))), showTime(shift.start), showTime(shift.end), shift.branch_id,
      shift.break_minutes + ' phút', shift.approved_ot_minutes + ' phút',
    ]), 'Chưa có ca làm trong kỳ.');
  const states = {present: 'Đủ lượt vào/ra', incomplete: 'Thiếu lượt vào/ra', absent: 'Chưa có lượt chấm',
    paid_leave: 'Phép có lương', unpaid_leave: 'Phép không lương', invalid: 'Cần kiểm tra'};
  table('attendance-rows', ['Ngày', 'Vào', 'Ra', 'Giờ thường', 'Giờ phép có lương', 'OT', 'Trạng thái'],
    data.attendance.map(row => [
      showDate(row.work_date), checkTime(row.check_in), checkTime(row.check_out),
      hours(row.regular_hours), hours(row.paid_leave_hours), hours(row.ot_hours),
      row.status === 'absent' && timestamp(row.scheduled_end) > timestamp(data.as_of) ? 'Ca chưa kết thúc' : states[row.status],
    ]), 'Chưa có dữ liệu chấm công trong kỳ.');

  const verified = data.daily.filter(row => row.amount != null);
  const total = verified.length ? verified.reduce((sum, row) => sum + row.amount, 0) : null;
  const summary = [['Lương công tạm tính trong kỳ', total]];
  if (data.advance) {
    summary.push(['Lương tạm tính đến ngày 15', data.advance.accrued],
      ['Tạm ứng đề xuất', data.advance.suggested_amount], ['Tạm ứng đã chi', data.advance.paid_amount]);
  }
  amounts('pay-summary', summary);
  table('pay-rows', ['Ngày', 'Giờ thường và phép', 'Lương công', 'Tiền OT', 'Phụ trội đêm', 'Tạm tính', 'Đối chiếu'],
    data.daily.map(row => [
      showDate(row.work_date), hours(row.regular_paid_hours), money(row.amount == null ? null : row.base_pay),
      money(row.amount == null ? null : row.ot_pay), money(row.amount == null ? null : row.night_extra_pay), money(row.amount),
      row.pending_shift_count ? `Chờ đối chiếu ${row.pending_shift_count} ca` : 'Đã có dữ liệu',
    ]), data.daily_error || 'Chưa có ca đã kết thúc để tính lương theo ngày.');

  const slip = data.monthly;
  if (slip) {
    const balance = slip.balance_due ?? slip.net;
    amounts('month-payslip', [
      ['Lương gộp', slip.gross], ['BH người lao động', slip.insurance], ['Thuế TNCN', slip.tax],
      ['Khấu trừ khác', slip.other_deduction], ['Thực lĩnh', slip.net], ['Tạm ứng đã trừ', slip.advance_paid ?? 0],
      [balance < 0 ? 'Tạm ứng vượt thực lĩnh' : 'Còn phải trả', Math.abs(balance)],
    ], 'Phiếu lương tháng đã chốt');
  } else {
    $('month-payslip').textContent = 'Phiếu lương tháng sẽ hiển thị khi kỳ lương được chốt.';
  }
  const leaveStates = {pending: 'Chờ duyệt', approved: 'Đã duyệt', rejected: 'Từ chối'};
  table('leave-rows', ['Từ ngày', 'Đến ngày', 'Loại nghỉ', 'Lý do', 'Trạng thái'],
    data.leaves.map(row => [showDate(row.start_date), showDate(row.end_date),
      row.leave_type === 'PAID' ? 'Có lương' : 'Không lương', row.reason, leaveStates[row.status]]),
    'Chưa có đơn nghỉ phép.');
  $('staff-status').textContent = 'Cập nhật lúc ' + showTime(data.as_of);
  $('staff-content').hidden = false;
}

async function load() {
  if (!month.value) return;
  currentLoad?.abort();
  const controller = new AbortController();
  currentLoad = controller;
  try {
    const data = await requestJSON('/api/hrm/self?month=' + encodeURIComponent(month.value), {signal: controller.signal});
    if (!controller.signal.aborted) render(data);
  } catch (error) {
    if (controller.signal.aborted) return;
    if (error.status === 401) {
      $('staff-content').hidden = true;
      location.replace(loginPage());
      return;
    }
    if (error.status === 403) $('staff-content').hidden = true;
    $('staff-status').textContent = error.message;
  } finally {
    if (currentLoad === controller) currentLoad = null;
  }
}

function showTab() {
  const sections = ['schedule', 'attendance', 'salary', 'leave'];
  const hash = location.hash.slice(1);
  const selected = sections.includes(hash) ? hash : 'schedule';
  for (const id of sections) $(id).hidden = id !== selected;
  for (const link of document.querySelectorAll('.staff-tabs a')) {
    if (link.hash === '#' + selected) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
}

window.addEventListener('hashchange', showTab);
month.addEventListener('change', () => {
  if (!month.value) return;
  const url = new URL(location.href);
  url.searchParams.set('month', month.value);
  history.replaceState(null, '', url);
  $('staff-content').hidden = true;
  $('staff-status').textContent = 'Đang tải dữ liệu…';
  load();
});
$('staff-reload').addEventListener('click', load);
$('leave-request').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget, button = form.querySelector('button');
  const feedback = $('leave-status');
  button.disabled = true;
  try {
    const body = {...Object.fromEntries(new FormData(form)), employee_id: profile.employee_id};
    await requestJSON('/api/hrm/leaves', {method: 'POST', body});
    form.reset();
    feedback.textContent = 'Đã gửi đơn nghỉ phép.';
    await load();
  } catch (error) {
    feedback.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
showTab();
load();
setInterval(() => { if (!document.hidden && !currentLoad) load(); }, 30000);
