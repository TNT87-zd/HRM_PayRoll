export async function requestJSON(path, {method = 'GET', body, signal} = {}) {
  const response = await fetch(path, {
    method, signal, cache: 'no-store',
    headers: body ? {'Content-Type': 'application/json'} : undefined,
    body: body ? JSON.stringify(body) : undefined,
  }).catch(error => {
    if (error.name === 'AbortError') throw error;
    throw new Error('Không kết nối được máy chủ. Vui lòng thử lại.');
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof result.detail === 'string' ? result.detail : 'Không thể xử lý yêu cầu. Vui lòng thử lại.';
    throw Object.assign(new Error(detail), {status: response.status});
  }
  return result;
}

export function loginPage() {
  const next = location.pathname + location.search + location.hash;
  return '/login.html?next=' + encodeURIComponent(next);
}

export function accountHome(account, next = '') {
  const paths = account.role === 'employee' ? ['/employee.html']
    : account.role === 'kiosk' ? ['/kiosk.html'] : ['/admin.html', '/portal.html', '/enroll.html'];
  if (next.startsWith('/') && !next.startsWith('//')) {
    let destination;
    try { destination = new URL(next, location.origin); } catch { return paths[0]; }
    if (destination.origin === location.origin && paths.includes(destination.pathname)) {
      return destination.pathname + destination.search + destination.hash;
    }
  }
  return paths[0];
}

document.addEventListener('click', async event => {
  const button = event.target.closest('button[data-logout]');
  if (!button || button.disabled) return;
  button.disabled = true;
  const feedback = document.querySelector('[data-session-error]');
  if (feedback) feedback.textContent = '';
  try {
    await requestJSON('/api/auth/logout', {method: 'POST'});
    location.replace('/login.html');
  } catch {
    const message = 'Chưa đăng xuất được. Vui lòng thử lại.';
    if (feedback) feedback.textContent = message;
    else window.alert(message);
    button.disabled = false;
  }
});

window.addEventListener('pageshow', event => {
  if (event.persisted) location.reload();
});
