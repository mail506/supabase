# VISTAVAULT 保管証明ダッシュボード

PROTOSCAPE / 黒山裕志

## フェーズ構成

| フェーズ | 内容 | 状態 |
|---|---|---|
| Phase 1 | モックデータで表示確認 | ✅ 現在 |
| Phase 2 | Supabase 接続・ESP32からPOST | 🔜 |
| Phase 3 | ハッシュチェーン・保管証明書PDF出力 | 🔜 |

## ローカル起動

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Supabase テーブル設計（Phase 2）

### sensor_logs

```sql
CREATE TABLE sensor_logs (
  id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  device_id     TEXT NOT NULL,
  recorded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  temperature   FLOAT4,
  humidity      FLOAT4,
  dew_point     FLOAT4,
  rssi          INTEGER,
  uptime_sec    INTEGER,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);
```

### operation_logs

```sql
CREATE TABLE operation_logs (
  id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  device_id     TEXT NOT NULL,
  occurred_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  event_type    TEXT NOT NULL,
  triggered_by  TEXT,
  detail        JSONB,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);
```

### event_type 一覧

| 値 | 意味 |
|---|---|
| `lock` | 施錠 |
| `unlock` | 解錠 |
| `door_open` | 扉 開 |
| `door_close` | 扉 閉 |
| `led_on` | 照明 ON |
| `led_off` | 照明 OFF |
| `reboot` | 再起動 |
| `wifi_connect` | WiFi 接続 |

## ESP32収集項目メモ

| 項目 | センサー/ソース | 備考 |
|---|---|---|
| 温度 | SHT31-D | ±0.3°C |
| 湿度 | SHT31-D | ±2%RH |
| 露点 | 計算値 | Magnus式 |
| WiFi RSSI | ESP32-C6内蔵 | dBm |
| 起動経過時間 | ESP32-C6 | `esp_timer_get_time()` |
| 施錠/解錠 | ソレノイド制御GPIO | トリガー元も記録 |
| 扉開閉 | 要:マグネットスイッチ | 追加部品 |
| 照明ON/OFF | COB LED制御GPIO | 現状スケジュール制御 |
