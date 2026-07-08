"""
VISTAVAULT 保管証明ダッシュボード
Phase 1: モックデータで表示確認
Phase 2: Supabase 接続（data/mock_data.py のコメントを参照）
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

from data.mock_data import (
    get_sensor_logs, get_operation_logs,
    calc_band_stats, calc_deviation_events, DEVIATION_BANDS,
)

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
    .vv-label  { font-size: 11px; color: #999; letter-spacing: 0.06em;
                 text-transform: uppercase; margin-bottom: 2px; }
    .vv-value  { font-size: 26px; font-weight: 600; color: #1a1a1a; line-height: 1.2; }
    .vv-sub    { font-size: 12px; color: #bbb; margin-top: 2px; }
    .sec-title { font-size: 11px; font-weight: 700; letter-spacing: 0.1em;
                 text-transform: uppercase; color: #888;
                 margin: 1.8rem 0 0.8rem; border-bottom: 1px solid #eee; padding-bottom: 6px; }
    .band-row  { display: flex; align-items: center; gap: 12px;
                 padding: 8px 0; border-bottom: 1px solid #f0f0f0; font-size: 13px; }
    .band-bar  { height: 8px; border-radius: 4px; min-width: 4px; }
    .ev-row    { font-size: 13px; padding: 5px 0; border-bottom: 1px solid #f5f5f5; color: #444; }
    .badge     { display: inline-block; padding: 1px 8px; border-radius: 3px;
                 font-size: 11px; font-weight: 500; letter-spacing: 0.02em; }
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
    st.caption(f"PROTOSCAPE  /  {latest['device_id']}")
with col_h2:
    st.markdown(
        f'<div style="padding-top:10px;font-size:12px;color:#aaa;line-height:2">'
        f'最終同期：{latest["recorded_at"].strftime("%Y-%m-%d %H:%M")}&emsp;'
        f'WiFi：{latest["rssi"]} dBm</div>',
        unsafe_allow_html=True,
    )
with col_h3:
    if st.button("更新"):
        st.cache_data.clear()
        st.rerun()

st.divider()

# ─────────────────────────────
# タブ
# ─────────────────────────────
tab_env, tab_ops, tab_cert = st.tabs(["環境ログ", "操作ログ", "保管証明書"])


# ══════════════════════════════
# TAB 1: 環境ログ
# ══════════════════════════════
with tab_env:

    # 期間フィルター
    col_f1, _ = st.columns([2, 6])
    with col_f1:
        period = st.selectbox("表示期間", ["直近24時間", "直近48時間", "全期間"], index=1)

    now = sensors["recorded_at"].max()
    if period == "直近24時間":
        df = sensors[sensors["recorded_at"] >= now - pd.Timedelta(hours=24)].copy()
    elif period == "直近48時間":
        df = sensors[sensors["recorded_at"] >= now - pd.Timedelta(hours=48)].copy()
    else:
        df = sensors.copy()

    df["deviation"] = (df["humidity"] - df["humidity_setpoint"]).abs()
    bands = calc_band_stats(df)
    total_h = len(df) * 15 / 60

    # ── 乖離バンドサマリー ──
    st.markdown('<div class="sec-title">設定値からの乖離分布</div>', unsafe_allow_html=True)

    band_cols = st.columns(len(bands))
    for col, b in zip(band_cols, bands):
        with col:
            bar_w = max(4, int(b["pct"] * 1.4))
            st.markdown(f"""
            <div class="vv-label">{b['label']}</div>
            <div class="vv-value" style="color:{b['color']}">{b['hours']}h</div>
            <div class="vv-sub">{b['pct']}%　／　全{total_h:.0f}h中</div>
            <div style="margin-top:8px">
              <div class="band-bar" style="width:{bar_w}%;background:{b['color']};opacity:0.85"></div>
            </div>
            """, unsafe_allow_html=True)

    # ── 湿度グラフ ──
    st.markdown('<div class="sec-title">温湿度ログ</div>', unsafe_allow_html=True)

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.45, 0.25, 0.30],
        subplot_titles=("湿度 (%RH)", "乖離量 (%RH)", "温度 / 露点 (°C)"),
    )

    sp = df["humidity_setpoint"]

    # 許容帯（±2%）
    fig.add_trace(go.Scatter(
        x=pd.concat([df["recorded_at"], df["recorded_at"][::-1]]),
        y=pd.concat([sp + 2, (sp - 2)[::-1]]),
        fill="toself", fillcolor="rgba(45,158,114,0.10)",
        line=dict(width=0), name="±2%帯", showlegend=True,
    ), row=1, col=1)

    # 設定値ライン
    fig.add_trace(go.Scatter(
        x=df["recorded_at"], y=sp,
        mode="lines", name="設定値",
        line=dict(color="#2d9e72", width=1.2, dash="dot"),
    ), row=1, col=1)

    # バンド別に色分けプロット
    band_colors = ["#2d9e72", "#7bc4a0", "#e8a44a", "#d95f49"]
    for (label, lo, hi), color in zip(DEVIATION_BANDS, band_colors):
        if hi is None:
            mask = df["deviation"] >= lo
        else:
            mask = (df["deviation"] >= lo) & (df["deviation"] < hi)
        if mask.any():
            fig.add_trace(go.Scatter(
                x=df.loc[mask, "recorded_at"],
                y=df.loc[mask, "humidity"],
                mode="markers", name=label,
                marker=dict(color=color, size=3),
            ), row=1, col=1)

    # 乖離量バー
    fig.add_trace(go.Bar(
        x=df["recorded_at"], y=df["deviation"],
        marker_color=[
            "#2d9e72" if d < 2 else "#7bc4a0" if d < 5 else "#e8a44a" if d < 10 else "#d95f49"
            for d in df["deviation"]
        ],
        name="乖離量", showlegend=False,
    ), row=2, col=1)
    for (label, lo, hi), color in zip(DEVIATION_BANDS[1:], band_colors[1:]):
        if lo > 0:
            fig.add_hline(y=lo, line_dash="dot", line_color=color,
                          line_width=1, annotation_text=f"{lo}%",
                          annotation_font_size=9, row=2, col=1)

    # 温度 / 露点
    fig.add_trace(go.Scatter(
        x=df["recorded_at"], y=df["temperature"],
        mode="lines", name="温度",
        line=dict(color="#b07a25", width=1.5),
    ), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=df["recorded_at"], y=df["dew_point"],
        mode="lines", name="露点",
        line=dict(color="#bbb", width=1, dash="dash"),
    ), row=3, col=1)

    fig.update_layout(
        height=560, margin=dict(t=40, b=20, l=0, r=0),
        legend=dict(orientation="h", y=-0.10, font_size=12),
        hovermode="x unified",
        plot_bgcolor="#fafafa", paper_bgcolor="#fafafa",
    )
    fig.update_yaxes(gridcolor="#f0f0f0")
    fig.update_xaxes(gridcolor="#f0f0f0")
    st.plotly_chart(fig, use_container_width=True)

    # ── 逸脱イベント詳細 ──
    st.markdown('<div class="sec-title">逸脱イベント詳細（±2%超）</div>', unsafe_allow_html=True)
    for (label, lo, hi), color in zip(DEVIATION_BANDS[1:], band_colors[1:]):
        events = calc_deviation_events(df, lo, hi)
        if len(events) == 0:
            continue
        with st.expander(f"{label}　{len(events)}件"):
            ev = events.copy()
            ev["開始"]     = ev["start"].dt.strftime("%m/%d %H:%M")
            ev["終了"]     = ev["end"].dt.strftime("%m/%d %H:%M")
            ev["継続"]     = ev["duration_min"].astype(str) + " 分"
            ev["最大乖離"] = ev["max_dev"].round(2).astype(str) + " %RH"
            st.dataframe(ev[["開始", "終了", "継続", "最大乖離"]],
                         use_container_width=True, hide_index=True)

    with st.expander("生データ"):
        st.dataframe(
            df[["recorded_at", "humidity", "humidity_setpoint", "deviation",
                "temperature", "dew_point", "rssi"]]
            .sort_values("recorded_at", ascending=False)
            .reset_index(drop=True),
            use_container_width=True,
        )
        st.download_button("CSVダウンロード",
                           df.to_csv(index=False).encode("utf-8"),
                           "sensor_logs.csv", "text/csv")


# ══════════════════════════════
# TAB 2: 操作ログ
# ══════════════════════════════
with tab_ops:
    st.markdown('<div class="sec-title">操作ログ</div>', unsafe_allow_html=True)

    EVENT_META = {
        "lock":           ("施錠",       "#e8f5ef", "#2d9e72"),
        "unlock":         ("解錠",       "#fdf0ee", "#d95f49"),
        "door_open":      ("扉 開",      "#eef4fb", "#4a80c4"),
        "door_close":     ("扉 閉",      "#eef4fb", "#4a80c4"),
        "led_on":         ("照明 ON",    "#fdf8ee", "#b07a25"),
        "led_off":        ("照明 OFF",   "#f5f5f5", "#999"),
        "reboot":         ("再起動",     "#f5f5f5", "#999"),
        "wifi_connect":   ("WiFi 接続",  "#f5f5f5", "#999"),
        "setpoint_change":("設定値変更", "#f3eefb", "#7a4ac4"),
    }

    col_t, col_e, col_b, col_sp = st.columns([3, 2, 2, 3])
    for c, h in zip([col_t, col_e, col_b, col_sp],
                    ["日時", "イベント", "操作元", "設定値"]):
        with c:
            st.markdown(f'<div style="font-size:11px;color:#bbb;font-weight:600;'
                        f'letter-spacing:.06em;text-transform:uppercase;'
                        f'padding-bottom:6px;border-bottom:1px solid #eee">{h}</div>',
                        unsafe_allow_html=True)

    for _, row in ops.sort_values("occurred_at", ascending=False).iterrows():
        label, bg, color = EVENT_META.get(row["event_type"], (row["event_type"], "#f5f5f5", "#999"))
        col_t, col_e, col_b, col_sp = st.columns([3, 2, 2, 3])
        with col_t:
            st.markdown(f'<div class="ev-row">{row["occurred_at"].strftime("%Y-%m-%d %H:%M:%S")}</div>',
                        unsafe_allow_html=True)
        with col_e:
            st.markdown(
                f'<div class="ev-row"><span class="badge" '
                f'style="background:{bg};color:{color}">{label}</span></div>',
                unsafe_allow_html=True,
            )
        with col_b:
            st.markdown(f'<div class="ev-row" style="color:#bbb;font-size:12px">'
                        f'{row["triggered_by"]}</div>', unsafe_allow_html=True)
        with col_sp:
            sp_val = row.get("humidity_setpoint")
            text = f'{sp_val}%RH' if pd.notna(sp_val) else ""
            st.markdown(f'<div class="ev-row" style="font-size:12px;color:#666">'
                        f'{text}</div>', unsafe_allow_html=True)


# ══════════════════════════════
# TAB 3: 保管証明書
# ══════════════════════════════
with tab_cert:
    st.markdown('<div class="sec-title">保管証明書プレビュー</div>', unsafe_allow_html=True)
    st.info("Phase 1：レイアウト確認用。PDF出力は Phase 3 で実装予定。")

    bands_all = calc_band_stats(sensors)
    total_h_all = len(sensors) * 15 / 60
    period_start = sensors["recorded_at"].min().strftime("%Y年%m月%d日 %H:%M")
    period_end   = sensors["recorded_at"].max().strftime("%Y年%m月%d日 %H:%M")
    setpoint_changes = ops[ops["event_type"] == "setpoint_change"]

    st.markdown(f"""
---

### VISTAVAULT 保管証明書

**発行日時：** {datetime.now().strftime("%Y年%m月%d日 %H:%M")}  
**デバイスID：** `{sensors['device_id'].iloc[0]}`  
**記録期間：** {period_start} ～ {period_end}  
**総記録時間：** {total_h_all:.0f} 時間  

---

#### 湿度設定値の履歴
""")

    for _, row in setpoint_changes.sort_values("occurred_at").iterrows():
        st.markdown(
            f"- {row['occurred_at'].strftime('%Y/%m/%d %H:%M')}　"
            f"設定値 → **{row['humidity_setpoint']}%RH**（{row['triggered_by']}）"
        )

    st.markdown("#### 設定値からの乖離分布")

    st.markdown("""
| 乖離幅 | 時間 | 割合 |
|--------|------|------|""")
    for b in bands_all:
        st.markdown(f"| {b['label']} | {b['hours']} 時間 | {b['pct']}% |")

    st.markdown(f"""
#### 温湿度記録

| 項目 | 最小 | 平均 | 最大 |
|------|------|------|------|
| 湿度 (%RH) | {sensors['humidity'].min():.1f} | {sensors['humidity'].mean():.1f} | {sensors['humidity'].max():.1f} |
| 温度 (°C)  | {sensors['temperature'].min():.1f} | {sensors['temperature'].mean():.1f} | {sensors['temperature'].max():.1f} |
| 露点 (°C)  | {sensors['dew_point'].min():.1f} | {sensors['dew_point'].mean():.1f} | {sensors['dew_point'].max():.1f} |

#### 操作記録

- 開錠回数：**{len(ops[ops['event_type'] == 'unlock'])} 回**
- 扉開閉回数：**{len(ops[ops['event_type'] == 'door_open'])} 回**
- 設定値変更：**{len(setpoint_changes)} 回**

---

本証明書は VISTAVAULT（PROTOSCAPE）が自動記録した環境データに基づきます。  
改ざん防止機構（ハッシュチェーン）は製品版にて実装予定。
""")

    col_a, col_b = st.columns(2)
    with col_a:
        st.button("PDF出力（未実装）", disabled=True)
    with col_b:
        st.button("共有リンク生成（未実装）", disabled=True)
