import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/backend/src'))
from hrm.store import init,db,password_hash
from hrm.core import timesheet
from main import app

@pytest.fixture
def clients(tmp_path,monkeypatch):
    monkeypatch.setenv('HRM_DB',str(tmp_path/'hrm.db'))
    monkeypatch.setenv('HRM_DISABLE_FACE','1')
    init()
    with db(True) as c:
        for name,role,eid in [('admin','hr',None),('employee','employee','NV0002'),('other','employee','NV0003')]:
            c.execute('INSERT INTO users VALUES(?,?,?,?)',(name,password_hash('test-password-123'),role,eid))
    with TestClient(app) as admin,TestClient(app) as emp,TestClient(app) as other:
        for client,name in [(admin,'admin'),(emp,'employee'),(other,'other')]:
            assert client.post('/api/hrm/auth/login',json={'username':name,'password':'test-password-123'}).status_code==200
        yield admin,emp,other

SHIFT={'shift_id':'S1','employee_id':'NV0002','branch_id':'CN01','start':'2025-10-06T08:00','end':'2025-10-06T16:00','break_minutes':0,'approved_ot_minutes':60,'ot_multiplier':1.5}
RUN={'standard_hours':208,'adjustments':{'NV0002':{'allowance':100000,'insurance':10000,'tax':20000}},'note':'Test cấu hình demo'}

def seed(admin,complete=True):
    assert admin.put('/api/hrm/employees',json={'employee_id':'NV0002','full_name':'Demo','branch_id':'CN01','contract_type':'PT','hourly_rate':50000}).status_code==200
    assert admin.put('/api/hrm/shifts',json=SHIFT).status_code==200
    for kind,stamp in [('IN','2025-10-06T08:00')]+([('OUT','2025-10-06T17:00')] if complete else []):
        assert admin.post('/api/hrm/events/manual',json={'employee_id':'NV0002','shift_id':'S1','scan_type':kind,'ts':stamp,'reason':'Demo kiểm thử'}).status_code==200

def test_full_workflow_and_isolation(clients):
    admin,emp,other=clients
    seed(admin)
    rows=admin.get('/api/hrm/attendance?month=2025-10').json()
    assert rows[0]['regular_hours']==8 and rows[0]['ot_hours']==1
    r=admin.post('/api/hrm/payroll/2025-10/calculate',json=RUN)
    assert r.status_code==200,r.text
    p=r.json()
    assert p['rows'][0]['gross']==575000
    assert p['rows'][0]['net']==545000
    assert emp.get('/api/hrm/payroll/2025-10').status_code==404
    r=admin.post('/api/hrm/payroll/2025-10/finalize',json={'reviewed':True,'input_hash':p['input_hash']})
    assert r.status_code==200,r.text
    assert len(emp.get('/api/hrm/payroll/2025-10').json()['rows'])==1
    assert other.get('/api/hrm/payroll/2025-10').json()['rows']==[]
    x=emp.get('/api/hrm/payroll/2025-10/export')
    assert x.status_code==200 and x.content[:2]==b'PK'
    assert admin.post('/api/hrm/payroll/2025-10/calculate',json=RUN).status_code==409
    assert admin.post('/api/hrm/events/manual',json={'employee_id':'NV0002','shift_id':'S1','scan_type':'OUT','ts':'2025-10-06T18:00','reason':'Không được đổi'}).status_code==409
    assert emp.put('/api/hrm/employees',json={'employee_id':'NV0002','full_name':'Hack','branch_id':'CN01','contract_type':'PT','hourly_rate':100000}).status_code==403
    assert emp.get('/api/hrm/audit').status_code==403
    assert emp.get('/api/analytics/summary').status_code==403
    assert other.get('/api/hrm/events?month=2025-10').json()==[]

def test_missing_checkout_cannot_finalize(clients):
    admin,_,_=clients
    seed(admin,False)
    p=admin.post('/api/hrm/payroll/2025-10/calculate',json=RUN).json()
    assert p['attendance'][0]['status']=='incomplete'
    assert admin.post('/api/hrm/payroll/2025-10/finalize',json={'reviewed':True,'input_hash':p['input_hash']}).status_code==409

def test_changed_inputs_require_recalculation(clients):
    admin,_,_=clients
    seed(admin)
    p=admin.post('/api/hrm/payroll/2025-10/calculate',json=RUN).json()
    assert admin.post('/api/hrm/events/manual',json={'employee_id':'NV0002','shift_id':'S1','scan_type':'OUT','ts':'2025-10-06T18:00','reason':'Bổ sung giờ ra'}).status_code==200
    assert admin.post('/api/hrm/payroll/2025-10/finalize',json={'reviewed':True,'input_hash':p['input_hash']}).status_code==409

def test_duplicate_and_shift_overlap(clients):
    admin,_,_=clients
    seed(admin)
    assert admin.put('/api/hrm/shifts',json=SHIFT|{'shift_id':'S2'}).status_code==409
    assert admin.put('/api/hrm/shifts',json=SHIFT|{'end':'2025-10-06T07:00'}).status_code==422
    assert admin.post('/api/hrm/events/manual',json={'employee_id':'NV0002','shift_id':'S1','scan_type':'IN','ts':'2025-10-06T08:00:30','reason':'Quét trùng'}).status_code==200
    assert len(admin.get('/api/hrm/events?month=2025-10').json())==2

def test_leave_approval_and_ownership(clients):
    admin,emp,other=clients
    seed(admin)
    body={'employee_id':'NV0002','start_date':'2025-10-06','end_date':'2025-10-06','leave_type':'PAID','reason':'Việc riêng'}
    assert other.post('/api/hrm/leaves',json=body).status_code==403
    l=emp.post('/api/hrm/leaves',json=body).json()
    assert emp.post('/api/hrm/leaves/'+l['leave_id']+'/decision',json={'status':'approved'}).status_code==403
    assert admin.post('/api/hrm/leaves/'+l['leave_id']+'/decision',json={'status':'approved'}).status_code==200
    p=admin.post('/api/hrm/payroll/2025-10/calculate',json=RUN).json()
    assert admin.post('/api/hrm/payroll/2025-10/finalize',json={'reviewed':True,'input_hash':p['input_hash']}).status_code==409

def test_paid_leave_without_events(clients):
    admin,emp,_=clients
    assert admin.put('/api/hrm/shifts',json=SHIFT).status_code==200
    l=emp.post('/api/hrm/leaves',json={'employee_id':'NV0002','start_date':'2025-10-06','end_date':'2025-10-06','leave_type':'PAID','reason':'Nghỉ đã duyệt'}).json()
    admin.post('/api/hrm/leaves/'+l['leave_id']+'/decision',json={'status':'approved'})
    r=admin.get('/api/hrm/attendance?month=2025-10').json()[0]
    assert r['paid_leave_hours']==8 and r['regular_hours']==0

def test_auth_logout_and_invalid_month(clients):
    admin,emp,_=clients
    assert admin.get('/api/hrm/attendance?month=oops').status_code==422
    emp.post('/api/hrm/auth/logout')
    assert emp.get('/api/hrm/employees').status_code==401
    with TestClient(app) as unauth:
        assert unauth.get('/api/hrm/employees').status_code==401
        assert unauth.post('/api/hrm/auth/login',json={'username':'admin','password':'bad'}).status_code==401

def test_cross_midnight_and_overtime_cap():
    s=SHIFT|{'start':'2025-10-06T22:00','end':'2025-10-07T06:00','break_minutes':30,'approved_ot_minutes':30}
    events=[{'shift_id':'S1','scan_type':'IN','ts':'2025-10-06T22:06'}, {'shift_id':'S1','scan_type':'OUT','ts':'2025-10-07T07:00'}]
    r=timesheet([s],events,[])[0]
    assert r['work_date']=='2025-10-06'
    assert r['regular_hours']==7.4 and r['ot_hours']==0.5 and r['late_minutes']==6
    assert 'unapproved_overtime_excluded' in r['flags']

def test_reject_nonfinite_and_negative_net(clients):
    admin,_,_=clients
    seed(admin)
    r=admin.post('/api/hrm/payroll/2025-10/calculate',json=RUN|{'adjustments':{'NV0002':{'tax':999999999}}})
    assert r.status_code==422
    assert admin.post('/api/hrm/payroll/2025-10/calculate',json=RUN|{'standard_hours':0}).status_code==422

def test_kiosk_writes_canonical_event(clients,monkeypatch):
    import types
    from datetime import datetime,timedelta
    from hrm.core import VN
    from services.face_service import face_service
    admin,emp,_=clients
    now=datetime.now(VN)
    s=SHIFT|{'shift_id':'LIVE1','start':(now-timedelta(hours=1)).isoformat(),'end':(now+timedelta(hours=7)).isoformat()}
    assert admin.put('/api/hrm/shifts',json=s).status_code==200
    monkeypatch.setattr(face_service,'engine',object())
    monkeypatch.setattr(face_service,'recognize',lambda *a,**k:dict(reason='accepted',matched=True,employee_id='NV0002',similarity=.8))
    monkeypatch.setitem(sys.modules,'cv2',types.SimpleNamespace(IMREAD_COLOR=1,imdecode=lambda *a:object()))
    form={'device_id':'CN01-TB01','scan_type':'IN','lat':'16.0471','lon':'108.2208'}
    r=admin.post('/api/kiosk/recognize',data=form,files={'file':('frame.jpg',b'fake image','image/jpeg')})
    assert r.status_code==200,r.text
    m=(now-timedelta(hours=1)).strftime('%Y-%m')
    rows=admin.get('/api/hrm/events?month='+m).json()
    assert len(rows)==1 and rows[0]['source']=='FACE'
    assert emp.post('/api/kiosk/recognize',data=form,files={'file':('frame.jpg',b'fake image','image/jpeg')}).status_code==403
    assert admin.post('/api/kiosk/recognize',data=form|{'device_id':'unknown'},files={'file':('frame.jpg',b'fake','image/jpeg')}).status_code==403

def test_login_throttling(clients):
    with TestClient(app) as c:
        for i in range(10):
            assert c.post('/api/hrm/auth/login',json={'username':'admin','password':'wrong'}).status_code==401
        assert c.post('/api/hrm/auth/login',json={'username':'admin','password':'wrong'}).status_code==429

def test_recalculated_adjustments_invalidate_old_review(clients):
    admin,_,_=clients
    seed(admin)
    old=admin.post('/api/hrm/payroll/2025-10/calculate',json=RUN).json()
    new=admin.post('/api/hrm/payroll/2025-10/calculate',json=RUN|{'adjustments':{}}).json()
    assert old['input_hash']!=new['input_hash']
    assert admin.post('/api/hrm/payroll/2025-10/finalize',json={'reviewed':True,'input_hash':old['input_hash']}).status_code==409

def test_face_voting_separates_in_out(monkeypatch):
    from services.face_service import FaceService
    svc=FaceService()
    monkeypatch.setattr(svc,'_recognize_once',lambda *a,**k:dict(reason='candidate',employee_id='NV0002',similarity=.8,matched=True))
    for _ in range(3):
        r=svc.recognize(None,'D',scan_type='IN')
    assert r['reason']=='accepted'
    for _ in range(3):
        r=svc.recognize(None,'D',scan_type='OUT')
    assert r['reason']=='accepted'
    assert svc.recognize(None,'D',scan_type='IN')['reason']=='duplicate'

def test_face_registration_requires_five_named_slots(clients,monkeypatch):
    import types
    import numpy as np
    from routers import employees as route
    from services.face_service import face_service
    from pathlib import Path
    import tempfile
    admin,_,_=clients
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)/'raw';root.mkdir()
        old=root/'NV0002';old.mkdir();(old/'front.jpg').write_bytes(b'original')
        monkeypatch.setattr(route,'FACE_RAW_DIR',root)
        def imwrite(path,img):
            Path(path).write_bytes(b'new image')
            return True
        monkeypatch.setitem(sys.modules,'cv2',types.SimpleNamespace(IMREAD_COLOR=1,imdecode=lambda *a:object(),imwrite=imwrite))
        result=types.SimpleNamespace(success=False,message='Ảnh mờ',embeddings=[])
        monkeypatch.setattr(face_service,'engine',types.SimpleNamespace(enroll_from_images=lambda *a,**k:result))
        files=[('files',(n+'.jpg',b'img','image/jpeg')) for n in ['front','left','right','under','up']]
        assert admin.post('/api/employees/NV0002/face/enroll',files=files[:3]).status_code==422
        assert admin.post('/api/employees/NV0002/face/enroll',files=files).status_code==422
        assert (old/'front.jpg').read_bytes()==b'original'
        result.success=True;result.embeddings=[np.ones(512)]*5;result.centroid_embedding=np.ones(512);result.mean_intra_similarity=.9
        r=admin.post('/api/employees/NV0002/face/enroll',files=files)
        assert r.status_code==200,r.text
        assert {p.name for p in old.iterdir()}=={'front.jpg','left.jpg','right.jpg','under.jpg','up.jpg'}
        assert list((root.parent/'backups'/'NV0002').rglob('front.jpg'))
