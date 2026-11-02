"""Run a browser smoke test with an isolated database and synthetic capture stream.

Uses a local Chrome installation and the pinned MediaPipe Web assets. No physical
camera, real employee writes or attendance events are used by this test.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import uvicorn

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'app/backend/src'))
sys.path.insert(0, str(ROOT/'app/backend/tests'))
from config import Settings
from main import create_app
from test_enrollment import FakeEngine, FakePose
from cv.head_pose import Pose
from fastapi import Depends
from fastapi.responses import FileResponse
from routers.auth import require_hr


def main():
    from playwright.sync_api import sync_playwright
    parser=argparse.ArgumentParser()
    parser.add_argument('--face-image',type=Path)
    parser.add_argument('--chrome',default='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    parser.add_argument('--port',type=int,default=8768)
    parser.add_argument('--screenshot',default='/private/tmp/hrm-registration-ui.png')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='hrm-browser-') as directory:
        data=Path(directory)/'data'
        for relative in ('clean/employees.csv','clean/branches.csv','raw/shifts.csv'):
            target=data/relative; target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/'data'/relative,target)
        estimator=FakePose()
        estimator.queue=[pose for pose in (Pose(0,0,0),Pose(22,0,0),Pose(-22,0,0),Pose(0,-15,0),Pose(0,15,0)) for _ in range(2)]
        app=create_app(Settings(data_dir=data,storage_dir=Path(directory)/'private'),FakeEngine(),estimator)
        if args.face_image:
            @app.get('/__test__/face.jpg')
            def test_face(user=Depends(require_hr)):
                return FileResponse(args.face_image.resolve())
            # Register the test-only fixture before the catch-all static mount.
            app.router.routes.insert(-1, app.router.routes.pop())
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=args.port,log_level='warning'))
        thread=threading.Thread(target=server.run,daemon=True); thread.start()
        deadline=time.monotonic()+20
        while not server.started:
            if time.monotonic()>deadline: raise RuntimeError('Test server failed to start')
            time.sleep(.1)
        try:
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(executable_path=args.chrome,headless=True,args=['--no-sandbox'])
                context=browser.new_context(viewport={'width':1440,'height':1100})
                page=context.new_page(); errors=[]
                page.on('pageerror',lambda error: errors.append(str(error)))
                base=f'http://127.0.0.1:{args.port}'
                page.goto(base+'/enroll.html')
                page.get_by_label('Tên đăng nhập').fill('browser_manager')
                page.get_by_label('Mật khẩu',exact=True).fill('browser-test-password')
                page.get_by_role('button',name='Tạo tài khoản',exact=True).click()
                page.wait_for_selector('#authModal[hidden]',state='attached')
                page.locator('#fullName').fill('Nhân viên kiểm thử giao diện')
                page.locator('#branchId').select_option('CN01')
                page.locator('#role').select_option('phuc_vu')
                shift=page.locator('#primaryShift option').evaluate_all('(options)=>options.find(o=>o.value)?.value')
                page.locator('#primaryShift').select_option(shift)
                page.locator('#salary').fill('8500000')
                page.get_by_role('button',name='Lưu hồ sơ',exact=True).click()
                page.wait_for_function("document.querySelector('#profileMessage').textContent.includes('Đã lưu hồ sơ')")
                employee_id=page.locator('#profileBadge').inner_text()
                page.screenshot(path=args.screenshot,full_page=True)
                pose_result=None
                if args.face_image:
                    pose_result=page.evaluate('''async () => {
                      const worker=new Worker('/js/face-worker.js');
                      try {
                        await new Promise((resolve,reject)=>{
                          const timer=setTimeout(()=>reject(new Error('Worker init timeout')),20000);
                          worker.onerror=e=>reject(new Error(e.message));
                          worker.onmessage=({data})=>{if(data.type==='ready'){clearTimeout(timer);resolve();} else if(data.type==='error')reject(new Error(data.message));};
                          worker.postMessage({type:'init'});
                        });
                        const image=await createImageBitmap(await (await fetch('/__test__/face.jpg')).blob());
                        return await new Promise((resolve,reject)=>{
                          worker.onmessage=({data})=>data.type==='error'?reject(new Error(data.message)):resolve(data);
                          worker.postMessage({type:'frame',image,timestamp:1000},[image]);
                        });
                      } finally {worker.terminate();}
                    }''')
                    assert pose_result['count']==1,pose_result
                    assert abs(pose_result['angles']['yaw'])<15,pose_result
                page.close()
                page=context.new_page(); page.on('pageerror',lambda error: errors.append(str(error)))
                page.add_init_script('''
                  navigator.mediaDevices.getUserMedia=async()=>{
                    const canvas=document.createElement('canvas');canvas.width=1280;canvas.height=720;
                    const ctx=canvas.getContext('2d');
                    const draw=()=>{
                      const image=ctx.createImageData(1280,720);
                      for(let i=0;i<image.data.length;i+=4){const v=50+Math.random()*150;image.data[i]=v;image.data[i+1]=v;image.data[i+2]=v;image.data[i+3]=255;}
                      ctx.putImageData(image,0,0);
                    };
                    draw();setInterval(draw,80);return canvas.captureStream(20);
                  };
                  navigator.mediaDevices.enumerateDevices=async()=>[];
                  window.Worker=class{
                    constructor(){}
                    postMessage(message){
                      if(message.type==='init'){setTimeout(()=>this.onmessage({data:{type:'ready'}}),20);return;}
                      const text=document.querySelector('.pose.active')?.textContent||'';
                      const yaw=text.includes('trái')?22:text.includes('phải')?-22:0;
                      const pitch=text.includes('Ngước')?-15:text.includes('Cúi')?15:0;
                      message.image.close();
                      setTimeout(()=>this.onmessage({data:{type:'frame',count:1,bbox:[.25,.15,.5,.7],angles:{yaw,pitch,roll:0}}}),10);
                    }
                    terminate(){}
                  };
                ''')
                page.goto(base+'/enroll.html')
                page.wait_for_selector('#authModal[hidden]',state='attached')
                page.locator('#search').fill(employee_id)
                page.get_by_role('button',name='Nhân viên kiểm thử giao diện').click()
                page.locator('#consent').check()
                page.get_by_role('button',name='Bắt đầu quét',exact=True).click()
                page.wait_for_function("document.querySelector('#commitCapture').disabled===false",timeout=45000)
                page.get_by_role('button',name='Hoàn tất đăng ký',exact=True).click()
                page.wait_for_function("document.querySelector('#faceMessage').textContent.includes('thành công')")
                page.get_by_role('button',name='Quét thử',exact=True).click()
                page.wait_for_function("document.querySelector('#verifyMessage').textContent.includes('Nhận diện:')")
                assert not errors,errors
                page.screenshot(path=args.screenshot,full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
                browser.close()
                print(json.dumps({'browser_errors':errors,'employee_id':employee_id,'real_model_pose':pose_result,
                                  'synthetic_capture':'10/10, commit and preview passed','mobile_overflow':False,
                                  'screenshot':args.screenshot},ensure_ascii=False))
        finally:
            server.should_exit=True;thread.join(timeout=10)


if __name__=='__main__': main()
