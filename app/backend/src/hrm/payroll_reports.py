"""Authenticated monthly payroll snapshots and exports. No public static files."""
import csv
import hashlib
import io
import json
import os
import re
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from hrm import core
from hrm.store import get, settings

SUMMARY = [('employee_id','Mã NV'),('contract_type','FT/PT'),('gross','Lương gộp'),
           ('insurance','BH NLĐ'),('employer_insurance','BH DN'),('tax','Thuế'),('net','Thực lĩnh')]

def configuration(con, month):
    saved = get(con, 'payroll_config', month)
    if saved:
        return saved
    path = Path(core.__file__).with_name('payroll_contracts.json')
    if not path.is_file():
        raise ValueError('Chưa khai hợp đồng cho kỳ này. Nhập cấu hình hợp đồng trước khi tính lương.')
    return dict(payroll_2026_policy=core.load_policy(),
                contracts=json.loads(path.read_text(encoding='utf-8-sig')),
                source='CONTRACT_FILE')

def safe(value):
    if isinstance(value, (dict,list)):
        value=json.dumps(value,ensure_ascii=False)
    if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):
        return "'"+value
    return value

def csv_bytes(rows):
    out=io.StringIO(newline='')
    if rows:
        keys=list(dict.fromkeys(k for row in rows for k in row))
        writer=csv.DictWriter(out,keys)
        writer.writeheader()
        writer.writerows({k:safe(v) for k,v in row.items()} for row in rows)
    return out.getvalue().encode('utf-8-sig')

def workbook_bytes(p):
    wb=Workbook()
    wb.remove(wb.active)
    def sheet(name, rows, columns=None):
        ws=wb.create_sheet(name)
        columns=columns or [(k,k) for k in dict.fromkeys(k for r in rows for k in r)]
        ws.append([title for _,title in columns])
        for r in rows:
            ws.append([safe(r.get(k,'')) for k,_ in columns])
        ws.freeze_panes='C2'
        ws.auto_filter.ref=ws.dimensions
        for cell in ws[1]:
            cell.fill=PatternFill('solid',fgColor='3B2518')
            cell.font=Font(color='FFFFFF',bold=True)
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width=min(42,max(16,max(len(str(c.value or '')) for c in col[:30])+2))
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                if isinstance(cell.value,(float,int)) and not isinstance(cell.value,bool):
                    cell.number_format='#,##0.####'
        ws.sheet_properties.pageSetUpPr.fitToPage=True
        ws.page_setup.orientation='landscape'
        ws.page_setup.paperSize=ws.PAPERSIZE_A4
        ws.page_setup.fitToWidth=1
        ws.page_setup.fitToHeight=0
        ws.print_title_rows='1:1'
        return ws
    sheet('Bang luong',p['rows'],SUMMARY)
    sheet('Chi tiet',p['rows'])
    sheet('Bang cong',p.get('attendance',[]))
    sheet('Nguon du lieu',[dict(month=p['month'],status=p['status'],run_id=p.get('run_id',''),
        calculated_at=p.get('calculated_at',''),finalized_at=p.get('finalized_at',''),
        input_hash=p.get('input_hash',''),source=p.get('source',''),
        note=p.get('parameters',{}).get('note',''))])
    out=io.BytesIO(); wb.save(out)
    return out.getvalue()

def archive(p):
    """Atomic file replacement; database remains the canonical snapshot.

    Export can rebuild missing files after a disk failure. A DB rollback may leave
    an unreferenced directory; it cannot be accessed through the API.
    """
    if not re.fullmatch(r'\d{4}-\d{2}',p['month']) or not re.fullmatch(r'[a-f0-9]{32}',p['run_id']):
        raise ValueError('Mã kỳ hoặc lần tính không hợp lệ')
    if p['status'] not in ('draft','finalized'):
        raise ValueError('Trạng thái không hợp lệ')
    folder=settings().data_dir/'reports'/'payroll'/p['month']/p['run_id']/p['status']
    folder.mkdir(parents=True,exist_ok=True)
    files={'payroll.xlsx':workbook_bytes(p),'attendance.csv':csv_bytes(p.get('attendance',[])),
           'payroll.json':json.dumps(p,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')}
    files['checksums.json']=json.dumps({n:hashlib.sha256(b).hexdigest() for n,b in files.items()},indent=2).encode()
    for name,content in files.items():
        temp=folder/(name+'.tmp')
        temp.write_bytes(content)
        os.replace(temp,folder/name)
    return folder
