"""Create a small reproducible scenario; refuses to overwrite the demo employee."""
import sys
from pathlib import Path
from datetime import datetime,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parent/'app/backend/src'))
from hrm.store import init,db,get,put,audit
from hrm.core import VN
from hrm.api import record_event

def main():
    init()
    day=(datetime.now(VN)-timedelta(days=2)).date().isoformat()
    eid='DEMO01'
    with db(True) as con:
        if get(con,'employees',eid):
            raise SystemExit('DEMO01 đã tồn tại; không ghi đè.')
        put(con,'employees',eid,dict(employee_id=eid,full_name='Nhân viên demo',branch_id='CN01',contract_type='PT',base_salary=0,hourly_rate=50000,active=True))
        s=dict(shift_id='DEMO01-'+day,employee_id=eid,branch_id='CN01',start=day+'T08:00:00+07:00',end=day+'T16:00:00+07:00',break_minutes=0,approved_ot_minutes=60,ot_multiplier=1.5)
        put(con,'shifts',s['shift_id'],s)
        record_event(con,eid,'IN',day+'T08:00:00+07:00','demo-cli','DEMO',shift_id=s['shift_id'])
        record_event(con,eid,'OUT',day+'T17:00:00+07:00','demo-cli','DEMO',shift_id=s['shift_id'])
        audit(con,'demo-cli','demo_created',{'employee_id':eid})
    print('Đã tạo DEMO01; chọn kỳ',day[:7],': 8 giờ thường + 1 giờ OT, tổng 475.000 VND trước điều chỉnh.')

if __name__=='__main__':
    main()
