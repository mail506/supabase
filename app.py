"""
VISTAVAULT 保管証明ダッシュボード
Phase 1: モックデータで表示確認
Phase 2: Supabase に接続（data/mock_data.py のコメントを参照）
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

from data.mock_data import get_sensor_logs, get_operation_logs

# ─────────────────────────────
# ページ設定
# ─────────────────────────────
st.set_page_config(
    page_title="VISTAVAULT 保管証明",
    page_icon="🔒",
    layout="wide",
)

st.markdown("""
<style>
    .metric-card {
        background: #f8f8f8;
        border-radius: 8px;
        padding: 1rem 1.2rem;
        border: 1px solid #e0e0e0;
    }
    .event-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────
# データ取得
# ─────────────────────────────
@st.cache_data(ttl=60)  # 60秒キャッシュ（Phase 2では短くする）
def load_data():
    sensors = get_sensor_logs()
    sensors["recorded_at"] = pd.to_datetime(sensors["recorded_at"])
    ops = get_operation_logs()
    ops["occurred_at"] = pd.to_datetime(ops["occurred_at"])
    return sensors, ops

sensors, ops = load_data()

# ─────────────────────────────
# ヘッダー
# ─────────────────────────────
col_title, col_device, col_refresh = st.columns([3, 2, 1])
with col_title:
    st.title("🔒 VISTAVAULT 保管証明")
    st.caption("Powered by PROTOSCAPE")
with col_device:
    latest = sensors.iloc[-1]
    st.markdown(f"""
    **デバイスID:** `{latest['device_id']}`  
    **最終同期:** {latest['recorded_at'].strftime('%Y-%m-%d %H:%M')}  
    **WiFi:** {latest['rssi']} dBm
    """)
with col_refresh:
    if st.button("🔄 更新"):
        st.cache_data.clear()
        st.rerun()

st.divider()

# ─────────────────────────────
# タブ
# ─────────────────────────────
tab_env, tab_ops, tab_cert = st.tabs(["📊 環境ログ", "🔑 操作ログ", "📄 保管証明書"])


# ══════════════════════
# TAB 1: 環境ログ
# ══════════════════════
with tab_env:

    # サマリーカード
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        avg_hum = sensors["humidity"].mean()
        max_hum = sensors["humidity"].max()
        st.metric("平均湿度", f"{avg_hum:.1f} %RH", delta=f"最大 {max_hum:.1f}%")
    with c2:
        avg_temp = sensors["temperature"].mean()
        max_temp = sensors["temperature"].max()
        st.metric("平均温度", f"{avg_temp:.1f} °C", delta=f"最大 {max_temp:.1f}°C")
    with c3:
        avg_dew = sensors["dew_point"].mean()
        st.metric("平均露点", f"{avg_dew:.1f} °C")
    with c4:
        hours = (sensors["recorded_at"].max() - sensors["recorded_at"].min()).total_seconds() / 3600
        st.metric("記録期間", f"{hours:.0f} 時間", delta=f"{len(sensors)} レコード")

    st.markdown("#### 温湿度ログ")

    # 期間フィルター
    col_f1, col_f2 = st.columns([2, 4])
    with col_f1:
        period = st.selectbox("表示期間", ["直近24時間", "直近48時間", "全期間"], index=0)

    now = sensors["recorded_at"].max()
    if period == "直近24時間":
        df_plot = sensors[sensors["recorded_at"] >= now - pd.Timedelta(hours=24)]
    elif period == "直近48時間":
        df_plot = sensors[sensors["recorded_at"] >= now - pd.Timedelta(hours=48)]
    else:
        df_plot = sensors

    # 温湿度グラフ（サブプロット）
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("湿度 (%RH)", "温度 (°C)"),
    )

    fig.add_trace(go.Scatter(
        x=df_plot["recorded_at"], y=df_plot["humidity"],
        mode="lines", name="湿度",
        line=dict(color="#1D9E75", width=1.5),
        fill="tozeroy", fillcolor="rgba(29,158,117,0.08)",
    ), row=1, col=1)

    # 湿度警戒ライン
    fig.add_hline(y=60, line_dash="dot", line_color="#E24B4A", opacity=0.5,
                  annotation_text="警戒 60%", row=1, col=1)
    fig.add_hline(y=40, line_dash="dot", line_color="#378ADD", opacity=0.5,
                  annotation_text="乾燥注意 40%", row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df_plot["recorded_at"], y=df_plot["temperature"],
        mode="lines", name="温度",
        line=dict(color="#BA7517", width=1.5),
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=df_plot["recorded_at"], y=df_plot["dew_point"],
        mode="lines", name="露点",
        line=dict(color="#888780", width=1, dash="dash"),
    ), row=2, col=1)

    fig.update_layout(
        height=420,
        margin=dict(t=40, b=20, l=0, r=0),
        legend=dict(orientation="h", y=-0.12),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # 生データ
    with st.expander("生データを見る"):
        st.dataframe(
            df_plot[["recorded_at", "humidity", "temperature", "dew_point", "rssi", "uptime_sec"]]
            .sort_values("recorded_at", ascending=False)
            .reset_index(drop=True),
            use_container_width=True,
        )
        csv = df_plot.to_csv(index=False).encode("utf-8")
        st.download_button("CSVダウンロード", csv, "sensor_logs.csv", "text/csv")


# ══════════════════════
# TAB 2: 操作ログ
# ══════════════════════
with tab_ops:
    st.markdown("#### 操作ログ")

    EVENT_LABEL = {
        "lock":         ("🔒", "施錠",         "#E1F5EE"),
        "unlock":       ("🔓", "解錠",         "#FAECE7"),
        "door_open":    ("📂", "扉 開",         "#E6F1FB"),
        "door_close":   ("📁", "扉 閉",         "#E6F1FB"),
        "led_on":       ("💡", "照明 ON",       "#FAEEDA"),
        "led_off":      ("🌙", "照明 OFF",      "#F1EFE8"),
        "reboot":       ("🔁", "再起動",        "#F1EFE8"),
        "wifi_connect": ("📶", "WiFi 接続",     "#EAF3DE"),
    }

    for _, row in ops.sort_values("occurred_at", ascending=False).iterrows():
        icon, label, bg = EVENT_LABEL.get(row["event_type"], ("•", row["event_type"], "#f0f0f0"))
        col_time, col_event, col_by = st.columns([3, 2, 2])
        with col_time:
            st.text(row["occurred_at"].strftime("%Y-%m-%d %H:%M:%S"))
        with col_event:
            st.markdown(
                f'<span style="background:{bg};padding:2px 10px;border-radius:4px;font-size:13px">'
                f'{icon} {label}</span>',
                unsafe_allow_html=True,
            )
        with col_by:
            st.caption(row["triggered_by"])


# ══════════════════════
# TAB 3: 保管証明書プレビュー
# ══════════════════════
with tab_cert:
    st.markdown("#### 保管証明書プレビュー")
    st.info("Phase 1: レイアウト確認用（PDF出力は Phase 2 で実装）")

    period_start = sensors["recorded_at"].min().strftime("%Y-%m-%d")
    period_end   = sensors["recorded_at"].max().strftime("%Y-%m-%d")
    unlock_count = len(ops[ops["event_type"] == "unlock"])

    st.markdown(f"""
    ---
    ### VISTAVAULT 保管証明書

    **発行日時：** {datetime.now().strftime("%Y年%m月%d日 %H:%M")}  
    **デバイスID：** `{sensors['device_id'].iloc[0]}`  
    **記録期間：** {period_start} ～ {period_end}

    #### 環境記録サマリー

    | 項目 | 最小 | 平均 | 最大 |
    |------|------|------|------|
    | 湿度 (%RH) | {sensors['humidity'].min():.1f} | {sensors['humidity'].mean():.1f} | {sensors['humidity'].max():.1f} |
    | 温度 (°C)  | {sensors['temperature'].min():.1f} | {sensors['temperature'].mean():.1f} | {sensors['temperature'].max():.1f} |
    | 露点 (°C)  | {sensors['dew_point'].min():.1f} | {sensors['dew_point'].mean():.1f} | {sensors['dew_point'].max():.1f} |

    #### 操作記録サマリー

    - 開錠回数：**{unlock_count} 回**
    - 扉開閉回数：**{len(ops[ops['event_type'] == 'door_open'])} 回**
    - 再起動：**{len(ops[ops['event_type'] == 'reboot'])} 回**

    #### 備考
    本証明書は VISTAVAULT（PROTOSCAPE）が記録した環境データに基づきます。  
    データの改ざん防止機構（ハッシュチェーン）は製品版にて実装予定。

    ---
    """)

    col_a, col_b = st.columns(2)
    with col_a:
        st.button("📄 PDF出力（未実装）", disabled=True)
    with col_b:
        st.button("🔗 共有リンク生成（未実装）", disabled=True)
