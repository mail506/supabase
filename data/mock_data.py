"""
Phase 1: モックデータ
Phase 2でSupabaseクライアントに差し替える
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


DEVICE_ID = "VVAULT-001"

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

    # 湿度：40〜55%、ゆるやかなドリフト + ノイズ
    base_hum = 47 + np.sin(np.linspace(0, 4 * np.pi, n)) * 5
    humidity = base_hum + np.random.normal(0, 0.4, n)

    # 温度：SHT31-Dで同時取得、20〜24℃
    temperature = 22 + np.sin(np.linspace(0, 2 * np.pi, n)) * 1.5 + np.random.normal(0, 0.1, n)

    # 露点：Magnus式で計算（temperature - (100 - humidity) / 5 の簡易版）
    dew_point = temperature - (100 - humidity) / 5

    # WiFi RSSI：-40〜-80 dBm
    rssi = np.random.randint(-75, -45, n)

    # 起動からの経過時間（秒）
    uptime_sec = [i * 900 for i in range(n)]

    return pd.DataFrame({
        "recorded_at": timestamps,
        "device_id": DEVICE_ID,
        "temperature": temperature.round(2),
        "humidity": humidity.round(2),
        "dew_point": dew_point.round(2),
        "rssi": rssi.tolist(),
        "uptime_sec": uptime_sec,
    })


def get_operation_logs() -> pd.DataFrame:
    """
    操作ログ（モック）
    event_type: lock / unlock / door_open / door_close / led_on / led_off / reboot / wifi_connect
    triggered_by: app / button / schedule / system
    """
    now = datetime.now()

    events = [
        (now - timedelta(hours=48),  "reboot",      "system", None),
        (now - timedelta(hours=47),  "wifi_connect","system", None),
        (now - timedelta(hours=46),  "led_on",      "schedule", None),
        (now - timedelta(hours=44),  "unlock",      "app",    None),
        (now - timedelta(hours=44, minutes=2), "door_open",  "app", None),
        (now - timedelta(hours=43, minutes=50),"door_close", "app", None),
        (now - timedelta(hours=43, minutes=49),"lock",       "app", None),
        (now - timedelta(hours=30),  "led_off",     "schedule", None),
        (now - timedelta(hours=24),  "led_on",      "schedule", None),
        (now - timedelta(hours=10),  "unlock",      "app",    None),
        (now - timedelta(hours=9, minutes=58), "door_open",  "app", None),
        (now - timedelta(hours=9, minutes=45), "door_close", "app", None),
        (now - timedelta(hours=9, minutes=44), "lock",       "app", None),
        (now - timedelta(hours=2),   "led_off",     "schedule", None),
    ]

    df = pd.DataFrame(events, columns=["occurred_at", "event_type", "triggered_by", "detail"])
    df["device_id"] = DEVICE_ID
    return df.sort_values("occurred_at").reset_index(drop=True)
