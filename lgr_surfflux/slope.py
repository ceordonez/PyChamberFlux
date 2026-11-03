import numpy as np
import pandas as pd
from scipy.stats import linregress

def estimate_slope(df, start, end, time_col="time", value_col="value"):
    subset = df[(df[time_col] >= start) & (df[time_col] <= end)]
    if len(subset) < 3:
        raise ValueError("Not enough data points in selected region")
    x = (subset[time_col] - subset[time_col].iloc[0]).dt.total_seconds()
    y = subset[value_col]
    res = linregress(x, y)
    return {
        "start": start,
        "end": end,
        "slope": res.slope,
        "intercept": res.intercept,
        "r_value": res.rvalue,
        "stderr": res.stderr
    }
