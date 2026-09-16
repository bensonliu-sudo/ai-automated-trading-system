# coding: utf-8
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional
import pandas as pd

import streamlit as st
import streamlit.components.v1 as components
# --- Place below the top-level imports in app/web.py ---
from streamlit.components.v1 import html as st_html
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "intel.db"

st.set_page_config(page_title="Intel Hub - Live Dashboard", page_icon="🛰️", layout="wide")
# --- Front-end script loaded once: save/restore scroll position ---
components.html("""
<script>
(function() {
  const KEY = 'st-scroll-top';
  function save() {
    try {
      const y = document.scrollingElement ? document.scrollingElement.scrollTop : window.pageYOffset;
      localStorage.setItem(KEY, String(y||0));
    } catch(e){}
  }
  function restore() {
    try {
      const v = parseFloat(localStorage.getItem(KEY) || '0');
      if (!isNaN(v)) window.scrollTo({top: v, behavior: 'instant'});
    } catch(e){}
  }
  // Restore once immediately on first mount
  restore();
  // Streamlit re-renders frequently: restore again after DOM changes
  new MutationObserver(() => { restore(); }).observe(document.body, {subtree: true, childList: true});
  // Save scroll position
  window.addEventListener('scroll', save, {passive: true});
  window.addEventListener('beforeunload', save);
})();
</script>
""", height=0)
# ========== Styles ==========
st.markdown("""
<style>
.radar{position:relative;width:20px;height:20px;margin-right:8px}
.radar:before,.radar:after{content:"";position:absolute;border:2px solid rgba(0,200,0,.7);border-radius:50%;inset:0;animation:pulse 1.6s linear infinite}
.radar:after{animation-delay:.8s}
@keyframes pulse{0%{transform:scale(.3);opacity:.9}70%{transform:scale(1.4);opacity:.1}100%{transform:scale(1.6);opacity:0}}
.header-small{color:#8b8b8b;font-size:.9rem;margin-top:2px}
.table-note{color:#909090;font-size:.85rem;margin-top:-6px}
.ih-table{width:100%;border-collapse:collapse;font-size:14px}
.ih-table th,.ih-table td{border-bottom:1px solid rgba(255,255,255,.08);padding:8px 10px;vertical-align:top}
.ih-table th{position:sticky;top:0;background:rgba(0,0,0,.25);backdrop-filter:blur(6px)}
.ih-link{color:inherit;text-decoration:none}
.ih-link:hover{text-decoration:underline}
.nowrap{white-space:nowrap}
.score-badge{padding:2px 8px;border-radius:999px;background:rgba(253,126,20,.15);border:1px solid rgba(253,126,20,.35)}
.small{font-size:12px;color:#a0a0a0}
/* Control vertical spacing between all stacked blocks */
div[data-testid="stVerticalBlock"] {
  gap: 0.2rem !important;          /* default is about 1.5rem; can shrink to 0.2-0.4 */
  margin-top: 0rem !important;     /* remove default extra top whitespace */
  margin-bottom: 0rem !important;  /* remove default extra bottom whitespace */
  padding-top: 0rem !important;
  padding-bottom: 0rem !important;
}
/* Whitespace between table container and controls above */
div[data-testid="stDataFrame"],
div[data-testid="stTable"] {
  margin-top: 0.3rem !important;   /* default is close to 2rem; compress it */
}
/* ========== Top whitespace (header placeholder) ========== */
/* Option A: hide the Streamlit header entirely, placeholder height becomes 0 */
header[data-testid="stHeader"]{
  height: 0px !important;
  visibility: hidden !important;
}
/* Some versions have an extra div inside the header; hiding it too is safer */
header[data-testid="stHeader"] > div { display: none !important; }

/* ========== Main container vertical padding (the master control for shifting everything up) ========== */
/* Change this to lift all content up. Try values between 0.6rem and 1rem */
.block-container{
  padding-top: 0rem !important;   /* <- top whitespace (smaller = higher) */
  padding-bottom: 0.6rem !important;/* bottom whitespace */
}

/* ========== Vertical spacing between blocks (whitespace between rows) ========== */
/* The default gap between rows is large; compress it uniformly here */
div[data-testid="stVerticalBlock"]{
  gap: 0.35rem !important;          /* default about 1.5rem -> make it more compact */
  margin-top: -5rem !important;#this is the key line
  margin-bottom: 0rem !important;
  padding-top: 0rem !important;
  padding-bottom: 0rem !important;
}

/* ========== Fine-tune spacing between table/heading and the row above (optional) ========== */
/* If the "Headlines" heading or table still looks loose, compress further here */
h2, h3, .stMarkdown h2, .stMarkdown h3{
  margin-top: 0.4rem !important;
  margin-bottom: 0.4rem !important;
}
div[data-testid="stDataFrame"], div[data-testid="stTable"]{
  margin-top: 0.35rem !important;
}

/* ========== Compress the top search/status area further (optional) ========== */
/* If the "radar + search box" row still sits too low, wrap that row in a container
   with class="topbar" and tune it separately here (optional; can be removed) */
.topbar{
  margin-top: 0rem !important;
  padding-top: 0rem !important;
}

/* Keep your previous color/link/table styles (if any) below this line ... */


</style>
""", unsafe_allow_html=True)

# ========== Top bar controls ==========
# left, mid, right, more = st.columns([1.1, 1.1, 1.6, 1.2], gap="small")
# with left:
#     min_score = st.slider("Min_threshold", 0, 100, 70, 5)
# # with mid:
# #     window_hours = st.slider("Lookback window (hours)", 1, 72, 48, 1)
# with right:
#     query = st.text_input("Search (headlines, sources, symbols, tags)", "")
# with more:
#     critical_only = st.checkbox("Critical only (>=critical)", value=False)

# col_a, col_b = st.columns([1, 2])
# with col_a:
#     auto_refresh = st.checkbox("Auto refresh", value=True)
# with col_b:
#     interval = st.select_slider("Refresh interval (seconds)", options=[5,10,15,20,30,45,60], value=10)

# # Soft workaround: full-page refresh + save/restore scroll position (feels like a partial refresh)
# # Use a partial rerun without triggering a full page reload (scroll position preserved)
# if auto_refresh:
#     st_autorefresh(interval=interval * 1000, key="auto-rerun")

components.html(f"""
<script>
(function(){{
  const KEY='ih_scroll_y';
  function saveScroll(){{ localStorage.setItem(KEY, String(window.scrollY||0)); }}
  window.addEventListener('beforeunload', saveScroll);
  document.addEventListener('visibilitychange', ()=>{{ if(document.hidden) saveScroll(); }});
  const y = parseFloat(localStorage.getItem(KEY)||'0');
  if (!isNaN(y)) {{
    // Wait for the Streamlit layout to render before restoring scroll
    setTimeout(()=>window.scrollTo({{top:y, behavior:'instant'}}), 60);
  }}
}})();
</script>
""", height=0)

# ========== Radar indicator ==========
# ========= Top bar (radar + status + search) in one row =========
radar_col, status_col, search_col = st.columns([0.06, 0.34, 0.60], gap="small")

with radar_col:
    # Small radar on the left
    st.markdown("<div class='radar'></div>", unsafe_allow_html=True)

with status_col:
    # Two status lines in the middle (both original lines kept)
    st.markdown("**Collectors running…** _collector tasks active_")
    st.markdown("<div class='header-small'></div>", unsafe_allow_html=True)

with search_col:
    # Only the search box on the right (label collapsed to reduce height)
    query = st.text_input(
        "Keyword search (headline, source, symbols, tags)",
        key="q",
        placeholder="Search keywords across headline/source/symbols/tags",
        label_visibility="collapsed",
    )
st.markdown("---")

# ========== DB utilities ==========
def _now_ms() -> int:
    import time
    return int(time.time() * 1000)

def _utc_ms_to_local_str(ms: int, tz_name: str) -> str:
    import datetime, pytz
    tz = pytz.timezone(tz_name)
    dt = datetime.datetime.utcfromtimestamp(ms/1000.0).replace(tzinfo=pytz.UTC)
    return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")

def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def _fetch_unpushed(conn, since_ms: int, query: str) -> pd.DataFrame:
    sql = """
    SELECT id, ts_detected_utc, ts_published_utc, headline, source, link,
           market, symbols, categories, tags, score, pushed,
           thread_key
    FROM events
    WHERE ts_detected_utc >= ? AND IFNULL(pushed,0)=0
    """
    params = [since_ms]
    if query.strip():
        like = f"%{query.strip()}%"
        sql += " AND (headline LIKE ? OR source LIKE ? OR symbols LIKE ? OR tags LIKE ?)"
        params += [like, like, like, like]
    sql += " ORDER BY ts_detected_utc DESC LIMIT 200"
    return pd.read_sql_query(sql, conn, params=params)

def _fetch_high(conn, since_ms: int, min_score: int, query: str, critical_only: bool) -> pd.DataFrame:
    sql = """
    SELECT id, ts_detected_utc, ts_published_utc, headline, source, link,
           market, symbols, categories, tags, score, pushed,
           thread_key
    FROM events
    WHERE ts_detected_utc >= ? AND score >= ?
    """
    params = [since_ms, min_score]
    if critical_only:
        sql += " AND score >= 90"   # your original "critical" logic
    if query.strip():
        like = f"%{query.strip()}%"
        sql += " AND (headline LIKE ? OR source LIKE ? OR symbols LIKE ? OR tags LIKE ?)"
        params += [like, like, like, like]
    sql += " ORDER BY score DESC, ts_detected_utc DESC LIMIT 500"
    return pd.read_sql_query(sql, conn, params=params)

def _top_count(df: pd.DataFrame, col: str, n: int = 10) -> pd.DataFrame:
    if col not in df:
        return pd.DataFrame(columns=[col, "count"])
    s = df[col].astype(str).str.split(r"[;,|\s]+", regex=True).explode()
    s = s[s.str.len() > 0]
    return s.value_counts().reset_index().rename(columns={"index": col, 0: "count"}).head(n)
# --- Insert where df_recent (or df_top) is queried, before rendering: ---
def _dedupe_latest(df: pd.DataFrame) -> pd.DataFrame:
    """
    Force dedupe by normalized headline:
      - source is ignored
      - for each headline keep the highest-score, most recent row
    """
    if df is None or df.empty:
        return df

    # Normalize headline: lowercase, collapse whitespace, strip special chars, truncate
    norm = (
        df.get("headline", "").fillna("")
          .str.lower()
          .str.replace(r"\s+", " ", regex=True)
          .str.replace(r"[^\w\s]", "", regex=True)
          .str.strip()
          .str.slice(0, 160)
    )

    # Sort: highest score first, then most recent
    tmp = df.assign(_key=norm).sort_values(
        by=["score", "ts_detected_utc"],
        ascending=[False, False],
        kind="mergesort",
    )

    # Dedupe: keep only one row per headline
    out = tmp.drop_duplicates(subset="_key", keep="first").drop(columns=["_key"])

    # Final output sorted by time (newest first)
    return out.sort_values(by="ts_detected_utc", ascending=False).reset_index(drop=True)
# ========== HTML table rendering (headline as clickable text) ==========
def render_table_html(df: pd.DataFrame, tz_name: str, *, show_score: bool = True) -> str:
    cols = ["Time", "Source"] + (["Score"] if show_score else []) + ["Headline", "symbols", "tags"]
    rows = []
    for _, r in df.iterrows():
        time_str = _utc_ms_to_local_str(int(r["ts_detected_utc"]), tz_name)
        src = str(r.get("source", "") or "")
        score = int(r.get("score", 0) or 0)
        title = str(r.get("headline", "") or "")
        link = str(r.get("link", "") or "")
        symbols = str(r.get("symbols", "") or "")
        tags = str(r.get("tags", "") or "")
        # Headline shown as text; clickable if a link exists
        if link.startswith("http"):
            title_html = f"<a class='ih-link' href='{link}' target='_blank' rel='noopener noreferrer'>{title}</a>"
        else:
            title_html = title
        tds = [
            f"<td class='nowrap small'>{time_str}</td>",
            f"<td>{src}</td>",
        ]
        if show_score:
            tds.append(f"<td><span class='score-badge'>{score}</span></td>")
        tds += [
            f"<td>{title_html}</td>",
            f"<td class='small'>{symbols}</td>",
            f"<td class='small'>{tags}</td>",
        ]
        rows.append("<tr>" + "".join(tds) + "</tr>")
    thead = "<tr>" + "".join([f"<th>{c}</th>" for c in cols]) + "</tr>"
    return f"<table class='ih-table'><thead>{thead}</thead><tbody>{''.join(rows)}</tbody></table>"

# ========== Read DB & display ==========
since_ms = _now_ms() - 48 * 3600 * 1000
try:
    conn = _connect()
except Exception as e:
    st.error(f"Cannot connect to database: {DB_PATH}\n{e}")
    st.stop()

# Unpushed
# Unpushed (by time)
df_unpushed = _fetch_unpushed(conn, since_ms, query)
df_unpushed = _dedupe_latest(df_unpushed) 
df_high = _fetch_high(conn, since_ms, 70, query, False)
df_high = _dedupe_latest(df_high)
# Latest unpushed stream
st.subheader("🛰️ Headlines")
if df_unpushed.empty:
    st.info("No unpushed events in the window.")
else:
    html = render_table_html(df_unpushed, tz_name="Australia/Sydney", show_score=True)
    st.markdown(html, unsafe_allow_html=True)
    st.markdown("<div class='table-note'></div>", unsafe_allow_html=True)

st.markdown("---")

# High-priority + trending
left_main, right_main = st.columns([0.62, 0.38])

with left_main:
    st.subheader("📌 High-priority stream (by score desc)")
    if df_high.empty:
        st.warning("No matching events in the window. Lower the minimum score or widen the lookback window.")
    else:
        html = render_table_html(df_high, tz_name="Australia/Sydney", show_score=True)
        st.markdown(html, unsafe_allow_html=True)

with right_main:
    st.subheader("🔥 Trending")
    h1_since = _now_ms() - 1*3600*1000
    h24_since = _now_ms() - 24*3600*1000
    df_1h = pd.read_sql_query("SELECT symbols,tags FROM events WHERE ts_detected_utc>=?", conn, params=[h1_since])
    df_24h= pd.read_sql_query("SELECT symbols,tags FROM events WHERE ts_detected_utc>=?", conn, params=[h24_since])

    st.caption("Symbols - last 1 hour")
    st.dataframe(_top_count(df_1h, "symbols", 10), use_container_width=True, hide_index=True)

    st.caption("Tags - last 1 hour")
    st.dataframe(_top_count(df_1h, "tags", 10), use_container_width=True, hide_index=True)

    st.caption("Symbols - last 24 hours")
    st.dataframe(_top_count(df_24h, "symbols", 10), use_container_width=True, hide_index=True)

    st.caption("Tags - last 24 hours")
    st.dataframe(_top_count(df_24h, "tags", 10), use_container_width=True, hide_index=True)

try:
    conn.close()
except Exception:
    pass