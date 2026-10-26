#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_data_folder.py
Luồng: [1] sinh raw/  ->  [2] raw -> clean/  ->  [3] clean -> features/  ->  [4] viết DATA_DICTIONARY.md + DATA_REPORT.md
Chạy:  python build_data_folder.py            (root mặc định = thư mục cha của scripts/)
       python build_data_folder.py --skip-generate   (giữ nguyên raw/ hiện có, chạy lại bước 2-4)
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import generate_cafe_hr_data as g

DATE_COLS = {
    "holidays": ["date"], "weather_daily": ["date"],
    "employees": ["hire_date", "termination_date"],
    "leave_requests": ["start_date", "end_date", "submitted_date"],
    "attendance_events": ["ts"],
    "attendance_daily": ["work_date", "planned_start", "planned_end", "check_in_ts", "check_out_ts"],
    "branch_sales_hourly": ["date"],
}
CLEAN_TABLES = ["branches", "shifts", "holidays", "weather_daily", "employees", "leave_requests",
                "attendance_events", "attendance_daily", "payroll", "branch_sales_hourly", "labels_anomaly"]
FEATURE_TABLES = ["features_anomaly", "features_attrition", "features_staffing_hourly"]


def write_csv(df, path):
    df.to_csv(path, index=False, encoding="utf-8-sig")


# ---------------------------------------------------------------- [1] RAW
def stage_raw(root, seed):
    T = g.build_all(seed)
    raw = root / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for name, df in T["clean"].items():
        write_csv(df, raw / f"{name}.csv")
    (root / "_internal").mkdir(exist_ok=True)
    write_csv(T["internal"]["employee_latent_traits"], root / "_internal" / "employee_latent_traits.csv")
    print(f"[1] raw/: {len(T['clean'])} file")


# ---------------------------------------------------------------- [2] CLEAN
def clean_table(name, df, log):
    n0 = len(df)
    for c in df.select_dtypes(include=["object", "string"]).columns:
        df[c] = df[c].str.strip()
    if name != "attendance_events":          # lượt quét trùng là BẤT THƯỜNG có nhãn, không được xóa
        df = df.drop_duplicates()
    log.append((name, n0, len(df), n0 - len(df)))
    return df.reset_index(drop=True)


def stage_clean(root):
    log, C = [], {}
    (root / "clean").mkdir(exist_ok=True)
    for name in CLEAN_TABLES:
        df = pd.read_csv(root / "raw" / f"{name}.csv", parse_dates=DATE_COLS.get(name, []),
                         encoding="utf-8-sig")
        C[name] = clean_table(name, df, log)
        write_csv(C[name], root / "clean" / f"{name}.csv")
    print("[2] clean/ xong")
    return C, pd.DataFrame(log, columns=["bảng", "dòng raw", "dòng sau làm sạch", "dòng bị loại"])


# ---------------------------------------------------------------- [3] FEATURES
def stage_features(root, C):
    E = C["employees"].copy()
    E["is_real_face"] = E.is_real_face.astype(bool)
    ev = C["attendance_events"].merge(C["labels_anomaly"], on="event_id", how="left")
    ev["anomaly_type"] = ev.anomaly_type.fillna("")
    ev["is_manual"] = ev.is_manual.astype(bool)
    hol = set(C["holidays"].date)
    F = {
        "features_anomaly": g.build_features_anomaly(ev, C["attendance_daily"], E, hol),
        "features_attrition": g.build_features_attrition(C["attendance_daily"], E, C["payroll"]),
        "features_staffing_hourly": g.build_features_staffing(
            g.staffing_hourly(C["attendance_daily"], C["branch_sales_hourly"]), C["weather_daily"], hol),
    }
    (root / "features").mkdir(exist_ok=True)
    for n, df in F.items():
        write_csv(df, root / "features" / f"{n}.csv")
        try:
            df.to_parquet(root / "features" / f"{n}.parquet", index=False)
        except Exception as ex:
            print("  bỏ qua Parquet:", type(ex).__name__)
    print("[3] features/ xong")
    return F


# ---------------------------------------------------------------- [4] TÀI LIỆU
def md_table(df):
    d = df.astype(str)
    out = ["| " + " | ".join(d.columns) + " |", "|" + "|".join(["---"] * len(d.columns)) + "|"]
    for r in d.itertuples(index=False):
        out.append("| " + " | ".join(x.replace("|", "/") for x in r) + " |")
    return "\n".join(out)


def stage_docs(root, C, F, clean_log):
    T2 = {"clean": C, "features": F}
    dd = g.data_dictionary(T2)
    val = g.validate(T2)
    # ---- DATA_DICTIONARY.md
    L = ["# DATA_DICTIONARY", "", "Mô tả cột của các bảng trong `clean/` và `features/`.", ""]
    for (grp, tb), sub in dd.groupby(["group", "table"], sort=False):
        L += [f"## {grp}/{tb}", "", g.TABLE_DESC.get(tb, ""), "",
              md_table(sub[["column", "dtype", "description", "n_missing"]]), ""]
    (root / "DATA_DICTIONARY.md").write_text("\n".join(L), encoding="utf-8")
    # ---- DATA_REPORT.md
    R = ["# DATA_REPORT", "",
         f"- Chuỗi: {g.CFG['chain_name']}; giai đoạn {g.CFG['start']} → {g.CFG['end']}; seed {g.CFG['seed']}.",
         "- Đây là dữ liệu MÔ PHỎNG; tên người và các tham số lương/bảo hiểm/thuế là giả định.", "",
         "## 1. Số dòng, số cột", ""]
    R.append(md_table(pd.DataFrame([(grp, n, f"{len(df):,}", df.shape[1])
                                    for grp, tbs in T2.items() for n, df in tbs.items()],
                                   columns=["nhóm", "bảng", "số dòng", "số cột"])))
    R += ["", "## 2. Tỷ lệ thiếu", ""]
    miss = []
    for grp, tbs in T2.items():
        for n, df in tbs.items():
            m = df.isna().mean()
            miss += [(n, c, f"{m[c] * 100:.1f}%") for c in m[m > 0].index]
    R.append(md_table(pd.DataFrame(miss, columns=["bảng", "cột", "% thiếu"])) if miss else "Không có cột nào thiếu.")
    R += ["", "Phần lớn giá trị thiếu là có chủ đích (chưa nghỉ việc, chỉ FT có lương tháng / chỉ PT có lương giờ, "
              "lượt QR hoặc chấm tay không có điểm khuôn mặt, ngày nghỉ không có giờ vào/ra).", "",
          "## 3. Phân phối", "", "### 3.1 Biến số", ""]
    num = []
    for grp, tbs in T2.items():
        for n, df in tbs.items():
            cols = [c for c in df.select_dtypes("number").columns if not c.endswith("_id")]
            if cols:
                s = df[cols].describe().T[["mean", "std", "min", "50%", "max"]].round(2)
                s.insert(0, "cột", s.index)
                s.insert(0, "bảng", n)
                num.append(s)
    R.append(md_table(pd.concat(num).rename(columns={"50%": "median"})))
    R += ["", "### 3.2 Biến phân loại (tối đa 8 giá trị)", ""]
    cat = []
    for grp, tbs in T2.items():
        for n, df in tbs.items():
            for c in df.select_dtypes(include=["object", "string"]).columns:
                if 2 <= df[c].nunique() <= 8:
                    vc = df[c].value_counts(normalize=True)
                    cat.append((n, c, "; ".join(f"{k}: {v * 100:.1f}%" for k, v in vc.items())))
    R.append(md_table(pd.DataFrame(cat, columns=["bảng", "cột", "phân phối"])))
    R += ["", "## 4. Cách làm sạch (raw → clean)", "",
          "- Đọc CSV từ `raw/`, ép kiểu ngày/giờ, cắt khoảng trắng ở cột chữ.",
          "- Xóa dòng trùng hoàn toàn ở mọi bảng, TRỪ `attendance_events`: các lượt quét trùng (`burst_duplicate`) là bất thường "
          "có nhãn để model học, nên giữ lại và để model phát hiện.",
          "- Không điền giá trị thiếu và không loại ngoại lai: các bất thường được gắn nhãn thay vì bị xóa.", "",
          md_table(clean_log), "",
          "## 5. Chia tập (theo thời gian, không xáo trộn)", ""]
    sp = []
    fa, fe, fs = F["features_attrition"], F["features_anomaly"], F["features_staffing_hourly"]
    for n, df, lab in [("features_anomaly", fe, "is_anomaly"), ("features_attrition", fa, "left_next_60d")]:
        for s, sub in df.groupby("split"):
            sp.append((n, s, f"{len(sub):,}", int(sub[lab].sum()), f"{sub[lab].mean() * 100:.2f}%"))
    for s, sub in fs.groupby("split"):
        sp.append(("features_staffing_hourly", s, f"{len(sub):,}", "-", "-"))
    R.append(md_table(pd.DataFrame(sp, columns=["bảng", "split", "số dòng", "mẫu dương", "tỷ lệ dương"])))
    R += ["", "## 6. Kiểm tra toàn vẹn", "", f"Đạt {int(val.passed.sum())}/{len(val)} kiểm tra.", "",
          md_table(val.assign(passed=val.passed.map({True: "ĐẠT", False: "KHÔNG ĐẠT"})))]
    (root / "DATA_REPORT.md").write_text("\n".join(R), encoding="utf-8")
    print(f"[4] DATA_DICTIONARY.md, DATA_REPORT.md xong. Kiểm tra: {int(val.passed.sum())}/{len(val)} đạt")
    for r in val[~val.passed].itertuples():
        print("  KHÔNG ĐẠT:", r.check, "|", r.detail)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None, help="thư mục data/ (mặc định: cha của scripts/)")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--skip-generate", action="store_true", help="giữ raw/ hiện có")
    a = ap.parse_args()
    root = Path(a.root).resolve() if a.root else Path(__file__).resolve().parents[1]
    if not a.skip_generate:
        stage_raw(root, a.seed)
    C, log = stage_clean(root)
    F = stage_features(root, C)
    stage_docs(root, C, F, log)
    print("Xong:", root)


if __name__ == "__main__":
    main()