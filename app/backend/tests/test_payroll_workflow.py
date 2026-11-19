from datetime import datetime

from test_enrollment import env, profile
from test_hrm_integration import event

from hrm import api, auth as hrm_auth, core, store
from models import User, UserEmployee
from routers import analytics
from routers.auth import hash_password


def test_individual_pay_advances_and_month_end(env, monkeypatch):
    app, client, *_ = env
    month = '2026-10'
    payroll = f'/api/hrm/payroll/{month}'

    class Clock(datetime):
        current = core.dt('2026-10-14T20:00:00')

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz)

    monkeypatch.setattr(api, 'datetime', Clock)
    ft = profile(client, base_salary=10400000).json()['employee_id']
    other_ft = profile(client).json()['employee_id']
    pt = profile(client, contract_type='PT', primary_shift='PT_AM', base_salary=None,
                 hourly_rate=30000).json()['employee_id']
    contract = dict(resident=True, nationality='VN', document_type='labor', duration_months=12,
                    valid_from=month, valid_until=month, meal_per_day=0, attendance_bonus=0)
    with app.state.session_factory() as con:
        store.put(con, 'payroll_config', month, {
            'payroll_2026_policy': core.load_policy(),
            'contracts': {ft: contract, other_ft: contract, pt: {**contract, 'agreed_monthly_hours': 30}},
        })
        for previous, amount in [('2026-08', 9600000), ('2026-09', 10000000)]:
            store.put(con, 'payroll', previous, {
                'status': 'finalized',
                'rows': [dict(employee_id=ft, contract_type='FT', base_pay=amount)],
            })
        staff = User(username='ft-staff', password_hash=hash_password('ft-staff-password'), role='employee')
        con.add(staff)
        con.flush()
        con.add(UserEmployee(user_id=staff.id, employee_id=ft))
        con.commit()

    def add_shift(eid, key, day, start, end, out=None, approved_ot=60):
        response = client.put('/api/hrm/shifts', json={
            'shift_id': key, 'employee_id': eid, 'branch_id': 'CN01',
            'start': f'{month}-{day}T{start}:00', 'end': f'{month}-{day}T{end}:00',
            'approved_ot_minutes': approved_ot,
        })
        assert response.status_code == 200, response.text
        assert event(client, eid, 'IN', f'{month}-{day}T{start}:00', key).status_code == 200
        if out:
            assert event(client, eid, 'OUT', f'{month}-{out}:00', key).status_code == 200

    add_shift(ft, 'ft-early', '02', '07:00', '15:00', '02T16:00')
    add_shift(ft, 'ft-midmonth', '15', '15:00', '23:00', '16T00:30', approved_ot=90)
    add_shift(ft, 'ft-later', '16', '07:00', '15:00', '16T15:00')
    add_shift(other_ft, 'ft-missing', '02', '07:00', '15:00')
    add_shift(pt, 'pt-complete', '02', '07:00', '12:00', '02T12:00')
    add_shift(pt, 'pt-missing', '03', '07:00', '12:00')

    ft_advance = f'{payroll}/advance/{ft}'
    assert client.post(ft_advance).status_code == 409
    Clock.current = core.dt('2026-10-20T22:00:00')
    attendance = client.get('/api/hrm/attendance', params={'month': month, 'contract_type': 'PT', 'q': pt}).json()
    assert [(row['contract_type'], row['status']) for row in attendance] == [('PT', 'present'), ('PT', 'incomplete')]
    csv = client.get('/api/hrm/attendance/export', params={'month': month, 'contract_type': 'PT'}).text
    assert 'contract_type' in csv and 'pt-complete' in csv and 'ft-early' not in csv

    def calculate(**extra):
        response = client.post(payroll+'/calculate', json={'note': 'Đã đối chiếu công', **extra})
        assert response.status_code == 200, response.text
        return response.json()

    individual = calculate(employee_id=pt)
    row, = individual['rows']
    assert row['employee_id'] == pt
    assert (row['base_pay'], row['paid_days'], row['pending_shift_count']) == (150000, 0.625, 1)
    next_individual = calculate(employee_id=ft)
    assert next_individual['selected_employee_id'] == ft
    assert set(r['employee_id'] for r in next_individual['rows']) == {ft, pt}
    assert next(r for r in next_individual['rows'] if r['employee_id'] == pt) == row
    batch = calculate()
    assert set(batch['errors']) == {other_ft}
    assert {row['employee_id'] for row in batch['rows']} == {ft, pt}

    preview = client.post(ft_advance).json()
    assert (preview['base_pay'], preview['ot_pay'], preview['suggested_amount']) == (800000, 150000, 855000)
    assert client.post(f'{payroll}/advance/{pt}').status_code == 422
    planning = client.get(payroll+'/planning').json()
    assert planning['estimates'][ft] == {'amount': 9600000, 'months': ['2026-09', '2026-08']}
    assert planning['advances'][ft]['paid_amount'] == 0

    assert event(client, other_ft, 'OUT', f'{month}-02T15:00:00', 'ft-missing').status_code == 200
    assert event(client, pt, 'OUT', f'{month}-03T12:00:00', 'pt-missing').status_code == 200
    # Give the second FT enough verified pay to cover monthly deductions.
    add_shift(other_ft, 'ft-second', '03', '07:00', '15:00', '03T16:00')
    add_shift(other_ft, 'ft-third', '04', '07:00', '15:00', '04T15:00')
    assert client.post(f'{payroll}/advance/{other_ft}').status_code == 200
    before_payment = calculate()
    assert not before_payment['errors']
    assert client.post(payroll+'/finalize', json={'reviewed': True, 'input_hash': before_payment['input_hash']}).status_code == 409

    payment = {'calculation_id': preview['calculation_id'], 'amount': preview['suggested_amount']}
    result = client.post(ft_advance+'/payment', json=payment)
    assert result.status_code == 200
    assert client.post(ft_advance+'/payment', json=payment).json() == result.json()
    assert client.post(ft_advance+'/payment', json={**payment, 'amount': 100000}).status_code == 409

    client.post('/api/auth/logout')
    assert client.post('/api/auth/login', json={'username':'ft-staff','password':'ft-staff-password'}).status_code == 200
    assert client.get(payroll).status_code == 404
    personal = client.get(payroll+'/planning').json()
    assert set(personal['advances']) == {ft}
    assert personal['advances'][ft]['paid_amount'] == 855000
    assert client.post(ft_advance).status_code == 403
    client.post('/api/auth/logout')
    assert client.post('/api/auth/login', json={'username':'manager','password':'test-enrollment-password'}).status_code == 200

    Clock.current = core.dt('2026-10-31T23:59:00')
    assert client.post(payroll+'/finalize', json={'reviewed': True, 'input_hash': before_payment['input_hash']}).status_code == 409
    settled = calculate()
    row = next(row for row in settled['rows'] if row['employee_id'] == ft)
    assert row['insurance'] == 1092000 and row['tax'] == 0
    assert row['advance_paid'] == 855000 and row['balance_due'] == row['net'] - 855000 < 0
    finished = client.post(payroll+'/finalize', json={'reviewed': True, 'input_hash': settled['input_hash']})
    assert finished.status_code == 200, finished.text
    assert client.get(payroll+'/export').content[:2] == b'PK'


def test_employee_account_daily_earnings_and_sign_out(env, monkeypatch):
    app, client, *_ = env
    month = '2026-10'
    self_url = f'/api/hrm/self?month={month}'
    accounts = '/api/hrm/auth/employee-accounts'

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return core.dt('2026-10-19T18:00:00').astimezone(tz)

    monkeypatch.setattr(api, 'datetime', Clock)
    employee, colleague = [
        profile(client, contract_type='PT', primary_shift='PT_AM', base_salary=None, hourly_rate=30000).json()['employee_id']
        for _ in range(2)
    ]
    contract = dict(resident=True, nationality='VN', document_type='labor', duration_months=12,
                    valid_from=month, valid_until=month, agreed_monthly_hours=30)
    with app.state.session_factory() as con:
        store.put(con, 'payroll_config', month, {
            'payroll_2026_policy': core.load_policy(), 'contracts': {employee: contract, colleague: contract},
        })
        store.put(con, 'payroll', month, {
            'status': 'draft', 'rows': [{'employee_id': employee, 'net': 123000}, {'employee_id': colleague, 'net': 89000}],
        })
        con.commit()

    credentials = {'username': 'quay-staff', 'password': 'test-quay-password'}
    account = client.post(accounts, json={**credentials, 'employee_id': employee})
    assert account.status_code == 201, account.text
    assert account.json() == {'employee_id': employee, 'username': credentials['username'], 'role': 'employee'}
    assert client.post(accounts, json={**credentials, 'username': 'duplicate', 'employee_id': employee}).status_code == 409
    assert client.get('/admin.html').status_code == 200
    assert client.get(self_url).status_code == 403

    for eid, day, out in [(employee, '02', '12:30'), (employee, '03', None),
                          (employee, '25', None), (colleague, '02', '12:30')]:
        key = f'{eid}-{day}'
        shift_data = dict(shift_id=key, employee_id=eid, branch_id='CN01',
                          start=f'{month}-{day}T07:00:00', end=f'{month}-{day}T12:00:00',
                          approved_ot_minutes=30)
        assert client.put('/api/hrm/shifts', json=shift_data).status_code == 200
        if day != '25':
            assert event(client, eid, 'IN', shift_data['start'], key).status_code == 200
        if out:
            assert event(client, eid, 'OUT', f'{month}-{day}T{out}:00', key).status_code == 200

    assert client.post('/api/auth/logout').status_code == 200
    guard = client.get('/admin.html', follow_redirects=False)
    assert guard.status_code == 303 and guard.headers['location'].startswith('/login.html?next=')
    assert client.get('/', follow_redirects=False).headers['location'] == '/login.html'
    assert client.get('/login.html').status_code == 200
    assert client.get(self_url).status_code == 401
    assert client.post('/api/auth/login', json=credentials).json()['role'] == 'employee'
    assert client.get('/admin.html', follow_redirects=False).headers['location'] == '/employee.html'
    assert client.get('/portal.html', follow_redirects=False).headers['location'] == '/employee.html'
    assert client.get('/employee.html').status_code == 200
    assert client.get('/api/analytics/summary').status_code == 403
    assert client.post(accounts, json={**credentials, 'employee_id': colleague}).status_code == 403

    personal = client.get(self_url + '&employee_id=' + colleague).json()
    assert personal['profile']['employee_id'] == employee
    assert {row['employee_id'] for row in personal['shifts'] + personal['attendance']} == {employee}
    assert [row['work_date'] for row in personal['daily']] == [f'{month}-02', f'{month}-03']
    verified, missing = personal['daily']
    assert (verified['base_pay'], verified['ot_pay'], verified['amount']) == (150000, 22500, 172500)
    assert missing['amount'] is None and missing['pending_shift_count'] == 1
    assert personal['monthly'] is None

    with app.state.session_factory() as con:
        snapshot = store.get(con, 'payroll', month)
        snapshot['status'] = 'finalized'
        store.put(con, 'payroll', month, snapshot)
        con.commit()
    assert client.get(self_url).json()['monthly']['net'] == 123000
    assert client.post('/api/auth/logout').status_code == 200
    assert client.get(self_url).status_code == 401


def test_staff_registration_requires_manager_approval(env):
    app, client, *_ = env
    employee = profile(client, role='quan_ly').json()['employee_id']
    endpoint = '/api/hrm/auth/employee-registrations'
    register = '/api/hrm/auth/employee-register'
    decision = f'{endpoint}/{employee}'
    manager = {'username': 'manager', 'password': 'test-enrollment-password'}
    credentials = {'username': 'new-quay-staff', 'password': 'test-quay-password'}
    body = {**credentials, 'employee_id': employee}
    assert client.post('/api/auth/logout').status_code == 200
    assert client.get(endpoint).status_code == 401
    assert client.post(register, json={**body, 'role': 'manager'}).status_code == 422
    assert client.post(register, json={**body, 'employee_id': 'UNKNOWN'}).status_code == 422
    assert client.post(register, json={**body, 'username': 'manager'}).status_code == 409
    response = client.post(register, json=body)
    assert response.status_code == 202, response.text
    assert response.json() == {'status': 'pending', 'username': credentials['username']}
    assert client.post(register, json=body).status_code == 409
    assert client.post('/api/auth/login', json=credentials).status_code == 401
    with app.state.session_factory() as con:
        pending = store.get(con, hrm_auth.REGISTRATION_KIND, employee)
        assert pending['password_hash'] != credentials['password']

    assert client.post('/api/auth/login', json=manager).status_code == 200
    request, = client.get(endpoint).json()
    assert request['employee_id'] == employee and 'password_hash' not in request
    old_id = request['request_id']
    assert client.post(decision, json={'request_id': old_id, 'approved': False}).json()['status'] == 'rejected'
    client.post('/api/auth/logout')
    assert client.post(register, json=body).status_code == 202
    assert client.post(decision, json={'request_id': old_id, 'approved': True}).status_code == 401

    assert client.post('/api/auth/login', json=manager).status_code == 200
    request, = client.get(endpoint).json()
    assert client.post(decision, json={'request_id': old_id, 'approved': True}).status_code == 409
    assert client.post(decision, json={'request_id': request['request_id'], 'approved': True}).json()['status'] == 'approved'
    assert client.get(endpoint).json() == []
    client.post('/api/auth/logout')
    assert client.post('/api/auth/login', json=credentials).json()['role'] == 'employee'
    assert client.get('/api/hrm/auth/me').json()['employee_id'] == employee
    assert client.get('/admin.html', follow_redirects=False).headers['location'] == '/employee.html'
    assert client.get(endpoint).status_code == 403


def test_admin_dashboard_uses_branch_records_and_skips_test_events(env, monkeypatch):
    app, client, *_ = env
    staff = profile(client).json()['employee_id']
    outside = profile(client, branch_id='CN02').json()['employee_id']
    base = '/api/analytics/branch-dashboard'

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return core.dt('2026-11-20T10:00:00').astimezone(tz)

    monkeypatch.setattr(analytics, 'datetime', Clock)
    with app.state.session_factory() as con:
        for key, employee, branch, source in [
            ('live', staff, 'CN01', 'SCHEDULE'),
            ('simulated', 'NV0001', 'CN01', 'GENERATED_TEST'),
            ('other-branch', outside, 'CN02', 'SCHEDULE'),
        ]:
            store.put(con, 'shifts', key, dict(
                shift_id=key, employee_id=employee, branch_id=branch, start='2026-11-19T07:00:00+07:00',
                end='2026-11-19T15:00:00+07:00', break_minutes=0, approved_ot_minutes=60,
                ot_multiplier=1.5, source=source,
            ))
            for direction, stamp in [('IN', '07:00:00'), ('OUT', '15:30:00')]:
                event_id = key + '-' + direction
                store.put(con, 'events', event_id, dict(event_id=event_id, employee_id=employee, shift_id=key,
                          scan_type=direction, ts='2026-11-19T'+stamp+'+07:00',
                          source='GENERATED_TEST' if key=='simulated' else 'MANUAL'))
        store.put(con, 'events', 'test-out', dict(event_id='test-out', employee_id=staff, shift_id='live',
                  scan_type='OUT', ts='2026-11-19T16:00:00+07:00', source='TEST_SQL'))
        store.put(con, 'payroll', '2026-11', dict(status='draft', source='WORKFLOW', rows=[
            dict(employee_id=staff, gross=500000, employer_insurance=50000, net=455000),
            dict(employee_id=outside, gross=600000, employer_insurance=60000, net=533000),
        ]))
        store.put(con, 'payroll', '2026-10', dict(status='draft', source='GENERATED_TEST', rows=[]))
        con.commit()

    today = client.get(base).json()
    assert today['attendance'] == [] and today['checkins'] == 0
    assert today['latest_date'] == '2026-11-19'
    report = client.get(base, params={'day': '2026-11-19', 'days': '1'}).json()
    assert report['branch']['id'] == 'CN01'
    assert (report['active_employees'], report['scheduled_employees'], report['checked_in_employees']) == (2, 1, 1)
    assert report['chart'][7]['count'] == report['checkins'] == 1
    assert report['ot_hours'] == 0.5 and len(report['events']) == 2
    assert report['payroll'] == {'status': 'draft', 'employee_count': 1, 'cost': 550000, 'net': 455000}
    week = client.get(base, params={'day': '2026-11-19', 'days': '7'}).json()
    assert len(week['chart']) == 7 and week['chart'][-1]['count'] == 1
    assert client.get(base, params={'day': '2026-10-15'}).json()['payroll'] == {'status': 'test_data'}
    csv = client.get(base+'/export', params={'day': '2026-11-19'})
    assert csv.status_code == 200 and 'live' in csv.text and 'simulated' not in csv.text and 'CN02' not in csv.text
    assert 'work_date' in client.get(base+'/export').text
    assert client.get('/api/hrm/attendance?month=2026-11&branch_id=CN01').json()[0]['branch_id'] == 'CN01'
    client.post('/api/auth/logout')
    assert client.get(base).status_code == 401
