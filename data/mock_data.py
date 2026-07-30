"""
Phase 2: Supabase接続
モックデータはコメントアウト済み（復元する場合は get_*_mock() を参照）
"""

import pandas as pd
import numpy as np
import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timedelta

DEVICE_ID        = "VVAULT-001"
DEFAULT_SETPOINT = 45.0

DEVIATION_BANDS = [
    ("±2%以内",  0.0,  2.0),
    ("±2〜5%",  2.0,  5.0),
    ("±5〜10%", 5.0, 10.0),
    ("±10%超", 10.0, None),
]


@st.cache_resource
def get_client() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


def get_sensor_logs() -> pd.DataFrame:
    client = get_client()
    rows = (
        client.table("sensor_logs")
        .select("*")
        .order("recorded_at")
        .execute()
        .data
    )
    if not rows:
        return pd.DataFrame(columns=[
            "recorded_at", "device_id", "temperature", "humidity",
            "dew_point", "humidity_setpoint", "rssi", "uptime_sec",
        ])
    df = pd.DataFrame(rows)
    df["recorded_at"] = pd.to_datetime(df["recorded_at"], format="ISO8601", utc=True)
    return df


def get_operation_logs() -> pd.DataFrame:
    client = get_client()
    rows = (
        client.table("operation_logs")
        .select("*")
        .order("occurred_at")
        .execute()
        .data
    )
    if not rows:
        return pd.DataFrame(columns=[
            "occurred_at", "device_id", "event_type",
            "triggered_by", "humidity_setpoint", "detail",
        ])
    df = pd.DataFrame(rows)
    df["occurred_at"] = pd.to_datetime(df["occurred_at"], format="ISO8601", utc=True)
    return df


def calc_band_stats(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    df["deviation"] = (df["humidity"] - df["humidity_setpoint"]).abs()
    interval_h = 15 / 60
    total_h    = len(df) * interval_h
    COLORS     = ["#2d9e72", "#7bc4a0", "#e8a44a", "#d95f49"]

    result = []
    for (label, lo, hi), color in zip(DEVIATION_BANDS, COLORS):
        mask  = df["deviation"] >= lo if hi is None else (df["deviation"] >= lo) & (df["deviation"] < hi)
        hours = mask.sum() * interval_h
        result.append({
            "label": label,
            "hours": round(hours, 1),
            "pct":   round(hours / total_h * 100, 1) if total_h > 0 else 0,
            "color": color,
        })
    return result


def calc_deviation_events(df: pd.DataFrame, lo: float, hi: float | None) -> pd.DataFrame:
    df = df.copy()
    df["deviation"] = (df["humidity"] - df["humidity_setpoint"]).abs()
    mask           = df["deviation"] >= lo if hi is None else (df["deviation"] >= lo) & (df["deviation"] < hi)
    df["in_band"]  = mask
    df["event_id"] = (df["in_band"] != df["in_band"].shift()).cumsum()
    events = (
        df[df["in_band"]]
        .groupby("event_id")
        .agg(start=("recorded_at", "first"), end=("recorded_at", "last"),
             max_dev=("deviation", "max"))
        .reset_index(drop=True)
    )
    events["duration_min"] = (
        (events["end"] - events["start"]).dt.total_seconds() / 60 + 15
    ).round(0).astype(int)
    return events
