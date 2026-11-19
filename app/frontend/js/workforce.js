/* Views over Portal's existing data. Writes continue through the original forms. */
(() => {
'use strict';
const $=id=>document.getElementById(id), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=v=>Number.isFinite(Number(v))?Number(v):0;
const money=v=>v==null?'—':num(v).toLocaleString('vi-VN')+' ₫';
const short=v=>num(v).toLocaleString('vi-VN',{maximumFractionDigits:1});
const parse=v=>new Date(typeof v==='string'&&!/(Z|[+-]\d\d:\d\d)$/.test(v)?v+'+07:00':v);
function parts(v){const d=parse(v);if(!Number.isFinite(+d))return null;const p=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(d).map(x=>[x.type,x.value]));return {day:`${p.year}-${p.month}-${p.day}`,time:`${p.hour}:${p.minute}`};}
const dayAdd=(day,n)=>new Date(Date.parse(day+'T12:00:00Z')+n*864e5).toISOString().slice(0,10);
const monday=day=>dayAdd(day,-((new Date(day+'T12:00:00Z').getUTCDay()+6)%7));
const label=day=>day.slice(8,10)+'/'+day.slice(5,7);
const entry=new URLSearchParams(location.search);
const requestedBranch=entry.get('branch')||'';
const initialBranch=/^[A-Za-z0-9_-]{1,40}$/.test(requestedBranch)?requestedBranch:'';
const requestedShift=entry.get('newShift')||'';
let newShiftDay=/^\d{4}-\d{2}-\d{2}$/.test(requestedShift)?requestedShift:'';
let week='',period='',search='',branch=initialBranch,selected='',payMonth='',paySearch='',payBranch=initialBranch,payType='';
const schedule=$('schedule'),salary=$('salary');if(!schedule||!salary)return;
function details(parent,title,nodes,id){const d=document.createElement('details');d.className='wf-editor';d.id=id;const s=document.createElement('summary');s.textContent=title;d.append(s);nodes.forEach(n=>d.append(n));parent.append(d);return d;}
// Retain the actual forms, event listeners and their permission attributes.
const shiftNodes=[...schedule.children].filter(n=>n.id!=='shiftTable'&&n.tagName!=='H2');
schedule.querySelector('h2').hidden=true;details(schedule,'Thêm / chỉnh sửa ca làm',shiftNodes,'wfShiftEditor');
const payrollNodes=[...salary.children].filter(n=>n.id!=='payTable'&&n.tagName!=='H2');
salary.querySelector('h2').hidden=true;details(salary,'Mức lương, điều chỉnh và chốt bảng lương',payrollNodes,'wfPayEditor');
const sched=document.createElement('div');sched.className='wf';schedule.prepend(sched);
const payroll=document.createElement('div');payroll.className='wf';salary.prepend(payroll);
function data(){return window.cafeData||{};}
function employee(id){return (data().employeeTable||[]).find(e=>e.employee_id===id)||{employee_id:id,full_name:id};}
function initials(name){return String(name||'?').trim().split(/\s+/).slice(-2).map(s=>s[0]).join('');}
function person(e){return `<div class="wf-person"><span class="wf-avatar">${esc(initials(e.full_name||e.employee_id))}</span><div><b>${esc(e.full_name||e.employee_id)}</b><small>${esc(e.employee_id)} · ${esc(e.role||e.branch_id||'Nhân viên')}</small></div></div>`;}
function options(rows,key,value,all){return `<option value="">${all}</option>`+[...new Set(rows.map(r=>r[key]).filter(Boolean))].sort().map(v=>`<option value="${esc(v)}" ${v===value?'selected':''}>${esc(v)}</option>`).join('');}
function branchControl(rows,id,value){
 const ids=[...new Set(rows.map(row=>row.branch_id).filter(Boolean))];
 if(ids.length===1)return `<span class="wf-pill">${esc(ids[0]==='CN01'?'Hải Châu · CN01':ids[0])}</span>`;
 if(!ids.length)return '';
 return `<select id="${id}" aria-label="Lọc chi nhánh">${options(rows,'branch_id',value,'Tất cả chi nhánh')}</select>`;
}
function openEditor(id){const d=$(id);d.open=true;d.scrollIntoView({behavior:'smooth',block:'start'});}
function addShift(day=''){
 const form=$('shiftForm');
 form.reset();
 form.elements.shift_id.value='';
 if(branch)form.elements.branch_id.value=branch;
 if(day){form.elements.start.value=day+'T07:00';form.elements.end.value=day+'T15:00';}
 openEditor('wfShiftEditor');
}
function editShift(s){const f=$('shiftForm');if(f.hidden)return;for(const k of ['shift_id','employee_id','branch_id','break_minutes','approved_ot_minutes','ot_multiplier'])if(f.elements[k])f.elements[k].value=s[k]??(k==='ot_multiplier'?1.5:0);for(const k of ['start','end']){const p=parts(s[k]);f.elements[k].value=p?p.day+'T'+p.time:'';}openEditor('wfShiftEditor');}
function conflicts(rows){const bad=new Set();const groups=new Map();for(const r of rows){if(!groups.has(r.employee_id))groups.set(r.employee_id,[]);groups.get(r.employee_id).push(r);}for(const rs of groups.values()){rs.sort((a,b)=>parse(a.start)-parse(b.start));for(let i=0;i<rs.length;i++)for(let j=i+1;j<rs.length&&parse(rs[j].start)<parse(rs[i].end);j++){bad.add(rs[i].shift_id);bad.add(rs[j].shift_id);}}return bad;}
function renderSchedule(){
 const d=data(),emps=d.employeeTable||[],shifts=d.shiftTable||[],m=$('month').value;
 if(m!==period){period=m;const today=parts(new Date().toISOString()).day;week=monday(today.startsWith(m)?today:m+'-01');}
 if(!week)return;
 const days=Array.from({length:7},(_,i)=>dayAdd(week,i));
 const team=emps.filter(e=>(!branch||e.branch_id===branch)&&(`${e.full_name} ${e.employee_id}`).toLocaleLowerCase('vi').includes(search.toLocaleLowerCase('vi')));
 const ids=new Set(team.map(e=>e.employee_id));const shown=shifts.filter(s=>ids.has(s.employee_id)&&days.includes(parts(s.start)?.day));
 const bad=conflicts(shifts),badShown=shown.filter(s=>bad.has(s.shift_id));
 const counts=days.map(day=>shown.filter(s=>parts(s.start)?.day===day).length);
 const hours=shown.reduce((n,s)=>n+Math.max(0,(parse(s.end)-parse(s.start))/36e5-num(s.break_minutes)/60),0);
 const canEdit=!$('shiftForm').hidden;
 sched.innerHTML=`<div class="wf-heading"><div><div class="wf-eyebrow">VẬN HÀNH CỬA HÀNG</div><h1>Lịch làm việc</h1><p>Xem và phân ca theo tuần.</p></div><div class="wf-actions"><span class="wf-pill">${shown.length} ca trong tuần</span>${canEdit?'<button data-new>＋ Thêm ca mới</button>':''}</div></div>
 <div class="wf-card wf-filters"><div class="wf-actions"><button data-week="-1" aria-label="Tuần trước">‹</button><b>${label(days[0])} – ${label(days[6])} / ${days[6].slice(0,4)}</b><button data-week="1" aria-label="Tuần sau">›</button></div><div class="wf-actions">${branchControl(emps,'wfBranch',branch)}<input id="wfSearch" placeholder="Tìm tên, mã nhân viên…" aria-label="Tìm nhân viên" value="${esc(search)}"></div></div>
 <div class="wf-alert ${badShown.length?'wf-danger':''}"><span class="wf-alert-icon">${badShown.length?'!':'✓'}</span><div><b>${badShown.length?badShown.length+' ca có thời gian chồng nhau':'Lịch ca đã tải từ hệ thống'}</b><small>${badShown.length?'Bấm vào ca được đánh dấu để rà soát thời gian.':'Kỳ '+esc(m)+' · Các ô ngoài kỳ chưa được tải. Ca qua đêm nằm ở ngày bắt đầu.'}</small></div></div>
 <div class="wf-card wf-board"><div class="wf-overflow"><table class="wf-week"><thead><tr><th>NHÂN SỰ & GIỜ DỰ KIẾN</th>${days.map((day,i)=>`<th class="${day===parts(new Date().toISOString()).day?'wf-today':''}">${i===6?'CN':'T'+(i+2)} · ${label(day)}<strong>${day.startsWith(m)?counts[i]+' ca trực':'Ngoài kỳ'}</strong></th>`).join('')}</tr></thead><tbody>${team.map(e=>{const es=shown.filter(s=>s.employee_id===e.employee_id);const h=es.reduce((n,s)=>n+Math.max(0,(parse(s.end)-parse(s.start))/36e5-num(s.break_minutes)/60),0);return `<tr><td>${person(e)}<div class="wf-hours">${short(h)} giờ dự kiến</div></td>${days.map(day=>{const rows=es.filter(s=>parts(s.start)?.day===day);return `<td>${rows.length?rows.map(s=>{const start=parts(s.start),end=parts(s.end);const am=Number(start.time.slice(0,2))<12;return `<button class="wf-shift ${am?'':'wf-afternoon'} ${bad.has(s.shift_id)?'wf-overlap':''}" data-shift="${esc(s.shift_id)}" ${canEdit?'':'disabled'}><b>${bad.has(s.shift_id)?'⚠ Chồng ca':am?'Ca sáng':'Ca chiều / tối'}</b><span>${esc(start.time)} – ${esc(end?.time)}${end?.day!==day?' (+1 ngày)':''}</span><small>${esc(s.branch_id)} · ${num(s.approved_ot_minutes)?'OT '+num(s.approved_ot_minutes)+' phút':'Ca đã lưu'}</small></button>`;}).join(''):`<div class="wf-off">${day.startsWith(m)?'Chưa xếp ca':'Ngoài kỳ'}</div>`}</td>`;}).join('')}</tr>`;}).join('')||'<tr><td colspan="8" class="wf-empty">Chưa có nhân viên phù hợp.</td></tr>'}</tbody></table></div><div class="wf-legend"><span>■ Ca sáng</span><span>🟧 Ca chiều / tối</span><span>□ Chưa xếp ca</span><b>Tổng: ${short(hours)} giờ dự kiến</b></div></div>
 <div class="wf-bottom"><div class="wf-card"><h2>Phân bổ ca trong tuần</h2><p>Số ca bắt đầu mỗi ngày theo bộ lọc hiện tại.</p><div class="wf-bars">${counts.map((n,i)=>`<div><b>${n}</b><span style="height:${n?Math.max(8,n/Math.max(...counts,1)*125):2}px"></span><small>${i===6?'CN':'T'+(i+2)}</small></div>`).join('')}</div></div><div class="wf-card wf-dark"><div class="wf-eyebrow">RÀ SOÁT LỊCH LÀM VIỆC</div><h2>Chuẩn bị cho ca tiếp theo</h2><p>${team.filter(e=>!shown.some(s=>s.employee_id===e.employee_id)).length} nhân viên trong bộ lọc chưa có ca bắt đầu trong tuần này.</p><p>Kiểm tra chi nhánh, giờ nghỉ và thời gian giao ca trước khi lưu.</p>${canEdit?'<button data-new>＋ Xếp ca cho nhân viên</button>':''}</div></div>`;
 sched.querySelectorAll('[data-week]').forEach(b=>{const next=dayAdd(week,Number(b.dataset.week)*7);b.disabled=!Array.from({length:7},(_,i)=>dayAdd(next,i)).some(day=>day.startsWith(m));b.onclick=()=>{week=next;renderSchedule();};});
 sched.querySelectorAll('[data-new]').forEach(b=>b.onclick=()=>addShift());
 sched.querySelectorAll('[data-shift]').forEach(b=>b.onclick=()=>editShift(shifts.find(s=>s.shift_id===b.dataset.shift)));
 const branchFilter=$('wfBranch');
 if(branchFilter)branchFilter.onchange=e=>{branch=e.target.value;renderSchedule();};
 $('wfSearch').oninput=e=>{const at=e.target.selectionStart;search=e.target.value;renderSchedule();$('wfSearch').focus();$('wfSearch').setSelectionRange(at,at);};
 schedule.classList.add('wf-enhanced');
 if(canEdit&&d.employeeTable&&location.hash==='#schedule'&&newShiftDay.startsWith(m+'-')){
  addShift(newShiftDay);
  newShiftDay='';
 }
}

function renderPayroll(){
 const d=data(), meta=d.pay||{}, rows=d.payTable||[], planning=d.planning||{};
 const m=$('month').value, monthLabel=m?m.slice(5)+'/'+m.slice(0,4):'';
 if(m!==payMonth){payMonth=m;selected='';}
 const canEdit=!$('payForm').closest('.hrOnly').hidden, closed=meta.status==='finalized';
 const roster=new Map(rows.map(row=>[row.employee_id,{...employee(row.employee_id),...row,calculated:true}]));
 for(const e of d.employeeTable||[]){
  if((!closed&&canEdit&&e.active&&!e.employee_id.startsWith('DEMO'))||meta.errors?.[e.employee_id]||planning.advances?.[e.employee_id]){
   if(!roster.has(e.employee_id))roster.set(e.employee_id,e);
  }
 }
 const all=[...roster.values()];
 const filtered=all.filter(r=>(!payBranch||r.branch_id===payBranch)&&(!payType||r.contract_type===payType)
  &&(`${r.full_name} ${r.employee_id}`).toLocaleLowerCase('vi').includes(paySearch.trim().toLocaleLowerCase('vi')));
 if(!filtered.some(r=>r.employee_id===selected))selected=filtered[0]?.employee_id||'';
 const r=roster.get(selected), sum=k=>rows.reduce((n,r)=>n+num(r[k]),0);
 const status=closed?'Đã chốt':d.pay?'Bản nháp':'Chưa tính';
 const advance=planning.advances?.[selected], estimate=planning.estimates?.[selected], issue=meta.errors?.[selected];
 const editable=canEdit&&!closed;
 const today=parts(new Date().toISOString()).day;
 const showAdvance=r&&(r.contract_type==='FT'||advance);
 const canPreview=editable&&m+'-15'<=today;
 const totalNet=sum('net'), totalEmployerInsurance=sum('employer_insurance');
 const totalStaffCost=sum('gross')+totalEmployerInsurance;
 const costsOpen=payroll.querySelector('.wf-cost-details')?.open;
 const metric=(label,value,description='',available=!!d.pay)=>`
  <div class="wf-metric"><small>${label}</small><strong>${available?value:'—'}</strong>
   ${description?`<span>${description}</span>`:''}</div>`;
 const line=(label,v)=>`<div class="wf-pay-line"><span>${label}</span><b>${money(v)}</b></div>`;
 const labelDue=v=>v<0?'Tạm ứng vượt thực lĩnh':'Còn phải trả';
 const count=v=>esc(v||0);
 const days=v=>num(v).toLocaleString('vi-VN',{maximumFractionDigits:3});
 const rowState=row=>meta.errors?.[row.employee_id]?'Cần xử lý'
  :row.pending_shift_count?`Chờ bổ sung ${count(row.pending_shift_count)} ca`
  :row.calculated?status:planning.advances?.[row.employee_id]?'Có tạm tính':'Chưa tính';
 const advancePanel=showAdvance?`
  <h3>Lương tạm tính đến ngày 15</h3>
  ${advance?`<p>${days(advance.paid_days)} công thường quy đổi</p>
   ${line('Lương công thực tế',advance.base_pay)}${line('Lương tăng ca',advance.ot_pay)}
   ${line('Lương tạm tính',advance.accrued)}${line('Đề xuất tạm ứng (90%)',advance.suggested_amount)}
   ${line('Tạm ứng đã chi',advance.paid_amount)}
   ${advance.pending_shift_count?`<p>Chờ bổ sung ${count(advance.pending_shift_count)} ca.</p>`:''}
   ${editable&&advance.paid_amount&&r.calculated&&advance.paid_amount!==num(r.advance_paid)?'<p>Tính lại để cập nhật tạm ứng vào quyết toán.</p>':''}`
  :`<p>${m+'-15'>today?'Có thể tính từ ngày 15.':'Chưa có lương tạm tính.'}</p>`}
  ${canPreview&&!advance?.paid_amount?`<div class="wf-actions"><button data-preview>${advance?'Tính lại tạm ứng':'Tính tạm ứng'}</button></div>`:''}
  ${editable&&advance&&!advance.paid_amount?`
   <form class="wf-actions wf-advance-form" data-payment>
    <label>Số tiền thực tế đã chi<input name="amount" type="number" required min="1" step="1" max="${esc(advance.accrued)}" value="${esc(advance.suggested_amount)}"></label>
    <button type="submit">Ghi nhận đã chi</button>
   </form>`:''}`:'';
 const settlement=r?.calculated?`
   <h3>Quyết toán tháng</h3>
   <p>${days(r.paid_days)} công quy đổi · ${short(r.regular_paid_hours)} giờ thường và phép có lương</p>
   <h4>Thu nhập</h4>
   ${line('Lương công thường',r.base_pay)}${line('Lương tăng ca',r.ot_pay)}${line('Phụ trội giờ đêm trong ca',r.night_extra_pay)}
   ${line('Phụ cấp',r.allowance)}${line('Thưởng',r.bonus)}${line('Tổng thu nhập',r.gross)}
   <h4>Khấu trừ từ lương</h4>
   ${line('Bảo hiểm người lao động',r.insurance)}${line('Thuế TNCN',r.tax)}${line('Khấu trừ khác',r.other_deduction)}
   <h4>Thanh toán</h4>
   ${line('Thực lĩnh cả tháng',r.net)}
   ${line('Tạm ứng đã trừ',r.advance_paid??0)}
   <div class="wf-net"><small>${labelDue(r.balance_due)}</small><strong>${money(Math.abs(r.balance_due??r.net))}</strong></div>`
   :'<p>Chưa có kết quả tính lương tháng.</p>';
 payroll.innerHTML=`
  <div class="wf-heading"><div><h1>Kỳ tính lương tháng ${esc(monthLabel)}</h1><span class="wf-pill">${status}</span></div>
   <div class="wf-actions"><button data-load>Tải lại phiếu lương</button>
    ${editable?'<button data-calculate>Tính cả kỳ</button><button data-config>Mức lương & chốt kỳ</button>':''}</div>
  </div>
  <div class="wf-metrics wf-pay-metrics">
   ${canEdit?metric('Tổng chi phí nhân sự',money(totalStaffCost),'Lương gộp + BH doanh nghiệp.'):''}
   ${metric('Tổng lương thực lĩnh',money(totalNet),'Thực lĩnh cả tháng, trước đối trừ tạm ứng.')}
   ${metric('Tạm ứng đã chi',money(Object.values(planning.advances||{}).reduce((n,a)=>n+num(a.paid_amount),0)),'',!!d.planning)}
   ${metric('Hồ sơ đã tính',rows.length)}
   ${metric('Phụ cấp & thưởng',money(sum('allowance')+sum('bonus')),'Đã tính trong lương gộp.')}
   ${metric('BH NLĐ & thuế',money(sum('insurance')+sum('tax')),'Khấu trừ từ lương nhân viên.')}
  </div>
  ${canEdit&&d.pay?`<details class="wf-cost-details" ${costsOpen?'open':''}>
   <summary>Chi tiết chi phí nhân sự <span>BH doanh nghiệp cả kỳ · ${money(totalEmployerInsurance)}</span></summary>
   <div class="wf-cost-breakdown">
    <div>
     ${line('Tổng lương thực lĩnh',totalNet)}
     ${line('BH người lao động',sum('insurance'))}
     ${line('Thuế TNCN',sum('tax'))}
     ${sum('other_deduction')?line('Khấu trừ khác trong lương gộp',sum('other_deduction')):''}
    </div><div>
     ${line('Lương gộp',sum('gross'))}
     ${line('BH doanh nghiệp cả kỳ',totalEmployerInsurance)}
     ${r?.calculated?line('BH doanh nghiệp của '+esc(r.employee_id),r.employer_insurance):''}
     ${line('Tổng chi phí nhân sự',totalStaffCost)}
    </div>
   </div>
  </details>`:''}
  <div class="wf-pay-layout">
   <div>
    <div class="wf-card wf-filters">
     <input id="wfPaySearch" type="search" aria-label="Tìm nhân viên trong bảng lương" placeholder="Tìm tên hoặc mã nhân viên…" value="${esc(paySearch)}">
     ${branchControl(all,'wfPayBranch',payBranch)}
     <select id="wfPayType" aria-label="Lọc bảng lương theo loại nhân viên">
      <option value="">Tất cả loại nhân viên</option><option value="FT" ${payType==='FT'?'selected':''}>Full-time (FT)</option><option value="PT" ${payType==='PT'?'selected':''}>Part-time (PT)</option>
     </select>
    </div>
    <div class="wf-card wf-pay-list"><div class="wf-overflow"><table>
     <thead><tr><th>NHÂN VIÊN</th><th>FT/PT</th><th>ƯỚC LƯỢNG LƯƠNG CÔNG</th><th>LƯƠNG CÔNG THỰC TẾ</th>
      <th>LƯƠNG GỘP</th><th>BH NLĐ</th><th>THUẾ</th><th>THỰC LĨNH</th><th>CÒN PHẢI TRẢ</th></tr></thead>
     <tbody>${filtered.map(row=>`<tr data-pay-person="${esc(row.employee_id)}" class="${row.employee_id===selected?'wf-selected':''}">
      <td><button type="button" class="wf-person-button" data-view-payslip aria-pressed="${row.employee_id===selected}"
        aria-label="Xem phiếu lương ${esc(row.employee_id)}">${esc(row.full_name||row.employee_id)}
       <small>${esc(row.employee_id)} · ${rowState(row)}</small></button>
       ${editable?`<button type="button" class="wf-row-calculate" data-calculate-person="${esc(row.employee_id)}"
        aria-label="Tính lương ${esc(row.employee_id)}">Tính lương</button>`:''}</td>
      <td>${esc(row.contract_type)}</td><td>${money(planning.estimates?.[row.employee_id]?.amount)}</td>
      <td>${money(row.base_pay??planning.advances?.[row.employee_id]?.base_pay)}
       ${row.base_pay==null&&planning.advances?.[row.employee_id]?'<small>Đến ngày 15</small>':''}</td>
      <td>${money(row.gross)}</td><td>${money(row.insurance)}</td>
      <td>${money(row.tax)}</td><td>${money(row.net)}</td>
      <td><b>${row.balance_due<0?'Vượt ứng '+money(-row.balance_due):money(row.balance_due??row.net)}</b></td>
     </tr>`).join('')||'<tr><td colspan="9" class="wf-empty">Không có nhân viên phù hợp.</td></tr>'}</tbody>
     </table></div><div class="wf-legend">Hiển thị ${filtered.length} / ${all.length} nhân viên</div></div>
    ${canEdit?`<div class="wf-card wf-reconcile"><h2>Đối soát công trước khi chốt</h2>
     ${d.pay&&meta.calculation_scope&&meta.calculation_scope!=='all'?'<p>Tính cả kỳ để cập nhật bản quyết toán trước khi chốt.</p>':''}
     <a href="#attendance">Mở bảng chấm công →</a></div>`:''}
   </div>
   <aside class="wf-card wf-slip">
    <div class="wf-slip-head"><span class="wf-logo">₫</span><div><h2>CÀ PHÊ 5TN</h2><small>PHIẾU LƯƠNG · ${esc(monthLabel)}</small></div></div>
    ${r?`<div class="wf-soft">${person(r)}<small>${esc(r.contract_type)} · ${rowState(r)}</small></div>
     ${issue?`<p role="alert">${esc(issue)}</p>`:''}
     ${r.pending_shift_count?`<p>${count(r.pending_shift_count)} ca thiếu lượt vào/ra đang chờ quản lý bổ sung.</p>`:''}
     ${editable?`<div class="wf-actions"><button type="button" data-calculate-person="${esc(r.employee_id)}">Tính lương ${esc(r.employee_id)}</button></div>`:''}
     ${r.contract_type==='FT'?`<h3>Ước lượng lương công cả tháng</h3>
      ${estimate?`${line('Mức lương công thấp nhất',estimate.amount)}<p>Kỳ đã chốt ${esc(estimate.months.join(', '))}</p>`
       :'<p>Chưa có lương công đã chốt trong hai tháng liền trước.</p>'}`:''}
     ${advancePanel}${settlement}
     ${r.calculated?(closed||canEdit?`<div class="wf-actions"><button data-print>In phiếu này</button><a class="wf-link-button" href="${esc($('exportPay').getAttribute('href')||'#')}">Tải Excel kỳ</a></div>`:''):''}`
    :'<div class="wf-empty">Chọn nhân viên để xem phiếu lương.</div>'}
   </aside>
  </div>`;
 payroll.querySelector('[data-load]').onclick=act(async()=>Promise.all([showPay({optional:true}),loadPlanning()]));
 if(editable){
  payroll.querySelector('[data-calculate]').onclick=window.calculatePayroll();
  payroll.querySelector('[data-config]').onclick=()=>openEditor('wfPayEditor');
 }
 const endpoint='/api/hrm/payroll/'+m+'/advance/'+encodeURIComponent(selected);
 const preview=payroll.querySelector('[data-preview]');
 if(preview)preview.onclick=act(async()=>{
  await api(endpoint,'POST');
  if(m===$('month').value){await loadPlanning(m);notice('Đã lưu tạm tính đến ngày 15.');}
 });
 const payment=payroll.querySelector('[data-payment]');
 if(payment)payment.onsubmit=act(async e=>{
  const amount=Number(e.target.elements.amount.value);
  if(!window.confirm('Xác nhận đã chi '+money(amount)+' tạm ứng cho '+selected+'?'))return;
  await api(endpoint+'/payment','POST',{amount,calculation_id:advance.calculation_id});
  if(m===$('month').value){await loadPlanning(m);notice('Đã ghi nhận tạm ứng đã chi.');}
 });
 const branchFilter=$('wfPayBranch');
 if(branchFilter)branchFilter.onchange=e=>{payBranch=e.target.value;renderPayroll();};
 $('wfPayType').onchange=e=>{payType=e.target.value;renderPayroll();};
 $('wfPaySearch').oninput=e=>{
  const at=e.target.selectionStart;
  paySearch=e.target.value;
  renderPayroll();
  const input=$('wfPaySearch');
  input.focus();
  if(at!=null)input.setSelectionRange(at,at);
 };
 const print=payroll.querySelector('[data-print]');
 if(print)print.onclick=()=>{
  const w=window.open('','_blank');
  if(!w)return;
  const link=w.document.createElement('link');
  link.rel='stylesheet';
  link.href=new URL('/css/workforce.css',location.href).href;
  w.document.head.append(link);
  const slip=payroll.querySelector('.wf-slip').cloneNode(true);
  slip.querySelectorAll('.wf-actions').forEach(n=>n.remove());
  w.document.body.className='wf-print';
  w.document.body.append(slip);
  link.onload=()=>{w.focus();w.print();};
 };
 salary.classList.add('wf-enhanced');
}

payroll.addEventListener('click',event=>{
 const calculate=event.target.closest('button[data-calculate-person]');
 if(calculate){
  const employeeId=calculate.dataset.calculatePerson;
  selected=employeeId;
  renderPayroll();
  window.calculatePayroll(employeeId)(event);
  return;
 }
 const row=event.target.closest('[data-pay-person]');
 if(!row)return;
 selected=row.dataset.payPerson;
 renderPayroll();
 const slip=payroll.querySelector('.wf-slip-head');
 slip.scrollIntoView({block:'nearest'});
 if(event.detail===0){
  payroll.querySelector('.wf-selected [data-view-payslip]')?.focus({preventScroll:true});
 }
});

function render(){try{renderSchedule();renderPayroll();}catch(e){console.error('Giao diện lịch/lương:',e);schedule.classList.remove('wf-enhanced');salary.classList.remove('wf-enhanced');}}
window.addEventListener('cafe:data',e=>{if(['payTable','planning'].includes(e.detail?.id))renderPayroll();
 else if(['employeeTable','shiftTable'].includes(e.detail?.id))render();});render();
})();
