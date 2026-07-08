"""
Phase 1: モックデータ
Phase 2でSupabaseクライアントに差し替える
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

DEVICE_ID    = "VVAULT-001"
DEFAULT_SETPOINT = 45.0

# 固定乖離バンド定義（%RH）: (ラベル, 下限, 上限)
DEVIATION_BANDS = [
    ("±2%以内",   0.0, 2.0),
    ("±2〜5%",   2.0, 5.0),
    ("±5〜10%",  5.0, 10.0),
    ("±10%超",  10.0, None),
]


def get_sensor_logs() -> pd.DataFrame:
    """
    Phase 2:
        from supabase import create_client
        client = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
        rows = client.table("sensor_logs").select("*").order("recorded_at").execute().data
        return pd.DataFrame(rows)
    """
    now = datetime.now()
    n   = 200  # 約50時間分（15分間隔）
    ts  = [now - timedelta(minutes=15 * i) for i in range(n)][::-1]

    base_hum    = DEFAULT_SETPOINT + np.sin(np.linspace(0, 4 * np.pi, n)) * 6
    humidity    = base_hum + np.random.normal(0, 0.5, n)
    temperature = 22 + np.sin(np.linspace(0, 2 * np.pi, n)) * 1.5 + np.random.normal(0, 0.1, n)
    dew_point   = temperature - (100 - humidity) / 5
    rssi        = np.random.randint(-75, -45, n)
    uptime_sec  = [i * 900 for i in range(n)]
    setpoint    = [DEFAULT_SETPOINT] * 100 + [50.0] * 100

    return pd.DataFrame({
        "recorded_at":       ts,
        "device_id":         DEVICE_ID,
        "temperature":       temperature.round(2),
        "humidity":          humidity.round(2),
        "dew_point":         dew_point.round(2),
        "humidity_setpoint": setpoint,
        "rssi":              rssi.tolist(),
        "uptime_sec":        uptime_sec,
    })


def get_operation_logs() -> pd.DataFrame:
    """
    event_type: lock / unlock / door_open / door_close /
                led_on / led_off / reboot / wifi_connect / setpoint_change
    """
    now = datetime.now()
    events = [
        (now - timedelta(hours=48),             "reboot",          "system",   None),
        (now - timedelta(hours=47),             "wifi_connect",    "system",   None),
        (now - timedelta(hours=47),             "setpoint_change", "app",      45.0),
        (now - timedelta(hours=46),             "led_on",          "schedule", None),
        (now - timedelta(hours=44),             "unlock",          "app",      None),
        (now - timedelta(hours=44, minutes=2),  "door_open",       "app",      None),
        (now - timedelta(hours=43, minutes=50), "door_close",      "app",      None),
        (now - timedelta(hours=43, minutes=49), "lock",            "app",      None),
        (now - timedelta(hours=30),             "led_off",         "schedule", None),
        (now - timedelta(hours=25),             "setpoint_change", "app",      50.0),
        (now - timedelta(hours=24),             "led_on",          "schedule", None),
        (now - timedelta(hours=10),             "unlock",          "app",      None),
        (now - timedelta(hours=9, minutes=58),  "door_open",       "app",      None),
        (now - timedelta(hours=9, minutes=45),  "door_close",      "app",      None),
        (now - timedelta(hours=9, minutes=44),  "lock",            "app",      None),
        (now - timedelta(hours=2),              "led_off",         "schedule", None),
    ]
    df = pd.DataFrame(events, columns=["occurred_at", "event_type", "triggered_by", "humidity_setpoint"])
    df["device_id"] = DEVICE_ID
    return df.sort_values("occurred_at").reset_index(drop=True)


def calc_band_stats(df: pd.DataFrame) -> list[dict]:
    """
    固定バンドごとの時間・割合を計算する（スライダー不要・改ざん不可）
    返り値: [{label, hours, pct, color}, ...]
    """
    df      = df.copy()
    df["deviation"] = (df["humidity"] - df["humidity_setpoint"]).abs()
    interval_h      = 15 / 60
    total_h         = len(df) * interval_h
    COLORS          = ["#2d9e72", "#7bc4a0", "#e8a44a", "#d95f49"]

    result = []
    for (label, lo, hi), color in zip(DEVIATION_BANDS, COLORS):
        if hi is None:
            mask = df["deviation"] >= lo
        else:
            mask = (df["deviation"] >= lo) & (df["deviation"] < hi)
        hours = mask.sum() * interval_h
        result.append({
            "label": label,
            "hours": round(hours, 1),
            "pct":   round(hours / total_h * 100, 1) if total_h > 0 else 0,
            "color": color,
        })
    return result


def calc_deviation_events(df: pd.DataFrame, lo: float, hi: float | None) -> pd.DataFrame:
    """指定バンドの連続逸脱イベント一覧"""
    df = df.copy()
    df["deviation"] = (df["humidity"] - df["humidity_setpoint"]).abs()
    if hi is None:
        mask = df["deviation"] >= lo
    else:
        mask = (df["deviation"] >= lo) & (df["deviation"] < hi)
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
