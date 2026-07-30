"""
VISTAVAULT Monitoring Dashboard — 1c Aurum
Design: Claude Design (Aurum concept)
"""

import time
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import pytz
import streamlit as st
from supabase import create_client

# ── Page config ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="VISTAVAULT MONITORING",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Design tokens ──────────────────────────────────────────────────────
BG_MAIN  = "#0e0e12"
BG_HERO  = "#0c0c10"
BG_CARD  = "#0a0a0e"
BG_NAV   = "#0f0f14"
BORDER   = "#1a1a22"
GOLD     = "#c9a252"
COL_TEMP = "#e8945a"
COL_HUM  = "#4a8dc8"
COL_VOC  = "#9b6fd6"
COL_DH   = "#3dcf8a"
COL_HM   = "#f0c84a"
COL_LIVE = "#3d9e6a"
TXT_PRI  = "#ede8df"
TXT_SEC  = "#6a6560"
TXT_DIM  = "#46443f"
TXT_VDIM = "#36342f"

PRESET_TARGETS = {"DRY": 30, "STD": 50, "MOIST": 70}
RANGE_HOURS    = {"1H": 1, "6H": 6, "24H": 24, "7D": 168}

EVENT_COLORS = {
    "preset_change":   GOLD,
    "shutter_open":    COL_LIVE,
    "shutter_close":   COL_HUM,
    "mode_change":     COL_VOC,
    "solenoid_unlock": COL_TEMP,
}

LOGO_SVG = """<svg width="20" height="20" viewBox="0 0 20 20" fill="none">
  <path d="M10 1.5L18.5 6.25V13.75L10 18.5L1.5 13.75V6.25Z" stroke="#c9a252" stroke-width="1"/>
  <path d="M10 4.5L15 7.5V12.5L10 15.5L5 12.5V7.5Z" stroke="#c9a252" stroke-width=".5" opacity=".4"/>
  <circle cx="10" cy="10" r="1.6" fill="#c9a252" opacity=".7"/>
</svg>"""

JST = pytz.timezone("Asia/Tokyo")
REFRESH_SEC = 30

# ── Supabase ───────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


def fetch_latest(sb) -> dict:
    res = (sb.table("sensor_logs")
             .select("temperature,humidity,voc_index,rosahl_dehumid_current_ma,rosahl_humid_current_ma")
             .order("recorded_at", desc=True).limit(1).execute())
    return res.data[0] if res.data else {}


def fetch_sensor_logs(sb, hours: int) -> pd.DataFrame:
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    res = (sb.table("sensor_logs")
             .select("recorded_at,temperature,humidity,voc_index,rosahl_dehumid_current_ma,rosahl_humid_current_ma")
             .gte("recorded_at", since).order("recorded_at").execute())
    if not res.data:
        return pd.DataFrame()
    df = pd.DataFrame(res.data)
    df["recorded_at"] = pd.to_datetime(df["recorded_at"], format="ISO8601", utc=True)
    return df


def fetch_op_logs(sb, limit: int = 100) -> pd.DataFrame:
    res = (sb.table("operation_logs")
             .select("occurred_at,event_type,detail")
             .order("occurred_at", desc=True).limit(limit).execute())
    if not res.data:
        return pd.DataFrame()
    df = pd.DataFrame(res.data)
    df["occurred_at"] = pd.to_datetime(df["occurred_at"], format="ISO8601", utc=True)
    return df


def resolve_preset(op_df: pd.DataFrame) -> tuple[str, int]:
    if not op_df.empty:
        pc = op_df[op_df["event_type"] == "preset_change"]
        if not pc.empty:
            detail = str(pc.iloc[0].get("detail", "")).upper()
            for p, t in PRESET_TARGETS.items():
                if p in detail:
                    return p, t
    return "STD", 50


def resolve_shutters(op_df: pd.DataFrame) -> tuple[str, str]:
    dehum = humid = "—"
    found_dh = found_hm = False
    for _, row in op_df.iterrows():
        if found_dh and found_hm:
            break
        ev = row.get("event_type", "")
        det = str(row.get("detail", "")).lower()
        state = "OPEN" if ev == "shutter_open" else "CLOSED"
        if not found_dh and "dehum" in det:
            dehum = state; found_dh = True
        if not found_hm and "humid" in det and "dehum" not in det:
            humid = state; found_hm = True
    return dehum, humid


def voc_status(val) -> tuple[str, str]:
    if val is None: return "—",     TXT_DIM
    if val < 100:   return "GOOD",  COL_LIVE
    if val < 200:   return "FAIR",  GOLD
    if val < 300:   return "POOR",  COL_TEMP
    return                 "BAD",   "#cf4a4a"

# ── Plotly ─────────────────────────────────────────────────────────────
_BASE_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor=BG_CARD,
    margin=dict(l=4, r=4, t=2, b=24),
    font=dict(family="JetBrains Mono, monospace", size=9, color=TXT_DIM),
    xaxis=dict(showgrid=False, zeroline=False, tickfont=dict(size=8, color=TXT_DIM),
               linecolor=BORDER, showline=False),
    yaxis=dict(showgrid=True, gridcolor="#16161e", zeroline=False,
               tickfont=dict(size=8, color=TXT_DIM), linecolor=BORDER, showline=False),
    hovermode="x unified",
    hoverlabel=dict(bgcolor=BG_CARD, bordercolor=BORDER, font_size=9,
                    font_family="JetBrains Mono"),
    showlegend=False,
)


def _hex_fill(hex_color: str) -> str:
    return hex_color + "18"


def make_line_chart(df: pd.DataFrame, col: str, color: str,
                    unit: str, height: int = 138, target=None) -> go.Figure:
    fig = go.Figure()
    if not df.empty and col in df.columns:
        y = df[col].where(df[col].notna())
        fig.add_trace(go.Scatter(
            x=df["recorded_at"], y=y,
            mode="lines",
            line=dict(color=color, width=1.5),
            fill="tozeroy", fillcolor=_hex_fill(color),
            hovertemplate=f"%{{y:.1f}}{unit}<extra></extra>",
        ))
    if target is not None:
        fig.add_hline(y=target, line_dash="dot", line_color=GOLD, line_width=1,
                      annotation_text=f"{target}%",
                      annotation_font_color=GOLD, annotation_font_size=8,
                      annotation_position="top right")
    fig.update_layout(**{**_BASE_LAYOUT, "height": height})
    return fig


def make_dual_chart(df: pd.DataFrame, height: int = 138) -> go.Figure:
    fig = go.Figure()
    for col, color, name in [
        ("rosahl_dehumid_current_ma", COL_DH, "DEHUM"),
        ("rosahl_humid_current_ma",   COL_HM, "HUMID"),
    ]:
        if not df.empty and col in df.columns:
            fig.add_trace(go.Scatter(
                x=df["recorded_at"], y=df[col].where(df[col].notna()),
                mode="lines", line=dict(color=color, width=1.5),
                name=name, hovertemplate=f"%{{y:.0f}} mA<extra>{name}</extra>",
            ))
    fig.update_layout(**{**_BASE_LAYOUT, "height": height})
    return fig

# ── CSS ────────────────────────────────────────────────────────────────
def inject_css():
    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400&family=Space+Grotesk:wght@300;400;500;600&family=JetBrains+Mono:wght@300;400;500;600&display=swap');

html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {{
    background: {BG_MAIN} !important;
    color: {TXT_PRI};
}}
[data-testid="stHeader"], [data-testid="stToolbar"] {{ display:none; }}
.main .block-container {{ padding:0 !important; max-width:100% !important; }}
section[data-testid="stSidebar"] {{ display:none; }}
.modebar {{ display:none !important; }}
div[data-testid="stPlotlyChart"] {{
    background:{BG_CARD} !important;
    border:1px solid {BORDER} !important;
    border-radius:4px !important;
    padding:8px 12px 4px !important;
}}
.element-container:has(.stPlotlyChart) {{ margin-bottom:6px !important; }}
/* time-range + log-filter radio — hide Streamlit chrome, show only labels */
div[data-testid="stRadio"] > label {{ display:none; }}
div[data-testid="stRadio"] > div {{
    display:flex !important; flex-direction:row !important;
    gap:2px; background:transparent;
}}
div[data-testid="stRadio"] > div > label {{
    display:flex; align-items:center;
    padding:3px 10px;
    font:400 7px 'JetBrains Mono',monospace; letter-spacing:.1em;
    color:{TXT_DIM}; border:1px solid #2a2a34; border-radius:2px;
    cursor:pointer; background:transparent;
}}
div[data-testid="stRadio"] > div > label[data-selected="true"],
div[data-testid="stRadio"] > div > label:has(input:checked) {{
    font-weight:700; color:{GOLD};
    background:rgba(201,162,82,.12);
    border:1px solid rgba(201,162,82,.2);
}}
div[data-testid="stRadio"] > div > label > span:first-child {{ display:none; }}
/* columns gap */
[data-testid="column"] {{ padding:0 6px !important; }}
@keyframes livepulse {{
    0%,100%{{opacity:1}} 50%{{opacity:.2}}
}}
.live-dot {{
    display:inline-block; width:5px; height:5px; border-radius:50%;
    background:{COL_LIVE}; animation:livepulse 2s ease-in-out infinite;
    vertical-align:middle; margin-right:4px;
}}
</style>""", unsafe_allow_html=True)

# ── HTML blocks ────────────────────────────────────────────────────────
def render_navbar(time_str: str, refresh_in: int):
    st.markdown(f"""
<div style="display:flex;align-items:center;padding:0 28px;height:50px;
            background:linear-gradient(180deg,{BG_NAV} 0%,#0a0a0e 100%);
            border-bottom:1px solid {BORDER};position:relative;">
  <div style="position:absolute;top:0;left:0;right:0;height:1px;
              background:linear-gradient(90deg,transparent 0%,rgba(201,162,82,.5) 25%,rgba(201,162,82,.5) 75%,transparent);"></div>
  <div style="display:flex;align-items:center;gap:12px;">
    {LOGO_SVG}
    <span style="font:600 14px 'Space Grotesk';letter-spacing:.18em;color:{TXT_PRI};">VISTAVAULT</span>
  </div>
  <div style="margin-left:auto;display:flex;align-items:center;gap:20px;">
    <span style="font:300 9px 'Space Grotesk';letter-spacing:.12em;color:#56534f;">MONITORING SYSTEM</span>
    <div style="width:1px;height:14px;background:#2a2a34;"></div>
    <div><span class="live-dot"></span><span style="font:600 9px 'JetBrains Mono';letter-spacing:.12em;color:{COL_LIVE};">LIVE</span></div>
    <span style="font:400 11px 'JetBrains Mono';color:#7a7570;">{time_str} JST</span>
    <span style="font:300 8px 'JetBrains Mono';color:{TXT_VDIM};">↻ {refresh_in}s</span>
  </div>
</div>""", unsafe_allow_html=True)


def render_hero(latest: dict, target: int):
    def _val(k, fmt=".1f"):
        v = latest.get(k)
        return f"{v:{fmt}}" if v is not None else "—"

    hum = latest.get("humidity")
    dh  = latest.get("rosahl_dehumid_current_ma")
    hm  = latest.get("rosahl_humid_current_ma")
    voc = latest.get("voc_index")

    hum_diff = (f"{'▲' if hum and hum > target else '▼'}{abs(hum - target):.1f}"
                f" vs {target}%RH target") if hum else "—"
    hum_dc = GOLD if hum and abs(hum - target) > 2 else COL_LIVE

    voc_lbl, voc_c = voc_status(voc)
    dh_active = dh and dh > 10
    hm_active = hm and hm > 10

    def cell(val_s, unit, label, color, extra="", bg="transparent", last=False):
        border = "" if last else f"border-right:1px solid {BORDER};"
        return f"""
        <div style="flex:1;padding:20px 24px 16px;text-align:center;background:{bg};{border}">
          <div style="font:300 52px 'Cormorant Garamond',serif;line-height:1;color:{color};">{val_s}</div>
          <div style="display:flex;align-items:center;justify-content:center;gap:6px;margin-top:5px;">
            <span style="font:300 14px 'Cormorant Garamond',serif;color:{TXT_DIM};">{unit}</span>
            <span style="width:1px;height:9px;background:#2a2a34;"></span>
            <span style="font:500 7px 'JetBrains Mono';letter-spacing:.18em;color:{TXT_DIM};">{label}</span>
          </div>
          {extra}
        </div>"""

    hum_extra = f'<div style="font:500 8px \'JetBrains Mono\';color:{hum_dc};margin-top:5px;letter-spacing:.08em;">{hum_diff}</div>'
    voc_extra = f'<div style="display:flex;align-items:center;justify-content:center;gap:4px;margin-top:5px;"><span style="width:4px;height:4px;border-radius:50%;background:{voc_c};"></span><span style="font:600 8px \'JetBrains Mono\';color:{voc_c};letter-spacing:.1em;">{voc_lbl}</span></div>'
    dh_extra  = f'<div style="display:flex;align-items:center;justify-content:center;gap:4px;margin-top:5px;"><span style="width:4px;height:4px;border-radius:50%;background:{"#3dcf8a" if dh_active else TXT_VDIM};"></span><span style="font:600 8px \'JetBrains Mono\';color:{"#3dcf8a" if dh_active else TXT_DIM};letter-spacing:.1em;">{"ACTIVE" if dh_active else "STANDBY"}</span></div>'
    hm_extra  = f'<div style="font:600 8px \'JetBrains Mono\';color:{COL_HM if hm_active else TXT_DIM};margin-top:5px;letter-spacing:.08em;">{"ACTIVE" if hm_active else "STANDBY"}</div>'

    st.markdown(f"""
<div style="display:flex;background:{BG_HERO};border-bottom:1px solid {BORDER};position:relative;">
  <div style="position:absolute;top:0;left:0;right:0;height:1px;
              background:linear-gradient(90deg,transparent,rgba(201,162,82,.12),transparent);"></div>
  {cell(_val('temperature'), '°C', 'TEMPERATURE', TXT_PRI)}
  {cell(_val('humidity'),    '%RH','HUMIDITY',    COL_HUM, hum_extra, 'rgba(74,141,200,.025)')}
  {cell(_val('voc_index','d'),'/500','VOC INDEX', TXT_PRI, voc_extra)}
  {cell(_val('rosahl_dehumid_current_ma','.0f'),'mA','DEHUM', COL_DH, dh_extra, 'rgba(61,207,138,.015)')}
  {cell(_val('rosahl_humid_current_ma','.0f'), 'mA','HUMID', COL_HM if hm_active else '#56534f', hm_extra, 'transparent', last=True)}
</div>""", unsafe_allow_html=True)


def render_control_bar(preset: str, target: int, dehum: str, humid: str):
    def p_btn(p):
        active = p == preset
        s = (f"color:{GOLD};font-weight:700;background:rgba(201,162,82,.1);"
             f"border-left:1px solid rgba(201,162,82,.2);border-right:1px solid rgba(201,162,82,.2);") if active else f"color:{TXT_DIM};"
        return f'<div style="padding:3px 10px;font:500 7px \'JetBrains Mono\';letter-spacing:.1em;{s}">{p}</div>'

    def sh_badge(label, state):
        c = COL_LIVE if state == "OPEN" else TXT_DIM
        d = COL_LIVE if state == "OPEN" else TXT_VDIM
        return (f'<div style="display:flex;align-items:center;gap:5px;">'
                f'<span style="font:400 7px \'JetBrains Mono\';letter-spacing:.1em;color:{TXT_DIM};">{label}</span>'
                f'<span style="width:4px;height:4px;border-radius:50%;background:{d};"></span>'
                f'<span style="font:700 7px \'JetBrains Mono\';color:{c};letter-spacing:.1em;">{state}</span>'
                f'</div>')

    st.markdown(f"""
<div style="display:flex;align-items:center;padding:0 28px;height:42px;
            background:{BG_CARD};border-bottom:1px solid {BORDER};">
  <div style="display:flex;align-items:center;gap:10px;">
    <div style="display:flex;border:1px solid #2a2a34;border-radius:3px;overflow:hidden;">
      {p_btn("DRY")}{p_btn("STD")}{p_btn("MOIST")}
    </div>
    <span style="font:700 8px 'JetBrains Mono';color:{GOLD};">{target}%RH</span>
    <span style="font:400 8px 'Space Grotesk';color:{TXT_DIM};">target</span>
  </div>
  <div style="width:1px;height:16px;background:#242430;margin:0 20px;"></div>
  <div style="display:flex;align-items:center;gap:16px;">
    {sh_badge("DEHUM", dehum)}
    {sh_badge("HUMID", humid)}
  </div>
</div>""", unsafe_allow_html=True)


def render_chart_label(color: str, title: str, unit: str, extra: str = ""):
    st.markdown(
        f'<div style="padding:10px 4px 3px;">'
        f'<span style="font:700 7px \'JetBrains Mono\';letter-spacing:.12em;color:{color};">{title}</span>'
        f'<span style="font:300 7px \'JetBrains Mono\';color:#2e2c28;margin-left:5px;">{unit}</span>'
        f'{extra}</div>',
        unsafe_allow_html=True,
    )


def render_op_log(op_df: pd.DataFrame, filt: str):
    if op_df.empty:
        rows = '<div style="padding:20px;color:' + TXT_DIM + ';font:400 10px \'Space Grotesk\';">No logs yet.</div>'
    else:
        if filt == "PC":
            df2 = op_df[op_df["event_type"] == "preset_change"]
        elif filt == "SO":
            df2 = op_df[op_df["event_type"].isin(["shutter_open", "shutter_close"])]
        else:
            df2 = op_df

        items = df2.head(25)
        rows = ""
        for i, (_, row) in enumerate(items.iterrows()):
            ev  = row.get("event_type", "")
            det = row.get("detail", "") or ""
            ts  = row.get("occurred_at")
            ts_s = ts.astimezone(JST).strftime("%H:%M:%S") if pd.notna(ts) else "—"
            c   = EVENT_COLORS.get(ev, TXT_DIM)
            is_last = i == len(items) - 1
            connector = "" if is_last else (
                f'<div style="width:1px;flex:1;background:{BORDER};margin-top:3px;margin-bottom:-1px;"></div>')
            rows += f"""
            <div style="display:flex;gap:10px;padding:9px 0;border-bottom:1px solid #141418;">
              <div style="display:flex;flex-direction:column;align-items:center;flex-shrink:0;padding-top:2px;">
                <div style="width:6px;height:6px;border-radius:50%;background:{c};"></div>
                {connector}
              </div>
              <div style="flex:1;min-width:0;padding-bottom:4px;">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px;">
                  <span style="font:600 7px 'JetBrains Mono';letter-spacing:.1em;color:{c};">{ev.upper()}</span>
                  <span style="font:300 9px 'JetBrains Mono';color:{TXT_DIM};">{ts_s}</span>
                </div>
                <p style="font:400 10px 'Space Grotesk';color:{TXT_SEC};margin:0;line-height:1.4;">{det}</p>
              </div>
            </div>"""

    count = len(op_df)
    st.markdown(f"""
<div style="background:{BG_MAIN};border-left:1px solid {BORDER};height:100%;">
  <div style="padding:13px 18px;border-bottom:1px solid {BORDER};
              display:flex;align-items:center;gap:10px;">
    <span style="font:700 8px 'JetBrains Mono';letter-spacing:.14em;color:{TXT_PRI};">OPERATION LOG</span>
    <span style="font:700 8px 'JetBrains Mono';background:#1e1e24;color:#7a7570;
                 padding:1px 7px;border-radius:10px;">{count}</span>
  </div>
  <div style="padding:6px 18px 14px;">{rows}</div>
</div>""", unsafe_allow_html=True)

# ── Main ───────────────────────────────────────────────────────────────
def main():
    inject_css()

    # Session state
    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = time.time()

    # ── Navbar ─────────────────────────────────────────────────────────
    now_jst    = datetime.now(JST)
    refresh_in = max(0, REFRESH_SEC - int(time.time() - st.session_state.last_refresh))
    render_navbar(now_jst.strftime("%H:%M:%S"), refresh_in)

    # ── Control strip: time-range + log-filter (Streamlit widgets) ─────
    ctrl_l, ctrl_r = st.columns([1, 1])
    with ctrl_l:
        time_range = st.radio(
            "time", options=list(RANGE_HOURS.keys()),
            horizontal=True, index=0, key="time_range", label_visibility="collapsed"
        )
    with ctrl_r:
        log_filter = st.radio(
            "log", options=["ALL", "PC", "SO"],
            horizontal=True, index=0, key="log_filter", label_visibility="collapsed"
        )

    # ── Data ───────────────────────────────────────────────────────────
    sb      = get_supabase()
    latest  = fetch_latest(sb)
    df      = fetch_sensor_logs(sb, RANGE_HOURS[time_range])
    op_df   = fetch_op_logs(sb, limit=100)
    preset, target   = resolve_preset(op_df)
    dehum_s, humid_s = resolve_shutters(op_df)

    # ── Hero + control bar ─────────────────────────────────────────────
    render_hero(latest, target)
    render_control_bar(preset, target, dehum_s, humid_s)

    # ── Main area: charts | op-log ─────────────────────────────────────
    col_charts, col_log = st.columns([1, 0.38], gap="small")

    with col_charts:
        target_line = target if not df.empty else None

        render_chart_label(
            COL_HUM, "HUMIDITY", "%RH",
            f'&nbsp;&nbsp;<span style="font:400 7px \'JetBrains Mono\';color:{GOLD};">— TARGET {target}%RH</span>',
        )
        st.plotly_chart(
            make_line_chart(df, "humidity", COL_HUM, "%RH", target=target_line),
            use_container_width=True, config={"displayModeBar": False},
        )

        render_chart_label(COL_TEMP, "TEMPERATURE", "°C")
        st.plotly_chart(
            make_line_chart(df, "temperature", COL_TEMP, "°C"),
            use_container_width=True, config={"displayModeBar": False},
        )

        render_chart_label(COL_VOC, "VOC INDEX", "0–500")
        st.plotly_chart(
            make_line_chart(df, "voc_index", COL_VOC, ""),
            use_container_width=True, config={"displayModeBar": False},
        )

        render_chart_label(
            TXT_PRI, "ROSAHL CURRENT", "mA",
            f'&nbsp;&nbsp;<span style="color:{COL_DH};font:400 7px \'JetBrains Mono\';">— DEHUM</span>'
            f'&nbsp;<span style="color:{COL_HM};font:400 7px \'JetBrains Mono\';">— HUMID</span>',
        )
        st.plotly_chart(
            make_dual_chart(df),
            use_container_width=True, config={"displayModeBar": False},
        )

    with col_log:
        render_op_log(op_df, log_filter)

    # ── Auto-refresh ───────────────────────────────────────────────────
    if time.time() - st.session_state.last_refresh >= REFRESH_SEC:
        st.session_state.last_refresh = time.time()
        st.rerun()
    time.sleep(1)
    st.rerun()


if __name__ == "__main__":
    main()
