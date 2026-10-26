import pandas as pd
D = "data"
f_att = pd.read_parquet(f"{D}/features/features_attrition.parquet")
f_ano = pd.read_parquet(f"{D}/features/features_anomaly.parquet")
f_stf = pd.read_parquet(f"{D}/features/features_staffing_hourly.parquet")
print(f_att.shape, f_ano.shape, f_stf.shape)