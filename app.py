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

from data.mock_data import get_sensor_logs, get_operation_logs, calc_stability

# ─────────────────────────────
# ページ設定
# ─────────────────────────────
st.set_page_config(
    page_title="VISTAVAULT 保管証明",
    page_icon="",
    layout="wide",
)

st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background: #fafafa; }
    .block-container { padding-top: 2rem; }
    .metric-label { font-size: 12px; color: #888; letter-spacing: 0.05em; text-transform: uppercase; }
    .metric-value { font-size: 28px; font-weight: 600; color: #1a1a1a; line-height: 1.2; }
    .metric-sub   { font-size: 12px; color: #aaa; margin-top: 2px; }
    .section-title { font-size: 13px; font-weight: 600; letter-spacing: 0.08em;
                     text-transform: uppercase; color: #555; margin: 1.5rem 0 0.8rem; }
    .event-row { font-size: 13px; padding: 6px 0; border-bottom: 1px solid #f0f0f0; }
    .badge { display: inline-block; padding: 1px 8px; border-radius: 3px;
             font-size: 11px; font-weight: 500; letter-spacing: 0.03em; }
    .stable-bar { background: #e8f5ef; border-left: 3px solid #2d9e72; 
                  padding: 10px 14px; border-radius: 0 4px 4px 0; margin: 4px 0; }
    .unstable-bar { background: #fdf0ee; border-left: 3px solid #d95f49;
                    padding: 10px 14px; border-radius: 0 4px 4px 0; margin: 4px 0; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────
# データ取得
# ─────────────────────────────
@st.cache_data(ttl=60)
def load_data():
    sensors = get_sensor_logs()
    sensors["recorded_at"] = pd.to_datetime(sensors["recorded_at"])
    ops = get_operation_logs()
    ops["occurred_at"] = pd.to_datetime(ops["occurred_at"])
    return sensors, ops

sensors, ops = load_data()
latest = sensors.iloc[-1]


# ─────────────────────────────
# ヘッダー
# ─────────────────────────────
col_h1, col_h2, col_h3 = st.columns([4, 3, 1])
with col_h1:
    st.markdown("## VISTAVAULT 保管証明")
    st.caption("PROTOSCAPE  /  " + latest["device_id"])
with col_h2:
    st.markdown(f"""
    <div style="padding-top:8px; font-size:13px; color:#888; line-height:2">
    最終同期：{latest['recorded_at'].strftime('%Y-%m-%d %H:%M')}&nbsp;&nbsp;
    WiFi：{latest['rssi']} dBm
    </div>
    """, unsafe_allow_html=True)
with col_h3:
    if st.button("更新"):
        st.cache_data.clear()
        st.rerun()

st.divider()


# ─────────────────────────────
# タブ
# ─────────────────────────────
tab_env, tab_ops, tab_cert = st.tabs(["環境ログ", "操作ログ", "保管証明書"])


# ══════════════════════
# TAB 1: 環境ログ
# ══════════════════════
with tab_env:

    # 期間フィルター + 許容乖離設定
    col_f1, col_f2, col_f3 = st.columns([2, 2, 4])
    with col_f1:
        period = st.selectbox("表示期間", ["直近24時間", "直近48時間", "全期間"], index=1)
    with col_f2:
        threshold = st.slider("許容乖離幅 (%RH)", min_value=1.0, max_value=10.0,
                               value=3.0, step=0.5,
                               help="この範囲内を「安定」と判定します")

    now = sensors["recorded_at"].max()
    if period == "直近24時間":
        df_plot = sensors[sensors["recorded_at"] >= now - pd.Timedelta(hours=24)].copy()
    elif period == "直近48時間":
        df_plot = sensors[sensors["recorded_at"] >= now - pd.Timedelta(hours=48)].copy()
    else:
        df_plot = sensors.copy()

    # 安定性計算
    stab = calc_stability(df_plot, threshold)

    # ── サマリーカード ──
    st.markdown('<div class="section-title">期間サマリー</div>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)

    def metric(col, label, value, sub=""):
        with col:
            st.markdown(f"""
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-sub">{sub}</div>
            """, unsafe_allow_html=True)

    metric(c1, "安定率", f"{stab['stable_pct']}%",
           f"許容 ±{threshold}%RH")
    metric(c2, "安定期間", f"{stab['stable_hours']}h",
           f"全{stab['total_hours']}h中")
    metric(c3, "逸脱期間", f"{stab['unstable_hours']}h",
           f"{len(stab['unstable_events'])}件の逸脱")
    metric(c4, "最大乖離", f"±{stab['max_deviation']}%RH", "設定値からの最大偏差")
    metric(c5, "平均乖離", f"±{stab['mean_deviation']}%RH", "設定値からの平均偏差")

    st.markdown('<div class="section-title">温湿度ログ</div>', unsafe_allow_html=True)

    # ── メインチャート：湿度 ──
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.45, 0.25, 0.30],
        subplot_titles=("湿度 (%RH)", "乖離量 (%RH)", "温度 / 露点 (°C)"),
    )

    setpoint_vals = df_plot["humidity_setpoint"]
    upper_band = setpoint_vals + threshold
    lower_band = setpoint_vals - threshold

    # 許容帯（シェード）
    fig.add_trace(go.Scatter(
        x=pd.concat([df_plot["recorded_at"], df_plot["recorded_at"][::-1]]),
        y=pd.concat([upper_band, lower_band[::-1]]),
        fill="toself",
        fillcolor="rgba(45,158,114,0.10)",
        line=dict(width=0),
        name=f"許容帯 ±{threshold}%RH",
        showlegend=True,
    ), row=1, col=1)

    # 設定値ライン
    fig.add_trace(go.Scatter(
        x=df_plot["recorded_at"], y=setpoint_vals,
        mode="lines", name="設定値",
        line=dict(color="#2d9e72", width=1.2, dash="dot"),
    ), row=1, col=1)

    # 実測湿度（安定 / 逸脱で色分け）
    df_plot["deviation"] = (df_plot["humidity"] - df_plot["humidity_setpoint"]).abs()
    df_plot["is_stable"] = df_plot["deviation"] <= threshold

    # 安定区間
    stable_mask = df_plot["is_stable"]
    fig.add_trace(go.Scatter(
        x=df_plot.loc[stable_mask, "recorded_at"],
        y=df_plot.loc[stable_mask, "humidity"],
        mode="markers", name="安定",
        marker=dict(color="#2d9e72", size=3),
        showlegend=True,
    ), row=1, col=1)

    # 逸脱区間
    unstable_mask = ~df_plot["is_stable"]
    if unstable_mask.any():
        fig.add_trace(go.Scatter(
            x=df_plot.loc[unstable_mask, "recorded_at"],
            y=df_plot.loc[unstable_mask, "humidity"],
            mode="markers", name="逸脱",
            marker=dict(color="#d95f49", size=4, symbol="circle"),
            showlegend=True,
        ), row=1, col=1)

    # ── 乖離チャート ──
    fig.add_trace(go.Bar(
        x=df_plot["recorded_at"],
        y=df_plot["deviation"],
        marker_color=[
            "#d95f49" if not s else "#c8e6d8"
            for s in df_plot["is_stable"]
        ],
        name="乖離量",
        showlegend=False,
    ), row=2, col=1)

    fig.add_hline(y=threshold, line_dash="dot",
                  line_color="#d95f49", line_width=1,
                  annotation_text=f"許容上限 {threshold}%RH",
                  annotation_font_size=10, row=2, col=1)

    # ── 温度 / 露点 ──
    fig.add_trace(go.Scatter(
        x=df_plot["recorded_at"], y=df_plot["temperature"],
        mode="lines", name="温度",
        line=dict(color="#b07a25", width=1.5),
    ), row=3, col=1)

    fig.add_trace(go.Scatter(
        x=df_plot["recorded_at"], y=df_plot["dew_point"],
        mode="lines", name="露点",
        line=dict(color="#aaa", width=1, dash="dash"),
    ), row=3, col=1)

    fig.update_layout(
        height=560,
        margin=dict(t=40, b=20, l=0, r=0),
        legend=dict(orientation="h", y=-0.10, font_size=12),
        hovermode="x unified",
        plot_bgcolor="#fafafa",
        paper_bgcolor="#fafafa",
    )
    fig.update_yaxes(gridcolor="#f0f0f0")
    fig.update_xaxes(gridcolor="#f0f0f0")

    st.plotly_chart(fig, use_container_width=True)

    # 逸脱イベント詳細
    if len(stab["unstable_events"]) > 0:
        st.markdown('<div class="section-title">逸脱イベント詳細</div>', unsafe_allow_html=True)
        ev = stab["unstable_events"].copy()
        ev["開始"]      = ev["start"].dt.strftime("%m/%d %H:%M")
        ev["終了"]      = ev["end"].dt.strftime("%m/%d %H:%M")
        ev["継続時間"]  = ev["duration_min"].astype(str) + " 分"
        ev["最大乖離"]  = ev["max_dev"].round(2).astype(str) + " %RH"
        st.dataframe(
            ev[["開始", "終了", "継続時間", "最大乖離"]],
            use_container_width=True, hide_index=True,
        )

    # 生データ
    with st.expander("生データを見る"):
        st.dataframe(
            df_plot[["recorded_at", "humidity", "humidity_setpoint",
                      "deviation", "is_stable", "temperature", "dew_point", "rssi"]]
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
    st.markdown('<div class="section-title">操作ログ</div>', unsafe_allow_html=True)

    EVENT_META = {
        "lock":           ("施錠",         "#e8f5ef", "#2d9e72"),
        "unlock":         ("解錠",         "#fdf0ee", "#d95f49"),
        "door_open":      ("扉 開",        "#eef4fb", "#4a80c4"),
        "door_close":     ("扉 閉",        "#eef4fb", "#4a80c4"),
        "led_on":         ("照明 ON",      "#fdf8ee", "#b07a25"),
        "led_off":        ("照明 OFF",     "#f5f5f5", "#888"),
        "reboot":         ("再起動",       "#f5f5f5", "#888"),
        "wifi_connect":   ("WiFi 接続",    "#f5f5f5", "#888"),
        "setpoint_change":("設定値変更",   "#f3eefb", "#7a4ac4"),
    }

    for _, row in ops.sort_values("occurred_at", ascending=False).iterrows():
        label, bg, color = EVENT_META.get(row["event_type"], (row["event_type"], "#f5f5f5", "#888"))
        col_t, col_e, col_b, col_sp = st.columns([3, 2, 2, 3])
        with col_t:
            st.markdown(f'<div class="event-row">{row["occurred_at"].strftime("%Y-%m-%d %H:%M:%S")}</div>',
                        unsafe_allow_html=True)
        with col_e:
            st.markdown(
                f'<div class="event-row"><span class="badge" style="background:{bg};color:{color}">'
                f'{label}</span></div>',
                unsafe_allow_html=True,
            )
        with col_b:
            st.markdown(f'<div class="event-row" style="color:#aaa;font-size:12px">{row["triggered_by"]}</div>',
                        unsafe_allow_html=True)
        with col_sp:
            if pd.notna(row.get("humidity_setpoint")):
                st.markdown(
                    f'<div class="event-row" style="font-size:12px">設定値 → {row["humidity_setpoint"]}%RH</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown('<div class="event-row"></div>', unsafe_allow_html=True)


# ══════════════════════
# TAB 3: 保管証明書
# ══════════════════════
with tab_cert:
    st.markdown('<div class="section-title">保管証明書プレビュー</div>', unsafe_allow_html=True)
    st.info("Phase 1：レイアウト確認用。PDF出力は Phase 3 で実装予定。")

    # 証明書全期間で再計算
    stab_all = calc_stability(sensors, threshold)
    period_start = sensors["recorded_at"].min().strftime("%Y年%m月%d日 %H:%M")
    period_end   = sensors["recorded_at"].max().strftime("%Y年%m月%d日 %H:%M")
    unlock_count = len(ops[ops["event_type"] == "unlock"])
    setpoint_changes = ops[ops["event_type"] == "setpoint_change"]

    st.markdown(f"""
---

### VISTAVAULT 保管証明書

**発行日時：** {datetime.now().strftime("%Y年%m月%d日 %H:%M")}
**デバイスID：** `{sensors['device_id'].iloc[0]}`
**記録期間：** {period_start} ～ {period_end}

---

#### 環境安定性サマリー（許容乖離幅 ±{threshold}%RH）

| 項目 | 値 |
|------|-----|
| 総記録時間 | {stab_all['total_hours']} 時間 |
| 安定期間 | {stab_all['stable_hours']} 時間 |
| 逸脱期間 | {stab_all['unstable_hours']} 時間 |
| **安定率** | **{stab_all['stable_pct']}%** |
| 最大乖離 | ±{stab_all['max_deviation']}%RH |
| 平均乖離 | ±{stab_all['mean_deviation']}%RH |

#### 湿度設定値の履歴
""", unsafe_allow_html=False)

    for _, row in setpoint_changes.iterrows():
        st.markdown(f"- {row['occurred_at'].strftime('%Y/%m/%d %H:%M')}　→　**{row['humidity_setpoint']}%RH**（{row['triggered_by']}）")

    st.markdown(f"""
#### 温湿度記録サマリー

| 項目 | 最小 | 平均 | 最大 |
|------|------|------|------|
| 湿度 (%RH) | {sensors['humidity'].min():.1f} | {sensors['humidity'].mean():.1f} | {sensors['humidity'].max():.1f} |
| 温度 (°C)  | {sensors['temperature'].min():.1f} | {sensors['temperature'].mean():.1f} | {sensors['temperature'].max():.1f} |
| 露点 (°C)  | {sensors['dew_point'].min():.1f} | {sensors['dew_point'].mean():.1f} | {sensors['dew_point'].max():.1f} |

#### 操作記録サマリー

- 開錠回数：**{unlock_count} 回**
- 扉開閉回数：**{len(ops[ops['event_type'] == 'door_open'])} 回**
- 設定値変更：**{len(setpoint_changes)} 回**

#### 備考
本証明書は VISTAVAULT（PROTOSCAPE）が記録した環境データに基づきます。
データの改ざん防止機構（ハッシュチェーン）は製品版にて実装予定。

---
""")

    col_pdf, col_share = st.columns(2)
    with col_pdf:
        st.button("PDF出力（未実装）", disabled=True)
    with col_share:
        st.button("共有リンク生成（未実装）", disabled=True)
