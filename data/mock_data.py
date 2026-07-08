"""
Phase 1: モックデータ
Phase 2でSupabaseクライアントに差し替える
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


DEVICE_ID = "VVAULT-001"
DEFAULT_SETPOINT = 45.0  # デフォルト湿度設定値（%RH）


def get_sensor_logs() -> pd.DataFrame:
    """
    SHT31-D + ESP32-C6 から取得可能なセンサーログ（モック）
    Phase 2: Supabase に差し替え
        from supabase import create_client
        client = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
        rows = client.table("sensor_logs").select("*").order("recorded_at").execute().data
        return pd.DataFrame(rows)
    """
    now = datetime.now()
    n = 200  # 約50時間分（15分間隔）

    timestamps = [now - timedelta(minutes=15 * i) for i in range(n)][::-1]

    # 湿度：ゆるやかなドリフト + ノイズ（設定値45%を基準に変動）
    base_hum = DEFAULT_SETPOINT + np.sin(np.linspace(0, 4 * np.pi, n)) * 6
    humidity = base_hum + np.random.normal(0, 0.5, n)

    # 温度：SHT31-Dで同時取得、20〜24℃
    temperature = 22 + np.sin(np.linspace(0, 2 * np.pi, n)) * 1.5 + np.random.normal(0, 0.1, n)

    # 露点：Magnus式で計算（temperature - (100 - humidity) / 5 の簡易版）
    dew_point = temperature - (100 - humidity) / 5

    # WiFi RSSI：-40〜-80 dBm
    rssi = np.random.randint(-75, -45, n)

    # 起動からの経過時間（秒）
    uptime_sec = [i * 900 for i in range(n)]

    # 湿度設定値：途中で45→50に変更されたシナリオ（100件目あたりで変更）
    setpoint = [DEFAULT_SETPOINT] * 100 + [50.0] * 100

    return pd.DataFrame({
        "recorded_at": timestamps,
        "device_id": DEVICE_ID,
        "temperature": temperature.round(2),
        "humidity": humidity.round(2),
        "dew_point": dew_point.round(2),
        "humidity_setpoint": setpoint,
        "rssi": rssi.tolist(),
        "uptime_sec": uptime_sec,
    })


def get_operation_logs() -> pd.DataFrame:
    """
    操作ログ（モック）
    event_type: lock / unlock / door_open / door_close / led_on / led_off
                reboot / wifi_connect / setpoint_change
    triggered_by: app / button / schedule / system
    humidity_setpoint: setpoint_change イベント時に新しい設定値を記録
    """
    now = datetime.now()

    events = [
        # (occurred_at, event_type, triggered_by, humidity_setpoint)
        (now - timedelta(hours=48),              "reboot",          "system",   None),
        (now - timedelta(hours=47),              "wifi_connect",    "system",   None),
        (now - timedelta(hours=47),              "setpoint_change", "app",      45.0),
        (now - timedelta(hours=46),              "led_on",          "schedule", None),
        (now - timedelta(hours=44),              "unlock",          "app",      None),
        (now - timedelta(hours=44, minutes=2),   "door_open",       "app",      None),
        (now - timedelta(hours=43, minutes=50),  "door_close",      "app",      None),
        (now - timedelta(hours=43, minutes=49),  "lock",            "app",      None),
        (now - timedelta(hours=30),              "led_off",         "schedule", None),
        (now - timedelta(hours=25),              "setpoint_change", "app",      50.0),
        (now - timedelta(hours=24),              "led_on",          "schedule", None),
        (now - timedelta(hours=10),              "unlock",          "app",      None),
        (now - timedelta(hours=9, minutes=58),   "door_open",       "app",      None),
        (now - timedelta(hours=9, minutes=45),   "door_close",      "app",      None),
        (now - timedelta(hours=9, minutes=44),   "lock",            "app",      None),
        (now - timedelta(hours=2),               "led_off",         "schedule", None),
    ]

    df = pd.DataFrame(events, columns=["occurred_at", "event_type", "triggered_by", "humidity_setpoint"])
    df["device_id"] = DEVICE_ID
    return df.sort_values("occurred_at").reset_index(drop=True)


def calc_stability(df: pd.DataFrame, threshold: float) -> dict:
    """
    センサーログから安定性指標を計算する
    threshold: 許容乖離幅（%RH）例）3.0
    """
    df = df.copy()
    df["deviation"] = (df["humidity"] - df["humidity_setpoint"]).abs()
    df["is_stable"] = df["deviation"] <= threshold

    interval_hours = 15 / 60  # 15分 = 0.25時間

    total_hours     = len(df) * interval_hours
    stable_hours    = df["is_stable"].sum() * interval_hours
    unstable_hours  = total_hours - stable_hours
    stable_pct      = stable_hours / total_hours * 100 if total_hours > 0 else 0

    # 連続した逸脱イベントを検出
    df["event_id"] = (df["is_stable"] != df["is_stable"].shift()).cumsum()
    unstable_events = (
        df[~df["is_stable"]]
        .groupby("event_id")
        .agg(
            start=("recorded_at", "first"),
            end=("recorded_at", "last"),
            max_dev=("deviation", "max"),
        )
        .reset_index(drop=True)
    )
    unstable_events["duration_min"] = (
        (unstable_events["end"] - unstable_events["start"]).dt.total_seconds() / 60 + 15
    ).round(0).astype(int)

    return {
        "total_hours":      round(total_hours, 1),
        "stable_hours":     round(stable_hours, 1),
        "unstable_hours":   round(unstable_hours, 1),
        "stable_pct":       round(stable_pct, 1),
        "max_deviation":    round(df["deviation"].max(), 2),
        "mean_deviation":   round(df["deviation"].mean(), 2),
        "unstable_events":  unstable_events,
    }
