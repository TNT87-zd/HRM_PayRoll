"""Registration API tests: isolated SQLite/files, no camera or personal data writes."""
import io
import json
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from config import CONSENT_VERSION, POSES, Settings
from cv.head_pose import Pose, angles_from_matrix, classify_pose
from cv.types import DetectedFace, FaceQualityReport
from main import create_app
from models import AttendanceRecord, Employee, EnrollmentSession, FaceSample, FaceTemplate, User
from routers.auth import hash_password
from services.face_service import FaceService


class FakeEngine:
    def __init__(self):
        self.vector = np.eye(2, 512, dtype=np.float32)[0]
        self.queue = []
        self.invalid = False

    def extract_single_face(self, image, **kwargs):
        vector = self.queue.pop(0) if self.queue else self.vector
        report = FaceQualityReport(is_valid=not self.invalid, num_faces=1, det_score=.99,
            face_width=190, face_height=190, blur_score=200, brightness=120,
            reasons=['too_blurry'] if self.invalid else [])
        face = DetectedFace(bbox=np.array([30, 30, 220, 220]), det_score=.99,
            kps=np.array([[80,80],[170,80],[125,125],[90,165],[160,165]]),
            embedding=vector, aligned_face=cv2.resize(image[30:220,30:220],(112,112)))
        return face, report


class FakePose:
    def __init__(self):
        self.queue = []
    def analyze(self, image):
        return self.queue.pop(0) if self.queue else Pose(0,0,0)
    def close(self):
        pass


@pytest.fixture
def env(tmp_path):
    data = tmp_path / 'data'
    (data/'clean').mkdir(parents=True)
    (data/'raw').mkdir()
    (data/'clean/branches.csv').write_text('branch_id,branch_name\nCN01,Chi nhánh 1\nCN02,Chi nhánh 2\n')
    (data/'raw/shifts.csv').write_text('shift_id,shift_name,contract_type,start_time,end_time\nFT_AM,Ca sáng,FT,07:00,15:00\nPT_AM,Ca bán thời gian,PT,07:00,11:00\n')
    (data/'clean/employees.csv').write_text('employee_id,full_name,branch_id,role,contract_type,primary_shift,hire_date,base_salary,hourly_rate\nNV0001,Nhân viên gốc,CN01,phuc_vu,FT,FT_AM,2026-01-01,8000000,\n')
    settings = Settings(data_dir=data, storage_dir=tmp_path/'private')
    engine, pose = FakeEngine(), FakePose()
    app = create_app(settings, engine, pose)
    @app.middleware('http')
    async def local_test_peer(request, call_next):
        request.scope['client'] = ('127.0.0.1', 12345)
        return await call_next(request)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        response = client.post('/api/auth/setup', json={'username':'manager','password':'test-enrollment-password'})
        assert response.status_code == 200
        yield app, client, engine, pose


def profile(client, key=None, **changes):
    body = dict(full_name='Nguyễn Văn A', branch_id='CN01', role='phuc_vu', contract_type='FT',
                primary_shift='FT_AM', hire_date='2026-11-03', base_salary=8500000, hourly_rate=None)
    body.update(changes)
    return client.post('/api/employees', json=body, headers={'Idempotency-Key':key or str(uuid.uuid4())})


def start(client, employee_id):
    response = client.post(f'/api/employees/{employee_id}/face/sessions',
        json={'consent':True,'consent_version':CONSENT_VERSION}, headers={'Idempotency-Key':str(uuid.uuid4())})
    assert response.status_code == 201, response.text
    return response.json()


def picture(seed):
    image = np.random.default_rng(seed).integers(30,220,(256,256,3),dtype=np.uint8)
    return cv2.imencode('.jpg', image)[1].tobytes()


def upload(env, employee_id, session, poses=None, images=None, declared=None):
    app, client, engine, estimator = env
    poses = poses or [pose for pose in POSES for _ in range(2)]
    rotations = {'front':Pose(0,0,0),'left':Pose(22,0,0),'right':Pose(-22,0,0),'up':Pose(0,-15,0),'down':Pose(0,15,0)}
    estimator.queue = [rotations[pose] for pose in poses]
    now = time.time()
    metadata = [{'sample_id':str(uuid.uuid4()), 'pose':pose,'captured_at':now-4+index*.35} for index,pose in enumerate(declared or poses)]
    blobs = images or [picture(index + 10) for index in range(len(poses))]
    response = client.post(f'/api/employees/{employee_id}/face/sessions/{session["session_id"]}/samples',
        files=[('files',(f'{index}.jpg',blob,'image/jpeg')) for index,blob in enumerate(blobs)],
        data={'manifest':json.dumps(metadata)})
    return response, metadata, blobs


def completed(env, employee_id):
    session = start(env[1], employee_id)
    response, _, _ = upload(env, employee_id, session)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'ready_to_commit', response.text
    response = env[1].post(f'/api/employees/{employee_id}/face/sessions/{session["session_id"]}/commit')
    assert response.status_code == 200, response.text
    assert response.json()['ready']
    return response.json()


def test_profile_auth_and_reference_validation(env):
    app, client, *_ = env
    assert client.get('/enroll.html').status_code == 200
    assert client.get('/api/employees/NV9999').status_code == 404
    assert profile(client, branch_id='UNKNOWN').status_code == 422
    assert profile(client, primary_shift='PT_AM').status_code == 422
    assert profile(client, base_salary=None).status_code == 422
    assert profile(client, full_name=' ').status_code == 422
    response = profile(client, contract_type='PT', primary_shift='PT_AM', base_salary=None, hourly_rate=28000)
    assert response.status_code == 201
    assert response.json()['hourly_rate'] == 28000
    assert response.json()['employee_id'] == 'NV0002'
    client.cookies.clear()
    assert client.get('/api/employees').status_code == 401
    assert profile(client).status_code == 401


def test_idempotent_profile_and_concurrent_ids(env):
    app, client, *_ = env
    key = str(uuid.uuid4())
    first, second = profile(client, key), profile(client, key)
    assert first.json()['employee_id'] == second.json()['employee_id']
    assert profile(client, key, full_name='Tên khác').status_code == 409
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: profile(client), range(8)))
    assert all(response.status_code == 201 for response in responses), [r.text for r in responses]
    assert len({r.json()['employee_id'] for r in responses}) == 8


def test_consent_owner_and_expiry(env):
    app, client, *_ = env
    employee = profile(client).json()['employee_id']
    url = f'/api/employees/{employee}/face/sessions'
    for body in ({}, {'consent':False,'consent_version':CONSENT_VERSION}, {'consent':True,'consent_version':'old'}):
        assert client.post(url,json=body,headers={'Idempotency-Key':str(uuid.uuid4())}).status_code == 422
    session = start(client,employee)
    assert client.get(f'/api/employees/NV0001/face/sessions/{session["session_id"]}').status_code == 404
    with app.state.session_factory() as db:
        db.get(EnrollmentSession,session['session_id']).expires_at = time.time()-1
        db.commit()
    assert client.get(f'{url}/{session["session_id"]}').status_code == 410
    assert client.get(f'/api/employees/{employee}').status_code == 200


def test_backend_rejects_wrong_pose_and_duplicate(env):
    employee = profile(env[1]).json()['employee_id']
    session = start(env[1],employee)
    result, *_ = upload(env,employee,session,poses=['front']*10,declared=[p for p in POSES for _ in range(2)])
    assert result.status_code == 200
    assert len(result.json()['rejected_samples']) == 8
    assert result.json()['status'] == 'capturing'
    assert env[1].post(f'/api/employees/{employee}/face/sessions/{session["session_id"]}/commit').status_code == 422
    other = start(env[1],employee)
    result,*_ = upload(env,employee,other,poses=['front','front'],images=[picture(4)]*2)
    assert result.json()['rejected_samples'][0]['reasons'] == ['duplicate_image']


def test_complete_persists_all_vectors_and_private_images(env):
    app,client,engine,_ = env
    employee = profile(client).json()['employee_id']
    session = completed(env,employee)
    url = f'/api/employees/{employee}/face/sessions/{session["session_id"]}'
    assert client.post(f'{url}/commit').json()['gallery_version'] == session['gallery_version']
    with app.state.session_factory() as db:
        record = db.get(Employee,employee)
        template = db.get(FaceTemplate,record.active_template_id)
        assert template.vector_count == 11
        assert len(template.vectors) == 11*512*4
        assert np.allclose(np.linalg.norm(np.frombuffer(template.vectors,np.float32).reshape(11,512),axis=1),1)
        samples = db.scalars(select(FaceSample).where(FaceSample.session_id==session['session_id'])).all()
        assert len(samples) == 10
        assert all(app.state.enrollment.path(s.path).is_file() for s in samples)
        sample_id = samples[0].id
    reloaded = FaceService(app.state.settings,app.state.session_factory,engine)
    reloaded.startup()
    assert reloaded.gallery[employee].shape == (11,512)
    image_url = f'{url}/samples/{sample_id}/image'
    assert client.get(image_url).status_code == 200
    assert client.delete(url).status_code == 409
    client.cookies.clear()
    assert client.get(image_url).status_code == 401
    assert client.get('/data/private/hrm.sqlite3').status_code == 404


def test_upload_retry_is_idempotent_and_cancel_cleans_files(env):
    app,client,*_ = env
    employee = profile(client).json()['employee_id']; session = start(client,employee)
    response,metadata,blobs = upload(env,employee,session,poses=['front','front'])
    assert response.status_code == 200
    url=f'/api/employees/{employee}/face/sessions/{session["session_id"]}'
    again=client.post(f'{url}/samples',files=[('files',('x.jpg',b,'image/jpeg')) for b in blobs],data={'manifest':json.dumps(metadata)})
    assert again.status_code==200 and again.json()['pose_counts']['front']==2
    assert client.delete(url).status_code==200
    assert not app.state.enrollment.path(f'face/staging/{session["session_id"]}').exists()
    assert client.get(f'/api/employees/{employee}').json()['has_face'] is False


def test_reenrollment_failure_keeps_active_template(env):
    app,client,engine,_ = env
    employee = profile(client).json()['employee_id']; completed(env,employee)
    with app.state.session_factory() as db: old_id=db.get(Employee,employee).active_template_id
    session=start(client,employee)
    engine.queue=[engine.vector]*9+[np.eye(2,512,dtype=np.float32)[1]]
    upload(env,employee,session)
    response=client.post(f'/api/employees/{employee}/face/sessions/{session["session_id"]}/commit')
    assert response.status_code==422
    assert response.json()['detail']['code']=='inconsistent_identity'
    with app.state.session_factory() as db: assert db.get(Employee,employee).active_template_id==old_id
    assert client.get(f'/api/employees/{employee}').json()['has_face']


def test_commit_database_failure_rolls_back_files_and_template(env):
    app,client,*_=env
    employee=profile(client).json()['employee_id']; session=start(client,employee)
    upload(env,employee,session)
    original=Session.commit
    def fail_template_commit(db):
        if any(isinstance(item,FaceTemplate) for item in db.new): raise RuntimeError('simulated disk failure')
        return original(db)
    with patch.object(Session,'commit',fail_template_commit):
        with pytest.raises(RuntimeError,match='simulated disk failure'):
            client.post(f'/api/employees/{employee}/face/sessions/{session["session_id"]}/commit')
    with app.state.session_factory() as db: assert db.get(Employee,employee).active_template_id is None
    assert app.state.enrollment.path(f'face/staging/{session["session_id"]}').is_dir()
    assert client.post(f'/api/employees/{employee}/face/sessions/{session["session_id"]}/commit').json()['ready']


def test_preview_no_attendance_and_kiosk_deduplication(env,monkeypatch):
    app,client,*_=env
    from routers import analytics
    monkeypatch.setattr(analytics,'DATA',app.state.settings.data_dir/'clean')
    monkeypatch.setattr(analytics,'_CACHE',{})
    employee=profile(client).json()['employee_id']; completed(env,employee)
    files=[('files',('query.jpg',picture(seed),'image/jpeg')) for seed in range(40,43)]
    preview=client.post(f'/api/employees/{employee}/face/verify-preview',files=files)
    assert preview.json()['verified_expected'] and preview.json()['recorded'] is False
    with app.state.session_factory() as db: assert db.scalar(select(func.count()).select_from(AttendanceRecord))==0
    for index in range(2):
        response=client.post('/api/kiosk/recognize',files=files,data={'device_id':'CN01-TB01','scan_type':'IN'})
        assert response.status_code==200,response.text
        assert response.json()['recorded'] is (index==0)
    with app.state.session_factory() as db: assert db.scalar(select(func.count()).select_from(AttendanceRecord))==1
    assert sum(client.get('/api/analytics/by-hour').json()['values'])==1


def test_unstable_group_and_inactive_employee(env):
    app,client,engine,_=env
    first=profile(client).json()['employee_id']; completed(env,first)
    second=profile(client).json()['employee_id']
    engine.vector=np.eye(2,512,dtype=np.float32)[1]; completed(env,second)
    files=[('files',('query.jpg',picture(seed),'image/jpeg')) for seed in range(3)]
    engine.queue=[np.eye(2,512,dtype=np.float32)[index] for index in (0,1,0)]
    response=client.post('/api/kiosk/recognize',files=files,data={'device_id':'test','scan_type':'IN'})
    assert response.json()['reason']=='unstable_identity' and not response.json()['matched']
    assert client.patch(f'/api/employees/{second}',json={'employment_status':'inactive'}).status_code==200
    assert second not in app.state.face.gallery


def test_permissions_and_csrf(env):
    app,client,*_=env
    assert client.post('/api/employees',json={},headers={'Origin':'https://untrusted.example'}).status_code==403
    with app.state.session_factory() as db:
        db.add(User(username='employee',password_hash=hash_password('employee-test-password'),role='employee'))
        db.commit()
    client.cookies.clear()
    assert client.post('/api/auth/login',json={'username':'employee','password':'employee-test-password'}).status_code==200
    assert client.get('/api/employees').status_code==403


def test_server_rejects_invalid_image_and_legacy_bypass(env):
    app,client,*_=env
    employee=profile(client).json()['employee_id']; session=start(client,employee)
    response,*_=upload(env,employee,session,poses=['front'],images=[b'not an image'])
    assert response.json()['rejected_samples'][0]['reasons']==['invalid_image']
    old=client.post(f'/api/employees/{employee}/face/enroll',files=[('files',('x.jpg',picture(1),'image/jpeg'))])
    assert old.status_code==400
    old=client.post(f'/api/employees/{employee}/face/enroll',files=[('files',('x.jpg',picture(1),'image/jpeg'))],data={'consent':'true'})
    assert old.status_code==422


def test_pose_boundaries_and_matrix_convention():
    assert classify_pose(Pose(22,0,0))=='left'
    assert classify_pose(Pose(-22,0,0))=='right'
    assert classify_pose(Pose(0,15,0))=='down'
    assert classify_pose(Pose(0,-15,0))=='up'
    assert classify_pose(Pose(40,0,0)) is None
    assert classify_pose(Pose(0,0,20)) is None
    angle=np.deg2rad(20)
    matrix=np.array([[np.cos(angle),0,np.sin(angle),0],[0,1,0,0],[-np.sin(angle),0,np.cos(angle),0],[0,0,0,1]])
    assert angles_from_matrix(matrix).yaw==pytest.approx(20)


def test_sample_replacement_and_owner_access(env):
    app,client,*_=env
    employee=profile(client).json()['employee_id']; session=start(client,employee)
    response,*_=upload(env,employee,session,poses=['front','front'])
    sample=response.json()['samples'][0]['sample_id']
    url=f'/api/employees/{employee}/face/sessions/{session["session_id"]}'
    assert client.delete(f'{url}/samples/{sample}').json()['pose_counts']['front']==1
    with app.state.session_factory() as db:
        db.add(User(username='other_manager',password_hash=hash_password('other-manager-password'),role='manager'));db.commit()
    client.cookies.clear()
    client.post('/api/auth/login',json={'username':'other_manager','password':'other-manager-password'})
    assert client.get(url).status_code==404
    assert client.post(f'{url}/commit').status_code==404


def test_duplicate_identity_and_config_change_do_not_activate(env):
    app,client,*_=env
    first=profile(client).json()['employee_id']; completed(env,first)
    second=profile(client).json()['employee_id']; session=start(client,second)
    upload(env,second,session)
    url=f'/api/employees/{second}/face/sessions/{session["session_id"]}'
    response=client.post(f'{url}/commit')
    assert response.status_code==409 and response.json()['detail']['code']=='duplicate_identity'
    with app.state.session_factory() as db: assert db.get(Employee,second).active_template_id is None
    app.state.settings.preprocessing_version='different-policy-v2'
    assert client.post(f'{url}/commit').status_code==409


def test_crash_recovery_and_retention_keep_active_files(env):
    app,client,*_=env
    employee=profile(client).json()['employee_id']; session=start(client,employee)
    upload(env,employee,session)
    service=app.state.enrollment
    staging=service.path(f'face/staging/{session["session_id"]}')
    final=service.path(f'face/enrollments/{employee}/{session["session_id"]}')
    final.parent.mkdir(parents=True,exist_ok=True);staging.rename(final)
    with app.state.session_factory() as db: service.cleanup(db)
    assert staging.exists() and not final.exists()
    assert client.post(f'/api/employees/{employee}/face/sessions/{session["session_id"]}/commit').json()['ready']
    with app.state.session_factory() as db:
        record=db.get(Employee,employee);template=db.get(FaceTemplate,record.active_template_id)
        template.retired_at=1;db.commit();service.cleanup(db)
        assert db.get(FaceTemplate,record.active_template_id) is not None
    assert final.exists()


def test_inactive_cannot_enroll_and_wrong_setup_host_denied(env):
    _,client,*_=env
    employee=profile(client).json()['employee_id']
    assert client.patch(f'/api/employees/{employee}',json={'employment_status':'inactive'}).status_code==200
    response=client.post(f'/api/employees/{employee}/face/sessions',json={'consent':True,'consent_version':CONSENT_VERSION},headers={'Idempotency-Key':str(uuid.uuid4())})
    assert response.status_code==409
    assert client.get('/api/auth/status',headers={'Host':'untrusted.example'}).json()['local_setup_allowed'] is False


def test_experimental_filters_do_not_mutate_baseline():
    from cv.preprocessing import POLICIES,enhance_face
    image=np.random.default_rng(44).integers(0,256,(112,112,3),dtype=np.uint8)
    original=image.copy()
    for policy in POLICIES:
        output=enhance_face(image,policy)
        assert output.shape==image.shape and output.dtype==np.uint8
        assert np.array_equal(image,original)
    assert np.array_equal(enhance_face(image,'baseline'),original)


def test_successful_replacement_retires_only_old_template(env):
    app,client,*_=env
    employee=profile(client).json()['employee_id']; first=completed(env,employee)
    second=completed(env,employee)
    assert first['gallery_version']!=second['gallery_version']
    with app.state.session_factory() as db:
        old=db.scalar(select(FaceTemplate).where(FaceTemplate.session_id==first['session_id']))
        old.retired_at=1;db.commit();old_id=old.id
        app.state.enrollment.cleanup(db)
        assert db.get(FaceTemplate,old_id) is None
        active=db.get(Employee,employee).active_template_id
        assert db.get(FaceTemplate,active).session_id==second['session_id']
    assert not app.state.enrollment.path(f'face/enrollments/{employee}/{first["session_id"]}').exists()
    assert app.state.enrollment.path(f'face/enrollments/{employee}/{second["session_id"]}').exists()


def test_calibration_metrics_count_wrong_identities_separately():
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
    from evaluate_face_policies import metrics
    captures=[
        {'truth':'A','candidate':'A','score':.8,'margin':.2},
        {'truth':'B','candidate':'A','score':.9,'margin':.2},
        {'truth':'C','candidate':None,'score':-1,'margin':-1},
        {'truth':None,'candidate':'A','score':.4,'margin':.2},
    ]
    result=metrics(captures,.55,.08)
    assert result['correct_known']==1 and result['wrong_identity']==1 and result['rejected_known']==1
    assert result['accepted_unknown']==0 and result['known_accept_rate']==pytest.approx(1/3)
