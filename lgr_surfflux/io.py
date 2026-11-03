import pandas as pd

def read_timeseries(path, time_col="time", value_col="value"):
    df = pd.read_csv(path, sep=',', engine='python', header=1)
    cols = df.columns.values
    df.columns = [item.strip() for item in cols]
    df[time_col] = pd.to_datetime(df[time_col], dayfirst=True)
    df[time_col] = df[time_col].dt.floor("s")
    df[value_col] = df[value_col].astype(float)
    return df[[time_col, value_col]].dropna()

def save_results(df, out_csv=None, out_excel=None):
    if out_csv:
        df.to_csv(out_csv, index=False)
    if out_excel:
        df.to_excel(out_excel, index=False)

