import {accountHome, requestJSON} from './session.mjs';

const form = document.querySelector('#login-form');
const submit = document.querySelector('#login-submit');
const submitLabel = document.querySelector('#login-submit-label');
const password = form.elements.password;
const toggle = document.querySelector('#show-password');
const feedback = document.querySelector('#login-error');
const registration = document.querySelector('#register-form');
const registerSubmit = document.querySelector('#register-submit');
const registrationFeedback = document.querySelector('#register-error');
const signInView = document.querySelector('#sign-in-view');
const registerView = document.querySelector('#register-view');
const requested = new URLSearchParams(location.search).get('next') || '';
const next = requested.includes('#') ? requested : requested + location.hash;

function enter(account) {
  location.replace(accountHome(account, next));
}

toggle.addEventListener('click', () => {
  const show = password.type === 'password';
  password.type = show ? 'text' : 'password';
  toggle.textContent = show ? 'Ẩn' : 'Hiện';
  toggle.setAttribute('aria-label', show ? 'Ẩn mật khẩu' : 'Hiện mật khẩu');
});

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (submit.disabled) return;
  submit.disabled = true;
  submitLabel.textContent = 'Đang đăng nhập…';
  form.setAttribute('aria-busy', 'true');
  feedback.textContent = '';
  try {
    const account = await requestJSON('/api/auth/login', {
      method: 'POST', body: {username: form.elements.username.value.trim(), password: password.value},
    });
    form.reset();
    enter(account);
  } catch (error) {
    feedback.textContent = error.status === 422 ? 'Kiểm tra lại tên đăng nhập và mật khẩu.' : error.message;
    submit.disabled = false;
    submitLabel.textContent = 'Đăng nhập';
    form.removeAttribute('aria-busy');
  }
});

submit.disabled = false;
registerSubmit.disabled = false;

function showRegistration(show) {
  signInView.hidden = show;
  registerView.hidden = !show;
  const heading = show ? 'register-title' : 'login-title';
  if (show) {
    password.type = 'password';
    toggle.textContent = 'Hiện';
    toggle.setAttribute('aria-label', 'Hiện mật khẩu');
  }
  document.querySelector('#login-panel').setAttribute('aria-labelledby', heading);
  document.querySelector('#' + heading).focus();
}

document.querySelector('#show-register').addEventListener('click', () => {
  feedback.textContent = '';
  document.querySelector('#login-success').textContent = '';
  showRegistration(true);
});
document.querySelector('#show-sign-in').addEventListener('click', () => showRegistration(false));

registration.addEventListener('submit', async event => {
  event.preventDefault();
  if (registerSubmit.disabled) return;
  registerSubmit.disabled = true;
  registerSubmit.textContent = 'Đang gửi yêu cầu…';
  registrationFeedback.textContent = '';
  const fields = registration.elements;
  try {
    const result = await requestJSON('/api/hrm/auth/employee-register', {
      method: 'POST',
      body: {
        employee_id: fields.employee_id.value.trim(),
        username: fields.username.value.trim(),
        password: fields.password.value,
      },
    });
    registration.reset();
    form.reset();
    form.elements.username.value = result.username;
    document.querySelector('#login-success').textContent = 'Đã gửi yêu cầu. Bạn có thể đăng nhập sau khi quản lý duyệt.';
    showRegistration(false);
  } catch (error) {
    registrationFeedback.textContent = error.message;
  } finally {
    registerSubmit.disabled = false;
    registerSubmit.textContent = 'Gửi yêu cầu đăng ký';
  }
});

requestJSON('/api/auth/status').then(status => {
  document.querySelector('#first-setup').hidden = !(status?.setup_required && status.local_setup_allowed);
}).catch(() => {});
