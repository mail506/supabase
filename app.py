"""
VISTAVAULT Monitoring Dashboard — 1c Aurum
"""
import time
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import pytz
import streamlit as st
from supabase import create_client

st.set_page_config(
    page_title="VISTAVAULT MONITORING",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Tokens ─────────────────────────────────────────────────────────────
BG_MAIN  = "#0e0e12"; BG_HERO = "#0c0c10"; BG_CARD = "#0a0a0e"
BORDER   = "#1a1a22"; GOLD    = "#c9a252"; COL_LIVE = "#3d9e6a"
COL_TEMP = "#e8945a"; COL_HUM = "#4a8dc8"; COL_VOC  = "#9b6fd6"
COL_DH   = "#3dcf8a"; COL_HM  = "#f0c84a"
TXT_PRI  = "#ede8df"; TXT_SEC = "#6a6560"; TXT_DIM  = "#46443f"
TXT_VDIM = "#36342f"

PRESET_TARGETS = {"DRY": 30, "STD": 50, "MOIST": 70}
RANGE_HOURS    = {"1H": 1, "6H": 6, "24H": 24, "7D": 168}
EVENT_COLORS   = {
    "preset_change":   GOLD,    "shutter_open":  COL_LIVE,
    "shutter_close":   COL_HUM, "mode_change":   COL_VOC,
    "solenoid_unlock": COL_TEMP,
}
JST          = pytz.timezone("Asia/Tokyo")
REFRESH_SEC  = 30
LOGO_SVG     = (
    '<svg width="20" height="20" viewBox="0 0 20 20" fill="none">'
    '<path d="M10 1.5L18.5 6.25V13.75L10 18.5L1.5 13.75V6.25Z" stroke="#c9a252" stroke-width="1"/>'
    '<path d="M10 4.5L15 7.5V12.5L10 15.5L5 12.5V7.5Z" stroke="#c9a252" stroke-width=".5" opacity=".4"/>'
    '<circle cx="10" cy="10" r="1.6" fill="#c9a252" opacity=".7"/></svg>'
)

# ── Supabase ───────────────────────────────────────────────────────────
@st.cache_resource
def get_sb():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def fetch_latest(sb):
    r = sb.table("sensor_logs").select(
        "temperature,humidity,voc_index,rosahl_dehumid_current_ma,rosahl_humid_current_ma"
    ).order("recorded_at", desc=True).limit(1).execute()
    return r.data[0] if r.data else {}

def fetch_sensor_logs(sb, hours):
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    r = sb.table("sensor_logs").select(
        "recorded_at,temperature,humidity,voc_index,"
        "rosahl_dehumid_current_ma,rosahl_humid_current_ma"
    ).gte("recorded_at", since).order("recorded_at").execute()
    if not r.data:
        return pd.DataFrame()
    df = pd.DataFrame(r.data)
    df["recorded_at"] = pd.to_datetime(df["recorded_at"], format="ISO8601", utc=True)
    return df

def fetch_op_logs(sb, limit=100):
    r = sb.table("operation_logs").select(
        "occurred_at,event_type,detail"
    ).order("occurred_at", desc=True).limit(limit).execute()
    if not r.data:
        return pd.DataFrame()
    df = pd.DataFrame(r.data)
    df["occurred_at"] = pd.to_datetime(df["occurred_at"], format="ISO8601", utc=True)
    return df

def resolve_preset(op_df):
    if not op_df.empty:
        pc = op_df[op_df["event_type"] == "preset_change"]
        if not pc.empty:
            det = str(pc.iloc[0].get("detail", "")).upper()
            for p, t in PRESET_TARGETS.items():
                if p in det:
                    return p, t
    return "STD", 50

def resolve_shutters(op_df):
    dehum = humid = "—"
    fd = fh = False
    for _, row in op_df.iterrows():
        if fd and fh:
            break
        ev  = row.get("event_type", "")
        det = str(row.get("detail", "")).lower()
        st_ = "OPEN" if ev == "shutter_open" else "CLOSED"
        if not fd and "dehum" in det:
            dehum = st_; fd = True
        if not fh and "humid" in det and "dehum" not in det:
            humid = st_; fh = True
    return dehum, humid

def voc_status(v):
    if v is None: return "—",    TXT_DIM
    if v < 100:   return "GOOD", COL_LIVE
    if v < 200:   return "FAIR", GOLD
    if v < 300:   return "POOR", COL_TEMP
    return               "BAD",  "#cf4a4a"

# ── Plotly ─────────────────────────────────────────────────────────────
BASE_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=BG_CARD,
    margin=dict(l=4, r=4, t=2, b=24),
    font=dict(family="monospace", size=9, color=TXT_DIM),
    xaxis=dict(showgrid=False, zeroline=False, tickfont=dict(size=8, color=TXT_DIM),
               linecolor=BORDER, showline=False),
    yaxis=dict(showgrid=True, gridcolor="#16161e", zeroline=False,
               tickfont=dict(size=8, color=TXT_DIM), linecolor=BORDER, showline=False),
    hovermode="x unified",
    hoverlabel=dict(bgcolor=BG_CARD, bordercolor=BORDER, font_size=9),
    showlegend=False,
)

def _empty_annotation(fig):
    fig.add_annotation(
        text="この期間にデータがありません",
        xref="paper", yref="paper", x=0.5, y=0.5,
        showarrow=False, font=dict(size=10, color="#56534f"),
    )

def make_chart(df, col, color, unit, h=138, target=None):
    fig = go.Figure()
    has_data = (not df.empty) and (col in df.columns) and bool(df[col].notna().any())
    if has_data:
        fig.add_trace(go.Scatter(
            x=df["recorded_at"], y=df[col].where(df[col].notna()),
            mode="lines", line=dict(color=color, width=1.5),
            fill="tozeroy", fillcolor=color + "18",
            hovertemplate=f"%{{y:.1f}}{unit}<extra></extra>",
        ))
    else:
        _empty_annotation(fig)
    if target is not None:
        fig.add_hline(y=target, line_dash="dot", line_color=GOLD, line_width=1,
                      annotation_text=f"{target}%", annotation_font_color=GOLD,
                      annotation_font_size=8, annotation_position="top right")
    fig.update_layout(**{**BASE_LAYOUT, "height": h})
    return fig

def make_dual(df, h=138):
    fig = go.Figure()
    any_data = False
    for col, c, nm in [
        ("rosahl_dehumid_current_ma", COL_DH, "DEHUM"),
        ("rosahl_humid_current_ma",   COL_HM, "HUMID"),
    ]:
        if not df.empty and col in df.columns and df[col].notna().any():
            any_data = True
            fig.add_trace(go.Scatter(
                x=df["recorded_at"], y=df[col].where(df[col].notna()),
                mode="lines", line=dict(color=c, width=1.5), name=nm,
                hovertemplate=f"%{{y:.0f}} mA<extra>{nm}</extra>",
            ))
    if not any_data:
        _empty_annotation(fig)
    fig.update_layout(**{**BASE_LAYOUT, "height": h})
    return fig

# ── CSS (st.html で注入) ────────────────────────────────────────────────
CSS = f"""
<style>
html,body,[data-testid="stAppViewContainer"],[data-testid="stApp"]{{
  background:{BG_MAIN}!important;color:{TXT_PRI};
}}
[data-testid="stHeader"],[data-testid="stToolbar"]{{display:none;}}
.main .block-container{{padding:0!important;max-width:100%!important;}}
section[data-testid="stSidebar"]{{display:none;}}
.modebar{{display:none!important;}}
div[data-testid="stPlotlyChart"]{{
  background:{BG_CARD}!important;border:1px solid {BORDER}!important;
  border-radius:4px!important;padding:8px 12px 4px!important;
}}
.element-container:has(.stPlotlyChart){{margin-bottom:6px!important;}}
div[data-testid="stRadio"]>label{{display:none;}}
div[data-testid="stRadio"]>div{{display:flex!important;flex-direction:row!important;gap:2px;background:transparent;}}
div[data-testid="stRadio"]>div>label{{
  display:flex;align-items:center;padding:3px 10px;
  font-size:11px;font-family:monospace;letter-spacing:.1em;
  color:{TXT_DIM};border:1px solid #2a2a34;border-radius:2px;cursor:pointer;background:transparent;
}}
div[data-testid="stRadio"]>div>label:has(input:checked){{
  font-weight:700;color:{GOLD};background:rgba(201,162,82,.12);border:1px solid rgba(201,162,82,.2);
}}
div[data-testid="stRadio"]>div>label>span:first-child{{display:none;}}
[data-testid="column"]{{padding:0 4px!important;}}
@keyframes livepulse{{0%,100%{{opacity:1}}50%{{opacity:.2}}}}
.live-dot{{display:inline-block;width:5px;height:5px;border-radius:50%;
  background:{COL_LIVE};animation:livepulse 2s ease-in-out infinite;
  vertical-align:middle;margin-right:4px;}}
</style>
"""

def h(html: str):
    st.markdown(html, unsafe_allow_html=True)

# ── Render blocks ──────────────────────────────────────────────────────
def render_navbar(ts: str, ri: int, data_age: str = ""):
    if data_age:
        live_html = (f'<span style="font-family:monospace;font-size:9px;letter-spacing:.1em;color:#c9a252;">'
                     f'LAST DATA {data_age}</span>')
    else:
        live_html = ('<div><span class="live-dot"></span>'
                     '<span style="font-weight:600;font-size:9px;letter-spacing:.12em;'
                     'color:#3d9e6a;font-family:monospace;">LIVE</span></div>')
    h(f"""
<div style="display:flex;align-items:center;padding:0 28px;height:50px;
  background:linear-gradient(180deg,#0f0f14 0%,#0a0a0e 100%);
  border-bottom:1px solid {BORDER};position:relative;">
  <div style="position:absolute;top:0;left:0;right:0;height:1px;
    background:linear-gradient(90deg,transparent,rgba(201,162,82,.5),transparent);"></div>
  <div style="display:flex;align-items:center;gap:12px;">
    {LOGO_SVG}
    <span style="font-weight:600;font-size:14px;letter-spacing:.18em;color:{TXT_PRI};">VISTAVAULT</span>
  </div>
  <div style="margin-left:auto;display:flex;align-items:center;gap:20px;">
    <span style="font-size:9px;letter-spacing:.12em;color:#56534f;">MONITORING SYSTEM</span>
    <div style="width:1px;height:14px;background:#2a2a34;"></div>
    {live_html}
    <span style="font-family:monospace;font-size:11px;color:#7a7570;">{ts} JST</span>
    <span style="font-family:monospace;font-size:8px;color:{TXT_VDIM};">↻ {ri}s</span>
  </div>
</div>""")

def render_hero(latest, target):
    def v(k, fmt=".1f"):
        val = latest.get(k)
        return f"{val:{fmt}}" if val is not None else "—"

    hum = latest.get("humidity")
    dh  = latest.get("rosahl_dehumid_current_ma")
    hm  = latest.get("rosahl_humid_current_ma")
    voc = latest.get("voc_index")

    hdiff = (f"{'▲' if hum > target else '▼'}{abs(hum-target):.1f} vs {target}%"
             if hum else "—")
    hdc   = GOLD if hum and abs(hum-target) > 2 else COL_LIVE
    vlbl, vc = voc_status(voc)
    dha = dh and dh > 10
    hma = hm and hm > 10

    def cell(vs, unit, lbl, color, extra="", bg="transparent", br=True):
        b = f"border-right:1px solid {BORDER};" if br else ""
        return (f'<div style="flex:1;padding:20px 24px 16px;text-align:center;background:{bg};{b}">'
                f'<div style="font-size:52px;font-weight:300;line-height:1;color:{color};">{vs}</div>'
                f'<div style="display:flex;align-items:center;justify-content:center;gap:6px;margin-top:5px;">'
                f'<span style="font-size:14px;font-weight:300;color:{TXT_DIM};">{unit}</span>'
                f'<span style="width:1px;height:9px;background:#2a2a34;"></span>'
                f'<span style="font-family:monospace;font-size:7px;letter-spacing:.18em;color:{TXT_DIM};">{lbl}</span>'
                f'</div>{extra}</div>')

    def sub(txt, c):
        return f'<div style="font-family:monospace;font-size:8px;color:{c};margin-top:5px;letter-spacing:.08em;">{txt}</div>'
    def dot_sub(lbl, c):
        return (f'<div style="display:flex;align-items:center;justify-content:center;gap:4px;margin-top:5px;">'
                f'<span style="width:4px;height:4px;border-radius:50%;background:{c};"></span>'
                f'<span style="font-family:monospace;font-weight:600;font-size:8px;color:{c};letter-spacing:.1em;">{lbl}</span></div>')

    h(f"""
<div style="display:flex;background:{BG_HERO};border-bottom:1px solid {BORDER};position:relative;">
  <div style="position:absolute;top:0;left:0;right:0;height:1px;
    background:linear-gradient(90deg,transparent,rgba(201,162,82,.12),transparent);"></div>
  {cell(v('temperature'), '°C', 'TEMPERATURE', TXT_PRI)}
  {cell(v('humidity'),    '%RH','HUMIDITY',    COL_HUM, sub(hdiff,hdc), 'rgba(74,141,200,.025)')}
  {cell(v('voc_index','d'), '/500','VOC INDEX', TXT_PRI, dot_sub(vlbl,vc))}
  {cell(v('rosahl_dehumid_current_ma','.0f'),'mA','DEHUM',COL_DH, dot_sub('ACTIVE' if dha else 'STANDBY', COL_DH if dha else TXT_DIM), 'rgba(61,207,138,.015)')}
  {cell(v('rosahl_humid_current_ma','.0f'), 'mA','HUMID', COL_HM if hma else '#56534f', sub('ACTIVE' if hma else 'STANDBY', COL_HM if hma else TXT_DIM), 'transparent', br=False)}
</div>""")

def render_ctrlbar(preset, target, dehum, humid):
    def pb(p):
        a = p == preset
        s = (f"color:{GOLD};font-weight:700;background:rgba(201,162,82,.1);"
             f"border-left:1px solid rgba(201,162,82,.2);border-right:1px solid rgba(201,162,82,.2);"
             if a else f"color:{TXT_DIM};")
        return f'<div style="padding:3px 10px;font-family:monospace;font-size:7px;letter-spacing:.1em;{s}">{p}</div>'
    def sb(lbl, st_):
        c = COL_LIVE if st_ == "OPEN" else TXT_DIM
        d = COL_LIVE if st_ == "OPEN" else TXT_VDIM
        return (f'<div style="display:flex;align-items:center;gap:5px;">'
                f'<span style="font-family:monospace;font-size:7px;letter-spacing:.1em;color:{TXT_DIM};">{lbl}</span>'
                f'<span style="width:4px;height:4px;border-radius:50%;background:{d};"></span>'
                f'<span style="font-family:monospace;font-weight:700;font-size:7px;color:{c};letter-spacing:.1em;">{st_}</span></div>')
    h(f"""
<div style="display:flex;align-items:center;padding:0 28px;height:42px;
  background:{BG_CARD};border-bottom:1px solid {BORDER};">
  <div style="display:flex;align-items:center;gap:10px;">
    <div style="display:flex;border:1px solid #2a2a34;border-radius:3px;overflow:hidden;">
      {pb("DRY")}{pb("STD")}{pb("MOIST")}
    </div>
    <span style="font-family:monospace;font-weight:700;font-size:8px;color:{GOLD};">{target}%RH</span>
    <span style="font-size:8px;color:{TXT_DIM};">target</span>
  </div>
  <div style="width:1px;height:16px;background:#242430;margin:0 20px;"></div>
  <div style="display:flex;align-items:center;gap:16px;">
    {sb("DEHUM", dehum)}{sb("HUMID", humid)}
  </div>
</div>""")

def render_clbl(color, title, unit, extra=""):
    h(f'<div style="padding:10px 4px 3px;">'
      f'<span style="font-family:monospace;font-weight:700;font-size:7px;letter-spacing:.12em;color:{color};">{title}</span>'
      f'<span style="font-family:monospace;font-size:7px;color:#2e2c28;margin-left:5px;">{unit}</span>'
      f'{extra}</div>')

def render_oplog(op_df, filt):
    if op_df.empty:
        st.markdown(f'<div style="padding:20px;color:{TXT_DIM};font-size:11px;">No logs yet.</div>',
                    unsafe_allow_html=True)
        return

    df2 = op_df
    if filt == "PC":
        df2 = op_df[op_df["event_type"] == "preset_change"]
    elif filt == "SO":
        df2 = op_df[op_df["event_type"].isin(["shutter_open", "shutter_close"])]

    rows = ""
    items = list(df2.head(30).iterrows())
    for i, (_, row) in enumerate(items):
        ev   = row.get("event_type", "")
        det  = str(row.get("detail", "") or "")
        ts   = row.get("occurred_at")
        ts_s = ts.astimezone(JST).strftime("%H:%M:%S") if pd.notna(ts) else "—"
        c    = EVENT_COLORS.get(ev, TXT_DIM)
        last = i == len(items) - 1
        conn = "" if last else f'<div style="width:1px;flex:1;background:{BORDER};margin-top:3px;margin-bottom:-1px;"></div>'
        rows += (
            f'<div style="display:flex;gap:10px;padding:9px 0;border-bottom:1px solid #141418;">'
            f'<div style="display:flex;flex-direction:column;align-items:center;flex-shrink:0;padding-top:2px;">'
            f'<div style="width:6px;height:6px;border-radius:50%;background:{c};"></div>{conn}</div>'
            f'<div style="flex:1;min-width:0;padding-bottom:4px;">'
            f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px;">'
            f'<span style="font-family:monospace;font-weight:600;font-size:7px;letter-spacing:.1em;color:{c};">{ev.upper()}</span>'
            f'<span style="font-family:monospace;font-size:9px;color:{TXT_DIM};">{ts_s}</span></div>'
            f'<p style="font-size:10px;color:{TXT_SEC};margin:0;line-height:1.4;">{det}</p>'
            f'</div></div>'
        )

    h(f"""
<div style="background:{BG_MAIN};border-left:1px solid {BORDER};height:100%;">
  <div style="padding:13px 18px;border-bottom:1px solid {BORDER};
    display:flex;align-items:center;gap:10px;">
    <span style="font-family:monospace;font-weight:700;font-size:8px;letter-spacing:.14em;color:{TXT_PRI};">OPERATION LOG</span>
    <span style="font-family:monospace;font-size:8px;background:#1e1e24;color:#7a7570;
      padding:1px 7px;border-radius:10px;">{len(op_df)}</span>
  </div>
  <div style="padding:6px 18px 14px;">{rows}</div>
</div>""")

# ── Main ───────────────────────────────────────────────────────────────
def main():
    # CSS注入
    st.markdown(CSS, unsafe_allow_html=True)

    # Session state
    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = time.time()

    now_jst    = datetime.now(JST)
    refresh_in = max(0, REFRESH_SEC - int(time.time() - st.session_state.last_refresh))

    # Data fetch
    try:
        sb     = get_sb()
        latest = fetch_latest(sb)
        op_df  = fetch_op_logs(sb)
        # 最新データの鮮度を算出
        latest_ts_df = fetch_sensor_logs(sb, 168)  # 直近7日から最新時刻を取る
        data_age = ""
        if not latest_ts_df.empty:
            last_dt = latest_ts_df["recorded_at"].max()
            delta_min = (datetime.now(pytz.utc) - last_dt).total_seconds() / 60
            if delta_min < 2:
                data_age = ""  # LIVE表示
            elif delta_min < 60:
                data_age = f"{int(delta_min)}分前"
            elif delta_min < 1440:
                data_age = f"{int(delta_min//60)}時間前"
            else:
                data_age = f"{int(delta_min//1440)}日前"
        preset, target   = resolve_preset(op_df)
        dehum_s, humid_s = resolve_shutters(op_df)
    except Exception as e:
        render_navbar(now_jst.strftime("%H:%M:%S"), refresh_in)
        st.error(f"Supabase接続エラー: {e}")
        return

    # Navbar（データ鮮度を反映）
    render_navbar(now_jst.strftime("%H:%M:%S"), refresh_in, data_age)

    # 時間範囲 + ログフィルター
    c1, c2, _ = st.columns([0.3, 0.3, 0.4])
    with c1:
        time_range = st.radio("t", list(RANGE_HOURS.keys()),
                              horizontal=True, index=2, key="tr",
                              label_visibility="collapsed")
    with c2:
        log_filter = st.radio("l", ["ALL", "PC", "SO"],
                              horizontal=True, index=0, key="lf",
                              label_visibility="collapsed")

    # 選択された時間範囲でセンサーログ取得
    df = fetch_sensor_logs(sb, RANGE_HOURS[time_range])

    # Hero + control bar
    render_hero(latest, target)
    render_ctrlbar(preset, target, dehum_s, humid_s)

    # Charts | Op-log
    col_c, col_l = st.columns([1, 0.38], gap="small")

    with col_c:
        render_clbl(COL_HUM, "HUMIDITY", "%RH",
                    f'&nbsp;&nbsp;<span style="font-family:monospace;font-size:7px;color:{GOLD};">— TARGET {target}%RH</span>')
        st.plotly_chart(make_chart(df, "humidity", COL_HUM, "%RH", target=target),
                        use_container_width=True, config={"displayModeBar": False})

        render_clbl(COL_TEMP, "TEMPERATURE", "°C")
        st.plotly_chart(make_chart(df, "temperature", COL_TEMP, "°C"),
                        use_container_width=True, config={"displayModeBar": False})

        render_clbl(COL_VOC, "VOC INDEX", "0–500")
        st.plotly_chart(make_chart(df, "voc_index", COL_VOC, ""),
                        use_container_width=True, config={"displayModeBar": False})

        render_clbl(TXT_PRI, "ROSAHL CURRENT", "mA",
                    f'&nbsp;&nbsp;<span style="font-family:monospace;font-size:7px;color:{COL_DH};">— DEHUM</span>'
                    f'&nbsp;<span style="font-family:monospace;font-size:7px;color:{COL_HM};">— HUMID</span>')
        st.plotly_chart(make_dual(df), use_container_width=True,
                        config={"displayModeBar": False})

    with col_l:
        render_oplog(op_df, log_filter)

    # Auto-refresh: 残り時間待ってからrerun
    if time.time() - st.session_state.last_refresh >= REFRESH_SEC:
        st.session_state.last_refresh = time.time()
        st.rerun()
    else:
        remaining = REFRESH_SEC - int(time.time() - st.session_state.last_refresh)
        time.sleep(min(remaining, 5))
        st.rerun()

if __name__ == "__main__":
    main()
