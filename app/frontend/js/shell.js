/* Khung điều hướng chung. Chỉ trang có <body data-shell="on"> được bọc thanh bên + thanh trên. */
(function(){
  var b=document.body,mode=b.getAttribute('data-shell');
  var f=document.createElement('link');f.rel='stylesheet';
  f.href='https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700&display=swap';document.head.appendChild(f);
  if(mode!=='on')return;
  var NAV=[['Vận hành',[['Tổng quan','/admin.html'],['Thống kê chuyên cần','/admin.html#chuyen-can'],['Điểm danh Kiosk','/kiosk.html'],['Đăng ký khuôn mặt','/enroll.html']]],
    ['Ca làm và chấm công',[['Lịch làm việc và ca','/portal.html#schedule'],['Bảng chấm công','/portal.html#attendance'],['Phê duyệt nghỉ phép','/portal.html#leave'],['Tính lương','/portal.html#salary']]],
    ['Hệ thống',[['Nhân sự','/portal.html#people'],['Nhật ký thao tác','/portal.html#audit']]]];
  var side=document.createElement('nav');side.className='side';side.setAttribute('aria-label','Điều hướng chính');
  var h='<div class="logo"><b>☕</b><span>Cafe 5TN<small>Nhân sự và tiền lương</small></span></div>';
  NAV.forEach(function(g){h+='<h4>'+g[0]+'</h4>';g[1].forEach(function(i){h+='<a href="'+i[1]+'">'+i[0]+'</a>';});});
  side.innerHTML=h+'<div class="foot"><a href="/">Trang chủ</a></div>';
  var main=document.createElement('div');main.className='app-main';
  var top=document.createElement('div');top.className='top';
  var title=(document.title||'').split(/[·\-–]/)[0].trim()||'HRM';
  top.innerHTML='<h1></h1><div style="display:flex;gap:14px;align-items:center"><span class="who" id="shellWho"></span><span class="pill off" id="shellPill"><i></i><span>Đang kiểm tra…</span></span></div>';
  top.querySelector('h1').textContent=title;
  var box=document.createElement('div');box.className='app-content';
  Array.prototype.slice.call(b.childNodes).forEach(function(n){if(!(n.nodeType===1&&n.tagName==='SCRIPT'))box.appendChild(n);});
  main.appendChild(top);main.appendChild(box);
  var wrap=document.createElement('div');wrap.className='app-shell';wrap.appendChild(side);wrap.appendChild(main);
  b.insertBefore(wrap,b.firstChild);

  function active(){var p=location.pathname,hh=location.hash||'';var best=null;
    side.querySelectorAll('a[href]').forEach(function(a){a.classList.remove('on');var u=new URL(a.href);
      if(u.pathname===p&&(u.hash===hh||(!hh&&(u.hash===''||u.hash==='#overview'||u.hash==='#schedule'))))best=a;});
    if(!best)side.querySelectorAll('a[href]').forEach(function(a){if(!best&&new URL(a.href).pathname===p)best=a;});
    if(best)best.classList.add('on');}
  addEventListener('hashchange',active);active();

  function ping(){fetch('/api/health').then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(){
      var p=document.getElementById('shellPill');p.className='pill';p.lastChild.textContent='Máy chủ hoạt động';})
    .catch(function(){var p=document.getElementById('shellPill');p.className='pill off';p.lastChild.textContent='Mất kết nối máy chủ';});}
  ping();setInterval(ping,15000);
  var who=document.getElementById('who'),sw=document.getElementById('shellWho');   // portal tự điền #who
  if(who&&sw){var sync=function(){sw.textContent=who.textContent;};new MutationObserver(sync).observe(who,{childList:true,characterData:true,subtree:true});sync();}
})();