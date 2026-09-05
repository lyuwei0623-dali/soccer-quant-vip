import streamlit as st
import numpy as np
import pandas as pd
import requests
import hashlib
import io
import time
import os
import base64
import sqlite3
from datetime import datetime, date, timedelta, timezone

# 1. 頁面設定（支援手機響應式寬度與捲動）
st.set_page_config(
    page_title="雙運動量化定價系統 (官方VIP)",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ================= 品牌防偽客製化設定 =================
BRAND_NAME = "維大力"              
BRAND_TAGLINE = "官方唯一正版認證 ｜ 賽事數據量化分析" 
CUSTOM_LOGO_URL = ""               
WATERMARK_TEXT = "維大力 官方正版認證" 

# ================= 密碼與金鑰設定 =================
MASTER_PASSCODE = "ADMIN999"      
SECRET_SALT = "MySecretKey2026"  

# ================= 尾盤自動封存資料庫 (SQLite) =================
DB_FILE = "closing_odds.db"

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS soccer_odds (
                        date_str TEXT, home TEXT, away TEXT,
                        ou_line REAL, is_locked INTEGER,
                        UNIQUE(date_str, home, away))''')
        c.execute('''CREATE TABLE IF NOT EXISTS mlb_odds (
                        date_str TEXT, home TEXT, away TEXT,
                        ou_line REAL, is_locked INTEGER,
                        UNIQUE(date_str, home, away))''')
        conn.commit()

init_db()

def get_db_ou(sport, date_str, home, away):
    table = "soccer_odds" if sport == "soccer" else "mlb_odds"
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(f"SELECT ou_line, is_locked FROM {table} WHERE date_str=? AND home=? AND away=?", (date_str, home, away))
        row = c.fetchone()
        return (row[0], row[1]) if row else (None, 0)

def save_db_ou(sport, date_str, home, away, ou_line, is_locked):
    table = "soccer_odds" if sport == "soccer" else "mlb_odds"
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(f"""
            INSERT INTO {table} (date_str, home, away, ou_line, is_locked)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(date_str, home, away) DO UPDATE SET
                ou_line=excluded.ou_line,
                is_locked=excluded.is_locked
            WHERE is_locked = 0
        """, (date_str, home, away, ou_line, int(is_locked)))
        conn.commit()

def sync_odds(sport, date_str, home, away, api_state, api_ou):
    db_ou, is_locked = get_db_ou(sport, date_str, home, away)
    is_completed = (api_state in ['in', 'post', 'Live', 'Final'])
    if db_ou and is_locked:
        return db_ou
    if api_ou:
        save_db_ou(sport, date_str, home, away, api_ou, is_completed)
        return api_ou
    if db_ou:
        save_db_ou(sport, date_str, home, away, db_ou, True)
        return db_ou
    return None

def force_update_fallback(sport, date_str, home, away, calc_ou):
    save_db_ou(sport, date_str, home, away, calc_ou, 1)

# ================= 1. 裝置綁定與 1 週防偽認證系統 =================
@st.cache_resource
def get_device_registry():
    return {}

def get_client_fingerprint():
    try:
        ua = st.context.headers.get("User-Agent", "default_ua")
        return hashlib.md5(ua.encode()).hexdigest()[:10]
    except Exception:
        return "device_default"

def generate_vip_token(user_name: str, issue_date: date = None) -> str:
    if not issue_date:
        issue_date = date.today()
    user_clean = user_name.strip().replace(" ", "").upper()
    date_str = issue_date.strftime("%Y-%m-%d")
    sig = hashlib.sha256(f"{user_clean}_{date_str}_{SECRET_SALT}".encode()).hexdigest()[:4].upper()
    return f"{user_clean}_{sig}"

def parse_and_validate_token(token: str):
    clean_token = token.strip().upper()
    if clean_token == MASTER_PASSCODE:
        return True, "管理員", date.today(), 999
    if "_" not in clean_token:
        return False, None, None, 0
    parts = clean_token.rsplit("_", 1)
    user_name, sig = parts[0], parts[1]
    if len(sig) != 4 or not user_name:
        return False, None, None, 0
    today = date.today()
    for i in range(8):
        check_date = today - timedelta(days=i)
        date_str = check_date.strftime("%Y-%m-%d")
        expected_sig = hashlib.sha256(f"{user_name}_{date_str}_{SECRET_SALT}".encode()).hexdigest()[:4].upper()
        if sig == expected_sig:
            return True, user_name, check_date, 7 - i
    return False, None, None, 0

def apply_branding_css():
    st.markdown(f"""
    <style>
    .stApp::before {{
        content: "{WATERMARK_TEXT}";
        position: fixed;
        top: 40%;
        left: 15%;
        width: 70%;
        text-align: center;
        transform: rotate(-25deg);
        font-size: 38px;
        font-weight: 900;
        color: rgba(225, 29, 72, 0.04);
        pointer-events: none;
        z-index: 0;
        font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif;
        letter-spacing: 6px;
    }}
    </style>
    """, unsafe_allow_html=True)

def render_brand_header():
    logo_html = ""
    if CUSTOM_LOGO_URL:
        logo_html = f'<img src="{CUSTOM_LOGO_URL}" style="width: 48px; height: 48px; border-radius: 50%; border: 2px solid #f59e0b; margin-right: 12px; object-fit: cover;">'
    else:
        for ext in ["jpg", "jpeg", "png", "webp", "jgp"]:
            filename = f"logo.{ext}"
            if os.path.exists(filename):
                try:
                    with open(filename, "rb") as img_f:
                        encoded = base64.b64encode(img_f.read()).decode()
                    mime_type = "jpeg" if ext in ["jpg", "jpeg", "jgp"] else ext
                    logo_html = f'<img src="data:image/{mime_type};base64,{encoded}" style="width: 48px; height: 48px; border-radius: 50%; border: 2px solid #f59e0b; margin-right: 12px; object-fit: cover;">'
                    break
                except Exception:
                    pass
        if not logo_html:
            logo_html = '<div style="background: linear-gradient(135deg, #f59e0b, #d97706); width: 44px; height: 44px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 22px; color: #fff; margin-right: 12px; font-weight: bold; box-shadow: 0 2px 6px rgba(245, 158, 11, 0.4);">🛡️</div>'

    header_html = f"""
    <div style="background: linear-gradient(90deg, #0f172a, #1e293b); border: 1px solid #334155; padding: 12px 16px; border-radius: 10px; display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">
        <div style="display: flex; align-items: center;">
            {logo_html}
            <div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="color: #f8fafc; font-size: 16px; font-weight: 800; letter-spacing: 0.5px;">{BRAND_NAME} 體育量化定價系統</span>
                    <span style="background: linear-gradient(90deg, #f59e0b, #d97706); color: #000; font-size: 10px; font-weight: 900; padding: 2px 6px; border-radius: 4px; text-transform: uppercase;">官方正版</span>
                </div>
                <div style="color: #94a3b8; font-size: 11px; margin-top: 2px;">{BRAND_TAGLINE}</div>
            </div>
        </div>
        <div style="text-align: right;"><span style="color: #38bdf8; font-size: 11px; font-weight: 600;">● 核心在線</span></div>
    </div>
    """
    st.markdown(header_html, unsafe_allow_html=True)

registry = get_device_registry()
url_vip = st.query_params.get("vip", "").strip().upper()
dev_fp = get_client_fingerprint()
auth_msg = ""
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
    st.session_state["is_admin"] = False
    st.session_state["user_name"] = ""
    st.session_state["current_token"] = ""
    st.session_state["days_left"] = 0

def try_authenticate(input_token: str):
    clean = input_token.strip().upper()
    if not clean:
        return False, "請輸入通行碼！"
    if clean == MASTER_PASSCODE:
        st.session_state["authenticated"] = True
        st.session_state["is_admin"] = True
        st.session_state["user_name"] = "管理員"
        st.session_state["current_token"] = MASTER_PASSCODE
        st.query_params["vip"] = MASTER_PASSCODE
        return True, "管理員登入成功！"
    is_valid, u_name, issue_dt, rem_days = parse_and_validate_token(clean)
    if not is_valid:
        return False, "⛔ 通行碼無效或已過期，請向官方管理員領取最新通行碼！"
    if clean not in registry:
        registry[clean] = {"user_name": u_name, "issue_date": issue_dt.strftime("%Y-%m-%d"), "dev_id": dev_fp, "bound_at": datetime.now().strftime("%m-%d %H:%M")}
    else:
        bound_dev = registry[clean].get("dev_id", "")
        if bound_dev and bound_dev != dev_fp and bound_dev != "device_default":
            return False, "⛔ 訪問被拒：此 VIP 代碼已綁定其他手機，嚴禁轉傳！"
    st.session_state["authenticated"] = True
    st.session_state["is_admin"] = False
    st.session_state["user_name"] = u_name
    st.session_state["current_token"] = clean
    st.session_state["days_left"] = rem_days
    st.query_params["vip"] = clean
    return True, "驗證成功！"

if not st.session_state["authenticated"] and url_vip:
    ok, msg = try_authenticate(url_vip)
    if not ok:
        auth_msg = msg

# ================= 3. 歐洲五大聯賽與歐冠量化引擎 =================
BASE_SOCCER_ELO = {
    "Real Madrid": 2010.0, "Barcelona": 1935.0, "Atletico Madrid": 1865.0, "Girona": 1785.0,
    "Athletic Club": 1805.0, "Athletic": 1805.0, "Real Sociedad": 1775.0, "Villarreal": 1775.0,
    "Real Betis": 1745.0, "Sevilla": 1710.0, "Celta Vigo": 1685.0, "Celta": 1685.0,
    "Osasuna": 1675.0, "Mallorca": 1680.0, "Valencia": 1690.0, "Rayo Vallecano": 1680.0,
    "Las Palmas": 1650.0, "Getafe": 1660.0, "Alaves": 1660.0, "Leganes": 1635.0,
    "Espanyol": 1655.0, "Valladolid": 1625.0, "Manchester City": 2020.0, "Arsenal": 1985.0,
    "Liverpool": 1970.0, "Chelsea": 1835.0, "Tottenham": 1815.0, "Tottenham Hotspur": 1815.0,
    "Newcastle": 1815.0, "Newcastle United": 1815.0, "Aston Villa": 1835.0, "Manchester United": 1785.0,
    "Brighton": 1775.0, "Brighton & Hove Albion": 1775.0, "West Ham": 1725.0, "West Ham United": 1725.0,
    "Fulham": 1715.0, "Bournemouth": 1705.0, "Brentford": 1705.0, "Crystal Palace": 1715.0,
    "Wolves": 1685.0, "Wolverhampton Wanderers": 1685.0, "Everton": 1690.0, "Nottingham Forest": 1685.0,
    "Leicester": 1675.0, "Southampton": 1635.0, "Ipswich": 1615.0, "Ipswich Town": 1615.0,
    "Hull City": 1650.0, "Hull": 1650.0, "Sunderland": 1660.0, "Coventry City": 1640.0,
    "Coventry": 1640.0, "Leeds United": 1670.0, "Leeds": 1670.0, "Bayern Munich": 1955.0,
    "Bayer Leverkusen": 1945.0, "Borussia Dortmund": 1875.0, "RB Leipzig": 1875.0, "Stuttgart": 1835.0,
    "Eintracht Frankfurt": 1785.0, "Freiburg": 1745.0, "Wolfsburg": 1725.0, "Mainz": 1705.0,
    "Augsburg": 1705.0, "Werder Bremen": 1715.0, "Inter": 1975.0, "Internazionale": 1975.0,
    "Atalanta": 1885.0, "Juventus": 1875.0, "Milan": 1865.0, "AC Milan": 1865.0,
    "Roma": 1805.0, "Lazio": 1805.0, "Napoli": 1825.0, "Bologna": 1815.0,
    "Fiorentina": 1775.0, "Torino": 1755.0, "Paris Saint-Germain": 1925.0, "Monaco": 1835.0,
    "Lille": 1815.0, "Marseille": 1785.0, "Lyon": 1775.0, "Nice": 1775.0,
    "Lens": 1765.0, "Brest": 1765.0, "Rennes": 1755.0
}

SOCCER_LEAGUES = {
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 英格蘭超級聯賽 (Premier League)": "eng.1",
    "🇪🇸 西班牙甲級聯賽 (La Liga)": "esp.1",
    "🇩🇪 德國甲級聯賽 (Bundesliga)": "ger.1",
    "🇮🇹 義大利甲級聯賽 (Serie A)": "ita.1",
    "🇫🇷 法國甲級聯賽 (Ligue 1)": "fra.1",
    "🏆 歐洲冠軍聯賽 (UEFA Champions League)": "uefa.champions"
}

SOCCER_GOALS = {
    "eng.1": {"home": 1.55, "away": 1.25}, "esp.1": {"home": 1.40, "away": 1.10},
    "ger.1": {"home": 1.65, "away": 1.35}, "ita.1": {"home": 1.45, "away": 1.15},
    "fra.1": {"home": 1.42, "away": 1.12}, "uefa.champions": {"home": 1.58, "away": 1.28}
}

SOCCER_CN = {
    "Manchester City": "曼城", "Arsenal": "兵工廠", "Liverpool": "利物浦", "Chelsea": "切爾西",
    "Tottenham Hotspur": "熱刺", "Tottenham": "熱刺", "Manchester United": "曼聯",
    "Newcastle United": "紐卡索聯", "Newcastle": "紐卡索聯", "Aston Villa": "阿斯頓維拉",
    "Brighton & Hove Albion": "布萊頓", "Brighton": "布萊頓", "West Ham United": "西漢姆聯", "West Ham": "西漢姆聯",
    "Fulham": "富勒姆", "Wolverhampton Wanderers": "狼隊", "Wolves": "狼隊", "Everton": "艾佛頓",
    "Brentford": "布倫特福德", "Crystal Palace": "水晶宮", "Bournemouth": "伯恩茅斯",
    "Nottingham Forest": "諾丁漢森林", "Leicester City": "萊斯特城", "Leicester": "萊斯特城",
    "Ipswich Town": "葉士域治", "Ipswich": "葉士域治", "Southampton": "南安普敦",
    "Hull City": "赫爾城", "Hull": "赫爾城", "Sunderland": "桑德蘭", "Coventry City": "科芬特里城",
    "Coventry": "科芬特里城", "Leeds United": "里茲聯", "Leeds": "里茲聯",
    "Real Madrid": "皇家馬德里", "Barcelona": "巴塞隆納", "Atlético Madrid": "馬德里競技", "Atletico Madrid": "馬德里競技",
    "Girona": "赫羅納", "Athletic Club": "畢爾包競技", "Athletic": "畢爾包競技", "Real Sociedad": "皇家社會",
    "Real Betis": "皇家貝提斯", "Villarreal": "比利亞雷亞爾", "Sevilla": "塞維亞", "Valencia": "瓦倫西亞",
    "Osasuna": "奧薩蘇納", "Celta Vigo": "塞爾塔", "Celta de Vigo": "塞爾塔", "Celta": "塞爾塔",
    "Mallorca": "馬約卡", "Rayo Vallecano": "巴列卡諾", "Las Palmas": "拉斯帕爾馬斯", "Getafe": "赫塔菲",
    "Alavés": "阿拉維斯", "Alaves": "阿拉維斯", "Espanyol": "西班牙人", "Leganés": "萊加內斯",
    "Leganes": "萊加內斯", "Real Valladolid": "瓦拉多利德", "Valladolid": "瓦拉多利德",
    "Bayern Munich": "拜仁慕尼黑", "Bayer Leverkusen": "勒沃庫森", "Borussia Dortmund": "多特蒙德",
    "RB Leipzig": "RB萊比錫", "Stuttgart": "斯圖加特", "Eintracht Frankfurt": "法蘭克福", "Freiburg": "弗萊堡",
    "Wolfsburg": "狼堡", "Mainz": "梅因斯", "Augsburg": "奧格斯堡", "Werder Bremen": "雲達不萊梅",
    "Inter": "國際米蘭", "Internazionale": "國際米蘭", "Inter Milan": "國際米蘭", "Atalanta": "亞特蘭大",
    "Juventus": "尤文圖斯", "Milan": "AC米蘭", "AC Milan": "AC米蘭", "Roma": "羅馬", "Lazio": "拉齊奧",
    "Napoli": "拿坡里", "Bologna": "波隆那", "Fiorentina": "佛倫提那", "Torino": "都靈",
    "Paris Saint-Germain": "巴黎聖日耳曼", "Monaco": "摩納哥", "Lille": "里爾", "Marseille": "馬賽",
    "Lyon": "里昂", "Nice": "尼斯", "Lens": "朗斯", "Brest": "布雷斯特", "Rennes": "雷恩"
}

SOCCER_INPLAY_DROPDOWN = {f"【足球】{v} ({k})": k for k, v in SOCCER_CN.items() if k in BASE_SOCCER_ELO}

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_clubelo_cached(date_str: str):
    elo_db = BASE_SOCCER_ELO.copy()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for url in [f"http://api.clubelo.com/{date_str}", "http://api.clubelo.com/today"]:
        try:
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200 and "Elo" in res.text:
                df = pd.read_csv(io.StringIO(res.text))
                club_col = next((c for c in df.columns if str(c).strip().lower() in ['club', 'team']), None)
                elo_col = next((c for c in df.columns if str(c).strip().lower() == 'elo'), None)
                if club_col and elo_col:
                    for _, row in df.iterrows():
                        elo_db[str(row[club_col]).strip()] = float(row[elo_col])
                    break
        except Exception:
            continue
    return elo_db

def fetch_soccer_matches_live(date_str: str):
    target_dt = datetime.strptime(date_str, "%Y-%m-%d")
    dates_to_query = [(target_dt - timedelta(days=1)).strftime("%Y%m%d"), target_dt.strftime("%Y%m%d"), (target_dt + timedelta(days=1)).strftime("%Y%m%d")]
    all_matches = {}
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "application/json, text/plain, */*", "Referer": "https://www.espn.com/"})
    
    for league_name, league_slug in SOCCER_LEAGUES.items():
        seen_ids = set()
        raw_events = []
        for host in ["https://site.web.api.espn.com", "https://site.api.espn.com"]:
            try:
                r = session.get(f"{host}/apis/site/v2/sports/soccer/{league_slug}/scoreboard?limit=100", timeout=4)
                if r.status_code == 200:
                    for ev in r.json().get("events", []):
                        eid = ev.get("id")
                        if eid and eid not in seen_ids:
                            seen_ids.add(eid)
                            raw_events.append(ev)
            except Exception:
                pass
            for d in dates_to_query:
                try:
                    r = session.get(f"{host}/apis/site/v2/sports/soccer/{league_slug}/scoreboard?dates={d}&limit=100", timeout=4)
                    if r.status_code == 200:
                        for ev in r.json().get("events", []):
                            eid = ev.get("id")
                            if eid and eid not in seen_ids:
                                seen_ids.add(eid)
                                raw_events.append(ev)
                except Exception:
                    pass
            if raw_events:
                break

        matches = []
        for event in raw_events:
            ev_date_raw = event.get("date", "")
            if not ev_date_raw:
                continue
            try:
                dt_utc = datetime.fromisoformat(ev_date_raw.replace("Z", "+00:00"))
                dt_tw = dt_utc.astimezone(timezone(timedelta(hours=8)))
                event_date_tw = dt_tw.strftime("%Y-%m-%d")
            except Exception:
                event_date_tw = ev_date_raw[:10]

            if event_date_tw != date_str:
                continue

            comp = event.get("competitions", [{}])[0]
            status_obj = comp.get("status", {}).get("type", {})
            api_state = status_obj.get("state", "pre")
            is_completed = status_obj.get("completed", False) or api_state == "post"
            
            h_team, a_team = "TBD", "TBD"
            h_score, a_score = None, None
            for c in comp.get("competitors", []):
                t_obj = c.get("team", {})
                t = t_obj.get("name") or t_obj.get("displayName") or t_obj.get("shortDisplayName", "TBD")
                if c.get("homeAway") == "home":
                    h_team = t
                    if is_completed or api_state in ['in', 'post']: h_score = c.get("score")
                else:
                    a_team = t
                    if is_completed or api_state in ['in', 'post']: a_score = c.get("score")
                    
            act_str = f"{h_score}:{a_score}" if h_score is not None else "未完賽"
            api_ou = None
            odds_list = comp.get("odds", [])
            if odds_list:
                try:
                    raw_ou = odds_list[0].get("overUnder", None)
                    if raw_ou is not None and float(raw_ou) > 0:
                        api_ou = float(raw_ou)
                except Exception:
                    pass
            
            final_ou_line = sync_odds("soccer", date_str, h_team, a_team, api_state, api_ou)
            matches.append({"home": h_team, "away": a_team, "score": act_str, "league": league_slug, "ou_line": final_ou_line})
            
        if matches:
            all_matches[league_name] = matches
    return all_matches

def generate_soccer_report(date_str: str):
    elo_db = fetch_clubelo_cached(date_str)
    all_matches = fetch_soccer_matches_live(date_str)
    tot = sum(len(m) for m in all_matches.values())
    if tot == 0:
        return 0, len(elo_db), ""
    
    html_blocks = []
    for l_name, matches in all_matches.items():
        rows = []
        for m in matches:
            h_cn = SOCCER_CN.get(m["home"], m["home"])
            a_cn = SOCCER_CN.get(m["away"], m["away"])
            h_elo = elo_db.get(m["home"], 1650.0)
            a_elo = elo_db.get(m["away"], 1650.0)
            diff = h_elo - a_elo
            bg = SOCCER_GOALS.get(m["league"], {"home": 1.50, "away": 1.20})
            lh = max(0.4, bg["home"] * (1.0 + diff / 550.0) * 1.15)
            la = max(0.3, bg["away"] * (1.0 - diff / 550.0))
            
            hg = np.random.poisson(lh, 10000)
            ag = np.random.poisson(la, 10000)
            hw_p = np.mean(hg > ag)
            dr_p = np.mean(hg == ag)
            aw_p = np.mean(hg < ag)
            
            live_ou = m.get("ou_line")
            if not live_ou:
                exp_tot = lh + la
                live_ou = 3.5 if exp_tot >= 3.6 else (3.0 if exp_tot >= 3.1 else (2.0 if exp_tot <= 2.2 else 2.5))
                force_update_fallback("soccer", date_str, m["home"], m["away"], live_ou)
                
            ov_p = np.mean((hg + ag) > live_ou)
            un_p = np.mean((hg + ag) < live_ou)
            btts_p = np.mean((hg > 0) & (ag > 0))
            
            max_1x2 = max(hw_p, dr_p, aw_p)
            if max_1x2 == hw_p:
                p_1x2, target_1x2 = f"{h_cn} 主勝<br>({hw_p*100:.1f}%)", "HOME"
            elif max_1x2 == aw_p:
                p_1x2, target_1x2 = f"{a_cn} 客勝<br>({aw_p*100:.1f}%)", "AWAY"
            else:
                p_1x2, target_1x2 = f"平局<br>({dr_p*100:.1f}%)", "DRAW"

            g_diff = hg - ag 
            if hw_p >= aw_p:
                h_cov_1 = np.mean(g_diff > 1)
                if hw_p >= 0.58 and h_cov_1 >= 0.42:
                    spread_p, spread_target = f"{h_cn} 讓-1<br>({h_cov_1*100:.1f}%)", "HOME_M1"
                elif hw_p >= 0.50:
                    spread_p, spread_target = f"{h_cn} 讓-0.5<br>({hw_p*100:.1f}%)", "HOME_M05"
                else:
                    spread_p, spread_target = f"{a_cn} 受+0.5<br>({np.mean(g_diff <= 0)*100:.1f}%)", "AWAY_P05"
            else:
                a_cov_1 = np.mean(g_diff < -1)
                if aw_p >= 0.58 and a_cov_1 >= 0.42:
                    spread_p, spread_target = f"{a_cn} 讓-1<br>({a_cov_1*100:.1f}%)", "AWAY_M1"
                elif aw_p >= 0.50:
                    spread_p, spread_target = f"{a_cn} 讓-0.5<br>({aw_p*100:.1f}%)", "AWAY_M05"
                else:
                    spread_p, spread_target = f"{h_cn} 受+0.5<br>({np.mean(g_diff >= 0)*100:.1f}%)", "HOME_P05"

            p_ou, model_ou_target = (f"大 {live_ou}<br>({ov_p*100:.1f}%)", "OVER") if ov_p >= un_p else (f"小 {live_ou}<br>({un_p*100:.1f}%)", "UNDER")
            p_btts = f"是<br>({btts_p*100:.1f}%)" if btts_p >= 0.5 else f"否<br>({(1-btts_p)*100:.1f}%)"
            
            score_counts = pd.Series(list(zip(hg, ag))).value_counts().head(1)
            pred_score_str = f"{score_counts.index[0][0]} : {score_counts.index[0][1]}" if not score_counts.empty else "1 : 1"

            cell_base = "padding: 8px 4px; border: 1px solid #cbd5e1; text-align: center; vertical-align: middle; white-space: normal; line-height: 1.3; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; word-break: break-word;"
            ml_style = f"{cell_base} color: #0f172a; font-weight: 600;"
            spread_style = f"{cell_base} color: #0f172a; font-weight: 600;"
            ou_style = f"{cell_base} color: #0f172a; font-weight: 600;"
            btts_style = f"{cell_base} color: #0f172a; font-weight: 600;"
            score_style = f"{cell_base} color: #0284c7; font-weight: 700;"

            if m["score"] != "未完賽" and ":" in m["score"]:
                try:
                    h_act, a_act = map(int, m["score"].split(":"))
                    act_res = "HOME" if h_act > a_act else ("AWAY" if h_act < a_act else "DRAW")
                    act_diff = h_act - a_act
                    act_tot = h_act + a_act
                    
                    ml_style += "background-color: #dcfce7; color: #15803d;" if target_1x2 == act_res else "background-color: #fee2e2; color: #b91c1c;"
                    
                    if spread_target == "HOME_M1":
                        spread_style += "background-color: #dcfce7; color: #15803d;" if act_diff > 1 else ("background-color: #fef9c3; color: #854d0e;" if act_diff == 1 else "background-color: #fee2e2; color: #b91c1c;")
                    elif spread_target == "HOME_M05":
                        spread_style += "background-color: #dcfce7; color: #15803d;" if act_diff > 0 else "background-color: #fee2e2; color: #b91c1c;"
                    elif spread_target == "AWAY_P05":
                        spread_style += "background-color: #dcfce7; color: #15803d;" if act_diff <= 0 else "background-color: #fee2e2; color: #b91c1c;"
                    elif spread_target == "AWAY_M1":
                        spread_style += "background-color: #dcfce7; color: #15803d;" if act_diff < -1 else ("background-color: #fef9c3; color: #854d0e;" if act_diff == -1 else "background-color: #fee2e2; color: #b91c1c;")
                    elif spread_target == "AWAY_M05":
                        spread_style += "background-color: #dcfce7; color: #15803d;" if act_diff < 0 else "background-color: #fee2e2; color: #b91c1c;"
                    elif spread_target == "HOME_P05":
                        spread_style += "background-color: #dcfce7; color: #15803d;" if act_diff >= 0 else "background-color: #fee2e2; color: #b91c1c;"

                    if act_tot == live_ou:
                        ou_style += "background-color: #fef9c3; color: #854d0e;" 
                    elif (act_tot > live_ou and model_ou_target == "OVER") or (act_tot < live_ou and model_ou_target == "UNDER"):
                        ou_style += "background-color: #dcfce7; color: #15803d;" 
                    else:
                        ou_style += "background-color: #fee2e2; color: #b91c1c;" 
                    
                    btts_style += "background-color: #dcfce7; color: #15803d;" if (h_act > 0 and a_act > 0) == (btts_p >= 0.5) else "background-color: #fee2e2; color: #b91c1c;"
                    
                    # 嚴格正比位置比對：預測「主進球 : 客進球」必須與真實「主比分 : 客比分」完全相符
                    pred_h_g, pred_a_g = map(int, pred_score_str.split(":"))
                    score_style += "background-color: #dcfce7; color: #15803d;" if (pred_h_g == h_act and pred_a_g == a_act) else "background-color: #fee2e2; color: #b91c1c;"
                except Exception:
                    pass
            
            row_html = f'''<tr>
                <td style="{cell_base} font-weight: bold; font-size: 15px; color: #0f172a;">{h_cn}<br><span style="font-size:12px; color:#64748b;">vs</span><br>{a_cn}</td>
                <td style="{cell_base} font-size: 13.5px; color: #334155;">{int(h_elo)}<br>vs {int(a_elo)}</td>
                <td style="{cell_base} color: #e11d48; font-weight: bold; font-size: 14.5px;">{lh:.2f} : {la:.2f}</td>
                <td style="{cell_base} font-weight: bold; font-size: 14px; color: #0f172a;">{m["score"]}</td>
                <td style="{score_style}">預測 {pred_score_str}</td>
                <td style="{ml_style} font-size: 14px;">{p_1x2}</td>
                <td style="{spread_style} font-size: 14px;">{spread_p}</td>
                <td style="{ou_style} font-size: 14px;">{p_ou}</td>
                <td style="{btts_style} font-size: 13.5px;">{p_btts}</td>
            </tr>'''
            rows.append(row_html)
            
        t_block = f'''
        <div style="margin-bottom: 22px; width: 100%; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif;">
            <div style="background: linear-gradient(90deg, #0f172a, #334155); color: #ffffff; padding: 9px 14px; border-radius: 6px 6px 0 0; font-size: 14px; font-weight: bold; display: flex; align-items: center;">
                {l_name}
            </div>
            <div style="overflow-x: auto; -webkit-overflow-scrolling: touch; border: 1px solid #cbd5e1; border-top: none; border-radius: 0 0 6px 6px;">
                <table style="width: 100%; min-width: 900px; table-layout: fixed; border-collapse: collapse; font-size: 14px; background-color: #ffffff;">
                    <colgroup>
                        <col style="width: 18%;">
                        <col style="width: 9%;">
                        <col style="width: 10%;">
                        <col style="width: 8%;">
                        <col style="width: 11%;">
                        <col style="width: 12%;">
                        <col style="width: 12%;">
                        <col style="width: 11%;">
                        <col style="width: 9%;">
                    </colgroup>
                    <thead>
                        <tr style="background-color: #f1f5f9; color: #0f172a; font-weight: 700; height: 38px;">
                            <th style="padding: 6px 4px; border: 1px solid #cbd5e1; text-align: center; vertical-align: middle;">對戰組合</th>
                            <th style="padding: 6px 4px; border: 1px solid #cbd5e1; text-align: center; vertical-align: middle;">ClubElo</th>
                            <th style="padding: 6px 4px; border: 1px solid #cbd5e1; text-align: center; vertical-align: middle;">預估 xG</th>
                            <th style="padding: 6px 4px; border: 1px solid #cbd5e1; text-align: center; vertical-align: middle;">真實比分</th>
                            <th style="padding: 6px 4px; border: 1px solid #cbd5e1; text-align: center; vertical-align: middle;">正比推薦</th>
                            <th style="padding: 6px 4px; border: 1px solid #cbd5e1; text-align: center; vertical-align: middle;">獨贏推薦</th>
                            <th style="padding: 6px 4px; border: 1px solid #cbd5e1; text-align: center; vertical-align: middle;">讓球推薦</th>
                            <th style="padding: 6px 4px; border: 1px solid #cbd5e1; text-align: center; vertical-align: middle;">大小推薦</th>
                            <th style="padding: 6px 4px; border: 1px solid #cbd5e1; text-align: center; vertical-align: middle;">雙進</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(rows)}
                    </tbody>
                </table>
            </div>
        </div>
        '''
        html_blocks.append(t_block)
    return tot, len(elo_db), "".join(html_blocks)

class AutomatedMLBQuantSystem:
    def __init__(self, simulations: int = 10000):
        self.simulations = simulations
        self.fip_constant = 3.15  
        self.park_factors = {
            "Colorado Rockies": 1.14, "Cincinnati Reds": 1.12, "Boston Red Sox": 1.08, 
            "Texas Rangers": 1.05, "Kansas City Royals": 1.04, "Atlanta Braves": 1.03,
            "Chicago White Sox": 1.03, "Los Angeles Dodgers": 1.02, "Philadelphia Phillies": 1.02,
            "Miami Marlins": 1.01, "Arizona Diamondbacks": 1.01, "Baltimore Orioles": 1.00,
            "Chicago Cubs": 1.00, "Houston Astros": 1.00, "New York Yankees": 1.00,
            "Washington Nationals": 0.99, "Los Angeles Angels": 0.99, "Milwaukee Brewers": 0.99,
            "Toronto Blue Jays": 0.99, "Minnesota Twins": 0.98, "Pittsburgh Pirates": 0.98,
            "San Francisco Giants": 0.98, "Tampa Bay Rays": 0.97, "Detroit Tigers": 0.97,
            "Cleveland Guardians": 0.97, "New York Mets": 0.96, "St. Louis Cardinals": 0.96,
            "San Diego Padres": 0.95, "Oakland Athletics": 0.94, "Athletics": 0.94, "Seattle Mariners": 0.91
        }
        self.umpire_factors = {
            "Lance Barksdale": 1.06, "CB Bucknor": 1.05, "Rob Drake": 1.05, "Laz Diaz": 1.04,
            "Brian O'Nora": 1.04, "Mark Ripperger": 1.03, "Dan Iassogna": 1.03,
            "Pat Hoberg": 0.94, "Doug Eddings": 0.94, "John Libka": 0.95, "Bill Miller": 0.95,
            "Dan Bellino": 0.96, "Gabe Morales": 0.96, "Jordan Baker": 0.97
        }
        self.dome_stadiums = [
            "Tampa Bay Rays", "Toronto Blue Jays", "Miami Marlins", 
            "Houston Astros", "Texas Rangers", "Arizona Diamondbacks", 
            "Milwaukee Brewers", "Seattle Mariners"
        ]
        self.team_cities = {
            "New York Yankees": "Bronx", "New York Mets": "Queens", "Los Angeles Dodgers": "Los Angeles",
            "Los Angeles Angels": "Anaheim", "Chicago Cubs": "Chicago", "Chicago White Sox": "Chicago",
            "Boston Red Sox": "Boston", "Baltimore Orioles": "Baltimore", "Atlanta Braves": "Atlanta",
            "Philadelphia Phillies": "Philadelphia", "Washington Nationals": "Washington", 
            "Cincinnati Reds": "Cincinnati", "Colorado Rockies": "Denver", "San Diego Padres": "San Diego",
            "San Francisco Giants": "San Francisco", "Detroit Tigers": "Detroit", "Kansas City Royals": "Kansas City",
            "Minnesota Twins": "Minneapolis", "Cleveland Guardians": "Cleveland", "Pittsburgh Pirates": "Pittsburgh",
            "St. Louis Cardinals": "St. Louis", "Oakland Athletics": "Oakland", "Athletics": "Oakland"
        }
        self.team_cn_names = {
            "New York Yankees": "洋基", "Baltimore Orioles": "金鶯", "Boston Red Sox": "紅襪",
            "Tampa Bay Rays": "光芒", "Toronto Blue Jays": "藍鳥", "Chicago White Sox": "白襪",
            "Cleveland Guardians": "守護者", "Detroit Tigers": "老虎", "Kansas City Royals": "皇家",
            "Minnesota Twins": "雙城", "Houston Astros": "太空人", "Los Angeles Angels": "天使",
            "Oakland Athletics": "運動家", "Athletics": "運動家", "Seattle Mariners": "水手",
            "Texas Rangers": "遊騎兵", "Atlanta Braves": "勇士", "Miami Marlins": "馬林魚",
            "New York Mets": "大都會", "Philadelphia Phillies": "費城人", "Washington Nationals": "國民",
            "Chicago Cubs": "小熊", "Cincinnati Reds": "紅人", "Milwaukee Brewers": "釀酒人",
            "Pittsburgh Pirates": "海盜", "St. Louis Cardinals": "紅雀", "Arizona Diamondbacks": "響尾蛇",
            "Colorado Rockies": "落磯", "Los Angeles Dodgers": "道奇", "San Diego Padres": "教士",
            "San Francisco Giants": "巨人"
        }
        self.lefty_pitchers = [
            "Tarik Skubal", "Chris Sale", "Blake Snell", "Max Fried", "Cole Ragans", "Garrett Crochet", 
            "Framber Valdez", "Ranger Suarez", "Carlos Rodón", "Shota Imanaga", "Cristopher Sánchez", 
            "Andrew Abbott", "Sean Manaea", "Jose Quintana", "Patrick Corbin", "Tyler Anderson", 
            "Yusei Kikuchi", "Martin Perez", "Jesus Luzardo", "Braxton Garrett", "Trevor Rogers",
            "MacKenzie Gore", "Justin Steele", "Nestor Cortes", "Reid Detmers"
        ]
        self.team_ratings = {
            "Los Angeles Dodgers": {"xwOBA_vs_R": 0.345, "xwOBA_vs_L": 0.335, "bp_siera": 3.30, "team_avg_sp": 3.40},
            "New York Yankees": {"xwOBA_vs_R": 0.335, "xwOBA_vs_L": 0.345, "bp_siera": 3.50, "team_avg_sp": 3.65},
            "Baltimore Orioles": {"xwOBA_vs_R": 0.334, "xwOBA_vs_L": 0.328, "bp_siera": 3.60, "team_avg_sp": 3.85},
            "Philadelphia Phillies": {"xwOBA_vs_R": 0.325, "xwOBA_vs_L": 0.342, "bp_siera": 3.45, "team_avg_sp": 3.50},
            "Atlanta Braves": {"xwOBA_vs_R": 0.320, "xwOBA_vs_L": 0.344, "bp_siera": 3.70, "team_avg_sp": 3.60},
            "Houston Astros": {"xwOBA_vs_R": 0.328, "xwOBA_vs_L": 0.315, "bp_siera": 3.65, "team_avg_sp": 3.70},
            "San Diego Padres": {"xwOBA_vs_R": 0.325, "xwOBA_vs_L": 0.318, "bp_siera": 3.55, "team_avg_sp": 3.68},
            "Kansas City Royals": {"xwOBA_vs_R": 0.322, "xwOBA_vs_L": 0.315, "bp_siera": 3.80, "team_avg_sp": 3.80},
            "Milwaukee Brewers": {"xwOBA_vs_R": 0.320, "xwOBA_vs_L": 0.312, "bp_siera": 3.50, "team_avg_sp": 3.85},
            "Minnesota Twins": {"xwOBA_vs_R": 0.318, "xwOBA_vs_L": 0.312, "bp_siera": 3.75, "team_avg_sp": 3.90},
            "Seattle Mariners": {"xwOBA_vs_R": 0.300, "xwOBA_vs_L": 0.315, "bp_siera": 3.40, "team_avg_sp": 3.35},
            "Chicago Cubs": {"xwOBA_vs_R": 0.312, "xwOBA_vs_L": 0.318, "bp_siera": 3.90, "team_avg_sp": 3.95},
            "Tampa Bay Rays": {"xwOBA_vs_R": 0.310, "xwOBA_vs_L": 0.310, "bp_siera": 3.65, "team_avg_sp": 3.85},
            "Cleveland Guardians": {"xwOBA_vs_R": 0.310, "xwOBA_vs_L": 0.302, "bp_siera": 3.25, "team_avg_sp": 3.75},
            "Boston Red Sox": {"xwOBA_vs_R": 0.322, "xwOBA_vs_L": 0.315, "bp_siera": 4.05, "team_avg_sp": 4.10},
            "Toronto Blue Jays": {"xwOBA_vs_R": 0.315, "xwOBA_vs_L": 0.308, "bp_siera": 4.10, "team_avg_sp": 4.15},
            "New York Mets": {"xwOBA_vs_R": 0.325, "xwOBA_vs_L": 0.315, "bp_siera": 3.95, "team_avg_sp": 4.05},
            "San Francisco Giants": {"xwOBA_vs_R": 0.308, "xwOBA_vs_L": 0.302, "bp_siera": 3.85, "team_avg_sp": 3.80},
            "Detroit Tigers": {"xwOBA_vs_R": 0.305, "xwOBA_vs_L": 0.300, "bp_siera": 3.70, "team_avg_sp": 3.90},
            "Texas Rangers": {"xwOBA_vs_R": 0.315, "xwOBA_vs_L": 0.305, "bp_siera": 4.20, "team_avg_sp": 4.25},
            "Arizona Diamondbacks": {"xwOBA_vs_R": 0.328, "xwOBA_vs_L": 0.320, "bp_siera": 4.15, "team_avg_sp": 4.30},
            "Cincinnati Reds": {"xwOBA_vs_R": 0.305, "xwOBA_vs_L": 0.315, "bp_siera": 4.10, "team_avg_sp": 4.20},
            "Washington Nationals": {"xwOBA_vs_R": 0.308, "xwOBA_vs_L": 0.298, "bp_siera": 4.35, "team_avg_sp": 4.45},
            "Pittsburgh Pirates": {"xwOBA_vs_R": 0.300, "xwOBA_vs_L": 0.295, "bp_siera": 4.25, "team_avg_sp": 3.85},
            "St. Louis Cardinals": {"xwOBA_vs_R": 0.310, "xwOBA_vs_L": 0.295, "bp_siera": 4.20, "team_avg_sp": 4.40},
            "Miami Marlins": {"xwOBA_vs_R": 0.295, "xwOBA_vs_L": 0.285, "bp_siera": 4.40, "team_avg_sp": 4.50},
            "Los Angeles Angels": {"xwOBA_vs_R": 0.305, "xwOBA_vs_L": 0.295, "bp_siera": 4.50, "team_avg_sp": 4.65},
            "Oakland Athletics": {"xwOBA_vs_R": 0.302, "xwOBA_vs_L": 0.295, "bp_siera": 4.45, "team_avg_sp": 4.70},
            "Athletics": {"xwOBA_vs_R": 0.302, "xwOBA_vs_L": 0.295, "bp_siera": 4.45, "team_avg_sp": 4.70},
            "Colorado Rockies": {"xwOBA_vs_R": 0.298, "xwOBA_vs_L": 0.285, "bp_siera": 4.85, "team_avg_sp": 5.20},
            "Chicago White Sox": {"xwOBA_vs_R": 0.288, "xwOBA_vs_L": 0.278, "bp_siera": 4.75, "team_avg_sp": 4.95}
        }
        self.re24_matrix = {
            0: {"Empty": 0.48, "1B": 0.86, "2B": 1.10, "3B": 1.35, "12B": 1.44, "13B": 1.70, "23B": 1.96, "Loaded": 2.28},
            1: {"Empty": 0.25, "1B": 0.51, "2B": 0.67, "3B": 0.95, "12B": 0.93, "13B": 1.14, "23B": 1.38, "Loaded": 1.54},
            2: {"Empty": 0.10, "1B": 0.22, "2B": 0.32, "3B": 0.36, "12B": 0.44, "13B": 0.48, "23B": 0.58, "Loaded": 0.75}
        }
        self.fatigue_db = {}

    def generate_negative_binomial_runs(self, expected_runs, size):
        if expected_runs <= 0:
            return np.zeros(size)
        dispersion_factor = 1.35
        variance = expected_runs * dispersion_factor
        p = expected_runs / variance
        n = (expected_runs ** 2) / (variance - expected_runs)
        return np.random.negative_binomial(n, p, size)

    def get_weather_data(self, home_team: str):
        if home_team in self.dome_stadiums:
            return 1.0, "室內巨蛋 (恆溫)"
        city = self.team_cities.get(home_team, "New York")
        try:
            url = f"https://wttr.in/{city}?format=j1"
            res = requests.get(url, timeout=3).json()
            temp_f = int(res['current_condition'][0]['temp_F'])
            wind_mph = int(res['current_condition'][0]['windspeedMiles'])
            return round(1.0 + ((temp_f - 72) * 0.003) + ((wind_mph / 10) * 0.015), 3), f"{temp_f}°F, 風 {wind_mph}mph"
        except Exception:
            return 1.0, "天氣預設 (無數據)"

    def calculate_yesterday_bullpen_fatigue(self, target_date_str: str):
        try:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
            yesterday_str = (target_date - timedelta(days=1)).strftime("%Y-%m-%d")
            res = requests.get(f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={yesterday_str}&hydrate=boxscore", timeout=4).json()
            for d in res.get("dates", []):
                for game in d.get("games", []):
                    for side in ["away", "home"]:
                        team_name = game["teams"][side]["team"]["name"]
                        boxscore = game.get("boxscore", {}).get("teams", {}).get(side, {})
                        total_bp_pitches = sum([boxscore.get("players", {}).get(f"ID{pid}", {}).get("stats", {}).get("pitching", {}).get("numberOfPitches", 0) for pid in boxscore.get("pitchers", [])[1:]])
                        if total_bp_pitches > 75:
                            self.fatigue_db[team_name] = {"multiplier": 1.15, "desc": f"🔴嚴重消耗({total_bp_pitches}球)"}
                        elif total_bp_pitches > 45:
                            self.fatigue_db[team_name] = {"multiplier": 1.05, "desc": f"🟡輕度疲勞({total_bp_pitches}球)"}
                        else:
                            self.fatigue_db[team_name] = {"multiplier": 1.00, "desc": "🟢休息充足"}
        except Exception:
            pass

    def calculate_live_fip(self, pitcher_id: int):
        if not pitcher_id: return None
        try:
            res = requests.get(f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}?hydrate=stats(group=[pitching],type=[season])", timeout=4).json()
            for group in res.get("people", [{}])[0].get("stats", []):
                if group.get("type", {}).get("displayName") == "season":
                    splits = group.get("splits", [])
                    if splits:
                        stat = splits[0].get("stat", {})
                        ip_str = str(stat.get("inningsPitched", "0"))
                        ip = float(ip_str.split(".")[0]) + (float(ip_str.split(".")[1]) / 3.0) if "." in ip_str else float(ip_str)
                        if ip < 15.0: return None 
                        hr, bb, hbp, k = int(stat.get("homeRuns", 0)), int(stat.get("baseOnBalls", 0)), int(stat.get("hitByPitch", 0)), int(stat.get("strikeOuts", 0))
                        return round(((13 * hr) + (3 * (bb + hbp)) - (2 * k)) / ip + self.fip_constant, 2)
        except Exception:
            pass
        return None

    def fetch_metrics(self, team_name: str, pitcher_name: str, pitcher_id: int):
        data = self.team_ratings.get(team_name, {"xwOBA_vs_R": 0.315, "xwOBA_vs_L": 0.315, "bp_siera": 4.00, "team_avg_sp": 4.20}).copy()
        live_fip = self.calculate_live_fip(pitcher_id)
        data["sp_advanced"] = live_fip if live_fip else min(data.get("team_avg_sp", 4.20) + 0.30, 5.50)
        fatigue_info = self.fatigue_db.get(team_name, {"multiplier": 1.00, "desc": "🟢健康(無資料)"})
        data["bp_siera_real"] = data["bp_siera"] * fatigue_info["multiplier"]
        data["fatigue_desc"] = fatigue_info["desc"]
        data["hand"] = "LHP" if any(lp in pitcher_name for lp in self.lefty_pitchers) else "RHP"
        return data

    def fetch_espn_mlb_odds(self, date_str: str):
        target_dt = datetime.strptime(date_str, "%Y-%m-%d")
        dates_to_query = [(target_dt - timedelta(days=1)).strftime("%Y%m%d"), target_dt.strftime("%Y%m%d"), (target_dt + timedelta(days=1)).strftime("%Y%m%d")]
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        odds_dict = {}
        for d_str in dates_to_query:
            try:
                res = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard?dates={d_str}", headers=headers, timeout=5).json()
                for event in res.get("events", []):
                    comp = event.get("competitions", [{}])[0]
                    odds_list = comp.get("odds", [])
                    if odds_list:
                        ou = odds_list[0].get("overUnder", None)
                        if ou:
                            h_name, a_name = "", ""
                            for c in comp.get("competitors", []):
                                if c.get("homeAway") == "home": h_name = c.get("team", {}).get("displayName", "")
                                else: a_name = c.get("team", {}).get("displayName", "")
                            if h_name and a_name: odds_dict[(a_name, h_name)] = float(ou)
            except Exception:
                pass
        return odds_dict

    def get_games_and_scores(self, date_str: str):
        target_dt = datetime.strptime(date_str, "%Y-%m-%d")
        try:
            res = requests.get(f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={(target_dt - timedelta(days=1)).strftime('%Y-%m-%d')}&endDate={(target_dt + timedelta(days=1)).strftime('%Y-%m-%d')}&hydrate=probablePitcher,linescore,officials", timeout=5).json()
        except Exception:
            return pd.DataFrame()
        
        games = []
        for d in res.get("dates", []):
            for game in d.get("games", []):
                game_date_utc = game.get("gameDate", "")
                if game_date_utc:
                    try:
                        if pd.to_datetime(game_date_utc).tz_convert('Asia/Taipei').strftime("%Y-%m-%d") != date_str:
                            continue
                    except Exception:
                        if date_str not in d.get("date", ""):
                            continue
                status = game.get("status", {}).get("abstractGameState", "Preview")
                umpire_name = "未公布 (TBD)"
                for official in game.get("officials", []):
                    if official.get("officialType") == "Home Plate":
                        umpire_name = official.get("official", {}).get("fullName", "未公布")
                        break
                games.append({
                    "away_team": game["teams"]["away"]["team"]["name"], "away_sp": game["teams"]["away"].get("probablePitcher", {}).get("fullName", "TBD"), "away_sp_id": game["teams"]["away"].get("probablePitcher", {}).get("id", None),
                    "home_team": game["teams"]["home"]["team"]["name"], "home_sp": game["teams"]["home"].get("probablePitcher", {}).get("fullName", "TBD"), "home_sp_id": game["teams"]["home"].get("probablePitcher", {}).get("id", None),
                    "status": status, "api_state": "pre" if status in ["Preview", "Pre-Game"] else ("Final" if status == "Final" else "Live"),
                    "away_score": game["teams"]["away"].get("score", None), "home_score": game["teams"]["home"].get("score", None), "umpire": umpire_name
                })
        return pd.DataFrame(games)

    def run_daily_pipeline(self, date_str: str = "2026-08-27"):
        self.calculate_yesterday_bullpen_fatigue(date_str)
        df_games = self.get_games_and_scores(date_str)
        if df_games.empty:
            return 0, ""
            
        espn_odds = self.fetch_espn_mlb_odds(date_str)
        rows_html = []
        for _, row in df_games.iterrows():
            away_data = self.fetch_metrics(row["away_team"], row["away_sp"], row["away_sp_id"])
            home_data = self.fetch_metrics(row["home_team"], row["home_sp"], row["home_sp_id"])
            away_cn = self.team_cn_names.get(row["away_team"], row["away_team"])
            home_cn = self.team_cn_names.get(row["home_team"], row["home_team"])
            
            weather_multiplier, weather_desc = self.get_weather_data(row["home_team"])
            ump_factor = self.umpire_factors.get(row["umpire"], 1.00)
            umpire_display = f"{row['umpire']}<br><span style='color:#e91e63; font-size:12px;'>(係數 {ump_factor:.2f})</span>"
            
            lambda_home = ((away_data["sp_advanced"] / 9.0) * 5.1 + (away_data["bp_siera_real"] / 9.0) * 3.9) * ((home_data["xwOBA_vs_L" if away_data["hand"] == "LHP" else "xwOBA_vs_R"] / 0.315) ** 2.5) * self.park_factors.get(row["home_team"], 1.00) * weather_multiplier * ump_factor * 1.03 * 1.05
            lambda_away = ((home_data["sp_advanced"] / 9.0) * 5.1 + (home_data["bp_siera_real"] / 9.0) * 3.9) * ((away_data["xwOBA_vs_L" if home_data["hand"] == "LHP" else "xwOBA_vs_R"] / 0.315) ** 2.5) * self.park_factors.get(row["home_team"], 1.00) * weather_multiplier * ump_factor * 1.05
            
            api_ou = espn_odds.get((row["away_team"], row["home_team"]), None)
            game_market_line = sync_odds("mlb", date_str, row["home_team"], row["away_team"], row["api_state"], api_ou)
            if not game_market_line:
                game_market_line = max(7.5, min(11.5, round((lambda_away + lambda_home) * 2) / 2.0))
                force_update_fallback("mlb", date_str, row["home_team"], row["away_team"], game_market_line)

            home_runs = self.generate_negative_binomial_runs(lambda_home, self.simulations)
            away_runs = self.generate_negative_binomial_runs(lambda_away, self.simulations)
            
            home_ml_prob = (np.sum(home_runs > away_runs) + np.sum(np.random.binomial(1, 0.54, size=np.sum(home_runs == away_runs)) == 1)) / 10000.0
            run_diff = home_runs - away_runs 
            
            if home_ml_prob >= 0.5:
                spread_pick, spread_target = (f"{home_cn} 讓-1.5<br>({np.mean(run_diff > 1.5)*100:.1f}%)", "HOME_M15") if np.mean(run_diff > 1.5) >= 0.40 else (f"{away_cn} 受+1.5<br>({np.mean(run_diff < 1.5)*100:.1f}%)", "AWAY_P15")
                ml_text, ml_target = f"{home_cn} 主勝<br>({home_ml_prob*100:.1f}%)", "HOME"
            else:
                spread_pick, spread_target = (f"{away_cn} 讓-1.5<br>({np.mean(run_diff < -1.5)*100:.1f}%)", "AWAY_M15") if np.mean(run_diff < -1.5) >= 0.40 else (f"{home_cn} 受+1.5<br>({np.mean(run_diff > -1.5)*100:.1f}%)", "HOME_P15")
                ml_text, ml_target = f"{away_cn} 客勝<br>({(1.0 - home_ml_prob)*100:.1f}%)", "AWAY"

            over_p = np.mean((home_runs + away_runs) > game_market_line)
            model_ou_pick = "大分" if over_p >= np.mean((home_runs + away_runs) < game_market_line) else "小分"
            ou_text = f"{model_ou_pick} {game_market_line}<br>({max(over_p, 1.0 - over_p)*100:.1f}%)"
            
            cell_base = "padding: 8px 4px; border: 1px solid #cbd5e1; text-align: center; vertical-align: middle; white-space: normal; line-height: 1.3; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; word-break: break-word;"
            ml_style = f"{cell_base} color: #0f172a; font-weight: 600;"
            spread_style = f"{cell_base} color: #0f172a; font-weight: 600;"
            ou_style = f"{cell_base} color: #0f172a; font-weight: 600;"
            
            if row["status"] == "Final" and row["home_score"] is not None and row["away_score"] is not None:
                h_act, a_act = int(row["home_score"]), int(row["away_score"])
                actual_score_str = f"{a_act} : {h_act}"
                ml_style += "background-color: #dcfce7; color: #15803d;" if ml_target == ("HOME" if h_act > a_act else "AWAY") else "background-color: #fee2e2; color: #b91c1c;"
                
                if spread_target == "HOME_M15": hit_spread = (h_act - a_act > 1.5)
                elif spread_target == "HOME_P15": hit_spread = (h_act - a_act > -1.5)
                elif spread_target == "AWAY_M15": hit_spread = (a_act - h_act > 1.5)
                else: hit_spread = (a_act - h_act > -1.5)
                
                spread_style += "background-color: #dcfce7; color: #15803d;" if hit_spread else "background-color: #fee2e2; color: #b91c1c;"

                actual_total = h_act + a_act
                if actual_total == game_market_line: ou_style += "background-color: #fef9c3; color: #854d0e;"
                elif (actual_total > game_market_line and model_ou_pick == "大分") or (actual_total < game_market_line and model_ou_pick == "小分"): ou_style += "background-color: #dcfce7; color: #15803d;"
                else: ou_style += "background-color: #fee2e2; color: #b91c1c;"
            else:
                actual_score_str = "未完賽"

            row_html = f'''<tr>
                <td style="{cell_base} font-weight: bold; font-size: 15px; color: #0f172a;"><span style="color:#64748b; font-size:12px;">(客)</span> {away_cn}<br><span style="color:#64748b; font-size:12px;">(主)</span> {home_cn}</td>
                <td style="{cell_base} font-size: 13px; color: #0f172a;">{row['away_sp']}<br><span style='color: #475569; font-size:12px;'>({away_data['hand']} | FIP {away_data['sp_advanced']:.2f})</span><br>vs<br>{row['home_sp']}<br><span style='color: #475569; font-size:12px;'>({home_data['hand']} | FIP {home_data['sp_advanced']:.2f})</span></td>
                <td style="{cell_base}"><span style='font-size:12.5px; color: #0f172a;'>{away_data['fatigue_desc']}</span><br><span style='font-size:12.5px; color: #0f172a;'>{home_data['fatigue_desc']}</span></td>
                <td style="{cell_base} font-size: 13px; color: #0f172a;">{umpire_display}</td>
                <td style="{cell_base} font-size: 13px; color: #0284c7;">{weather_desc}</td>
                <td style="{cell_base} color: #e11d48; font-weight: bold; font-size: 14.5px;">{lambda_away:.2f} : {lambda_home:.2f}</td>
                <td style="{cell_base} font-weight: bold; font-size: 14px; color: #0f172a;">{actual_score_str}</td>
                <td style="{ml_style} font-size: 14px;">{ml_text}</td>
                <td style="{spread_style} font-size: 14px;">{spread_pick}</td>
                <td style="{ou_style} font-size: 14px;">{ou_text}</td>
            </tr>'''
            rows_html.append(row_html)
            
        table_html = f'''
        <div style="margin-bottom: 20px; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif;">
            <div style="background: linear-gradient(90deg, #1e3a8a, #0369a1); color: #ffffff; padding: 9px 14px; border-radius: 6px 6px 0 0; font-size: 14px; font-weight: bold;">
                ⚾ 美國職棒大聯盟 (Major League Baseball)
            </div>
            <div style="overflow-x: auto; -webkit-overflow-scrolling: touch; border: 1px solid #cbd5e1; border-top: none; border-radius: 0 0 6px 6px;">
                <table style="width: 100%; min-width: 950px; table-layout: fixed; border-collapse: collapse; font-size: 14px; background-color: #ffffff;">
                    <colgroup>
                        <col style="width: 12%;"><col style="width: 14%;"><col style="width: 10%;"><col style="width: 10%;"><col style="width: 9%;"><col style="width: 9%;"><col style="width: 8%;"><col style="width: 10%;"><col style="width: 10%;"><col style="width: 8%;">
                    </colgroup>
                    <thead>
                        <tr style="background-color: #f1f5f9; text-align: center; color: #0f172a; font-weight: bold; height: 38px;">
                            <th style="padding: 6px 4px; border: 1px solid #cbd5e1; color: #0f172a; vertical-align: middle;">對戰組合</th>
                            <th style="padding: 6px 4px; border: 1px solid #cbd5e1; color: #0f172a; vertical-align: middle;">先發 & 慣用手</th>
                            <th style="padding: 6px 4px; border: 1px solid #cbd5e1; color: #0f172a; vertical-align: middle;">昨日牛棚狀態</th>
                            <th style="padding: 6px 4px; border: 1px solid #cbd5e1; color: #0f172a; vertical-align: middle;">本壘板主審</th>
                            <th style="padding: 6px 4px; border: 1px solid #cbd5e1; color: #0f172a; vertical-align: middle;">天氣與風向</th>
                            <th style="padding: 6px 4px; border: 1px solid #cbd5e1; color: #0f172a; vertical-align: middle;">預估分(客:主)</th>
                            <th style="padding: 6px 4px; border: 1px solid #cbd5e1; color: #0f172a; vertical-align: middle;">真實比分</th>
                            <th style="padding: 6px 4px; border: 1px solid #cbd5e1; color: #0f172a; vertical-align: middle;">獨贏推薦</th>
                            <th style="padding: 6px 4px; border: 1px solid #cbd5e1; color: #0f172a; vertical-align: middle;">讓分推薦 (±1.5)</th>
                            <th style="padding: 6px 4px; border: 1px solid #cbd5e1; color: #0f172a; vertical-align: middle;">大小推薦 (尾盤)</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(rows_html)}
                    </tbody>
                </table>
            </div>
        </div>
        '''
        return len(df_games), table_html

@st.cache_data(ttl=900, show_spinner=False)
def generate_mlb_report_cached(date_str: str):
    return AutomatedMLBQuantSystem(simulations=10000).run_daily_pipeline(date_str)

def login_view():
    apply_branding_css()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        render_brand_header()
        st.caption("請輸入會員通行碼以解鎖今日數據分析：")
        if auth_msg: st.error(auth_msg)
        passcode = st.text_input("通行碼", type="password", placeholder="請輸入專屬通行碼")
        if st.button("確認進入", use_container_width=True, type="primary"):
            ok, msg = try_authenticate(passcode)
            if ok: st.success(msg); st.rerun()
            else: st.error(msg)

def render_soccer_inplay_calculator():
    st.markdown("#### ⚡ 歐洲頂級足球走地公允定價試算器")
    st.caption("依據五大聯賽各隊即時時間衰減、落後追分強度與少打一人懲罰模型，秒出滾球公允賠率與進場訊號。")
    dropdown_labels = list(SOCCER_INPLAY_DROPDOWN.keys())
    col1, col2 = st.columns(2)
    with col1:
        home_choice = st.selectbox("選擇主隊 (Home Team)", dropdown_labels, index=0)
        home_team = SOCCER_INPLAY_DROPDOWN[home_choice]
        curr_home_score = st.number_input(f"{home_choice} 當前進球數", min_value=0, max_value=15, value=0)
        home_red_cards = st.number_input(f"{home_choice} 紅牌數", min_value=0, max_value=3, value=0)
    with col2:
        away_choice = st.selectbox("選擇客隊 (Away Team)", dropdown_labels, index=1)
        away_team = SOCCER_INPLAY_DROPDOWN[away_choice]
        curr_away_score = st.number_input(f"{away_choice} 當前進球數", min_value=0, max_value=15, value=0)
        away_red_cards = st.number_input(f"{away_choice} 紅牌數", min_value=0, max_value=3, value=0)
        
    c_time, c_line = st.columns(2)
    with c_time: minute = st.slider("當前比賽進行分鐘數 (Minute)", min_value=1, max_value=90, value=65)
    with c_line: live_ou_line = st.number_input("莊家目前開出之走地大小盤口", min_value=0.5, max_value=12.5, value=float(curr_home_score + curr_away_score) + 1.5, step=0.5)

    if st.button("🔥 立即計算走地公允盤口與進場訊號", use_container_width=True, type="primary"):
        diff = BASE_SOCCER_ELO.get(home_team, 1650.0) - BASE_SOCCER_ELO.get(away_team, 1650.0)
        rem_lh = max(0.4, 1.50 * (1.0 + diff / 550.0) * 1.15) * max(0.02, (90 - minute) / 90.0) * (1.20 if (curr_home_score < curr_away_score and minute >= 60) else 1.0) * max(0.3, 1.0 - home_red_cards * 0.35) * (1.0 + away_red_cards * 0.25)
        rem_la = max(0.3, 1.20 * (1.0 - diff / 550.0)) * max(0.02, (90 - minute) / 90.0) * (1.20 if (curr_away_score < curr_home_score and minute >= 60) else 1.0) * max(0.3, 1.0 - away_red_cards * 0.35) * (1.0 + home_red_cards * 0.25)
        
        fin_hg = curr_home_score + np.random.poisson(rem_lh, 10000)
        fin_ag = curr_away_score + np.random.poisson(rem_la, 10000)
        fin_tot = fin_hg + fin_ag
        
        hw_p, dr_p, aw_p = np.mean(fin_hg > fin_ag), np.mean(fin_hg == fin_ag), np.mean(fin_hg < fin_ag)
        over_p, under_p = np.mean(fin_tot > live_ou_line), np.mean(fin_tot < live_ou_line)
        
        st.markdown("---")
        st.markdown("##### 📊 走地公允勝率與理論賠率")
        res1, res2, res3, res4 = st.columns(4)
        with res1: st.metric(label=f"主勝 ({SOCCER_CN.get(home_team, home_team)})", value=f"{hw_p*100:.1f}%", delta=f"公允賠率 {1.0/max(0.01, hw_p):.2f}")
        with res2: st.metric(label="和局 (Draw)", value=f"{dr_p*100:.1f}%", delta=f"公允賠率 {1.0/max(0.01, dr_p):.2f}")
        with res3: st.metric(label=f"客勝 ({SOCCER_CN.get(away_team, away_team)})", value=f"{aw_p*100:.1f}%", delta=f"公允賠率 {1.0/max(0.01, aw_p):.2f}")
        with res4: st.metric(label="剩餘時間期望進球", value=f"{rem_lh + rem_la:.2f} 球", delta=f"主 {rem_lh:.2f} : 客 {rem_la:.2f}")

        st.markdown(f"##### 🎯 走地大小盤口 ({live_ou_line}) 價值判定")
        if over_p >= 0.55: st.success(f"🔥 **【正期望值訊號】推薦進場：大 {live_ou_line}** ｜ 模型勝率：**{over_p*100:.1f}%**")
        elif under_p >= 0.55: st.success(f"🛡️ **【正期望值訊號】推薦進場：小 {live_ou_line}** ｜ 模型勝率：**{under_p*100:.1f}%**")
        else: st.warning(f"⚖️ 盤口膠著：大 ({over_p*100:.1f}%) vs 小 ({under_p*100:.1f}%)")

def render_mlb_inplay_calculator():
    st.markdown("#### ⚡ MLB 美棒即時走地公允定價試算器 (RE24 矩陣)")
    st.caption("結合 FanGraphs 權威 RE24 出局數得分期望矩陣與後援投手負二項分佈，秒算半局得分率與全場勝率。")
    mlb_sys = AutomatedMLBQuantSystem(simulations=10000)
    mlb_dropdown_map = {f"【美棒】{v} ({k.split()[-1]})": k for k, v in mlb_sys.team_cn_names.items()}
    mlb_labels = list(mlb_dropdown_map.keys())
    
    col1, col2 = st.columns(2)
    with col1:
        away_choice = st.selectbox("客隊 (Away Team)", mlb_labels, index=1)
        away_team = mlb_dropdown_map[away_choice]
        curr_away_runs = st.number_input(f"{away_choice} 當前得分", min_value=0, max_value=30, value=2)
    with col2:
        home_choice = st.selectbox("主隊 (Home Team)", mlb_labels, index=0)
        home_team = mlb_dropdown_map[home_choice]
        curr_home_runs = st.number_input(f"{home_choice} 當前得分", min_value=0, max_value=30, value=3)

    c_inn, c_half, c_out = st.columns(3)
    with c_inn: inning = st.slider("當前局數 (Inning)", min_value=1, max_value=12, value=7)
    with c_half: half_inn = st.radio("半局", ["上半局 (Top)", "下半局 (Bottom)"], horizontal=True)
    with c_out: outs = st.selectbox("出局數 (Outs)", [0, 1, 2], index=1)
        
    base_state = st.selectbox("壘包狀態 (Runners on Base)", ["Empty (無人在壘)", "1B (一壘有人)", "2B (二壘有人)", "3B (三壘有人)", "12B (一二壘有人)", "13B (一三壘有人)", "23B (二三壘有人)", "Loaded (滿壘)"], index=4)
    live_ou_line = st.number_input("莊家目前開出之 MLB 走地大小盤口", min_value=1.5, max_value=25.5, value=float(curr_away_runs + curr_home_runs) + 2.5, step=0.5)

    if st.button("🔥 立即計算 MLB 走地勝率與半局得分率", use_container_width=True, type="primary"):
        curr_half_exp = mlb_sys.re24_matrix[outs].get(base_state.split(" ")[0], 0.50)
        is_top = ("Top" in half_inn)
        rem_away_exp = (curr_half_exp + (max(0, 9 - inning) - 1) * 0.45) if is_top else (max(0, 9 - inning) * 0.45)
        rem_home_exp = (max(0, 9 - inning + 1) * 0.45) if is_top else (curr_half_exp + (max(0, 9 - inning + 1) - 1) * 0.45)
        
        away_sim = curr_away_runs + mlb_sys.generate_negative_binomial_runs(rem_away_exp, 10000)
        home_sim = curr_home_runs + mlb_sys.generate_negative_binomial_runs(rem_home_exp, 10000)
        tot_sim = away_sim + home_sim
        
        h_win_p = (np.sum(home_sim > away_sim) + np.sum(np.random.binomial(1, 0.54, size=np.sum(away_sim == home_sim)) == 1)) / 10000.0
        over_p = np.mean(tot_sim > live_ou_line)
        
        st.markdown("---")
        st.markdown("##### ⚾ RE24 當前半局得分預期")
        m1, m2, m3 = st.columns(3)
        with m1: st.metric(label="當前半局期望得分 (RE24)", value=f"{curr_half_exp:.2f} 分")
        with m2: st.metric(label="本半局是否得分機率", value=f"{min(0.95, curr_half_exp / (curr_half_exp + 0.85))*100:.1f}%")
        with m3: st.metric(label="全場即時公允總分", value=f"{np.mean(tot_sim):.2f} 分")

        st.markdown("##### 🏆 即時全場勝率與翻盤公允賠率")
        r1, r2 = st.columns(2)
        with r1: st.metric(label=f"主勝 ({mlb_sys.team_cn_names.get(home_team, home_team)})", value=f"{h_win_p*100:.1f}%", delta=f"公允賠率 {1/max(0.01, h_win_p):.2f}")
        with r2: st.metric(label=f"客勝 ({mlb_sys.team_cn_names.get(away_team, away_team)})", value=f"{(1.0 - h_win_p)*100:.1f}%", delta=f"公允賠率 {1/max(0.01, 1.0 - h_win_p):.2f}")

        st.markdown(f"##### 🎯 走地大小分 ({live_ou_line}) 價值信號")
        if over_p >= 0.54: st.success(f"🔥 **【走地大分價值】推薦：大 {live_ou_line}** ｜ 模型勝率：**{over_p*100:.1f}%**")
        elif (1.0 - over_p) >= 0.54: st.success(f"🛡️ **【走地小分價值】推薦：小 {live_ou_line}** ｜ 模型勝率：**{(1.0 - over_p)*100:.1f}%**")
        else: st.info(f"⚖️ 走地盤口公允：大 ({over_p*100:.1f}%) vs 小 ({(1.0 - over_p)*100:.1f}%)")

def dashboard_view():
    apply_branding_css()
    render_brand_header()

    if st.session_state.get("is_admin", False):
        with st.expander("🛠️ **管理員控制台 (VIP 代碼生成與管理)**", expanded=False):
            st.markdown("##### 📌 一鍵生成 VIP 7 天防轉傳專屬代碼")
            col_in, col_gen = st.columns([3, 1])
            with col_in: new_user = st.text_input("輸入會員暱稱 / LINE 代號", placeholder="例如: TEST1 或 VIP888", label_visibility="collapsed")
            with col_gen:
                if st.button("⚡ 生成專屬通行碼", use_container_width=True, type="primary"):
                    if new_user:
                        token = generate_vip_token(new_user)
                        expire_str = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")
                        if token not in registry:
                            registry[token] = {"user_name": new_user.strip().upper(), "issue_date": date.today().strftime("%Y-%m-%d"), "dev_id": "", "bound_at": "尚未綁定 (發放中)"}
                        st.success(f"✅ 生成成功！有效期至 **{expire_str} 23:59**")
                        st.markdown(f"🔑 **會員通行密碼**： `{token}`")
                        st.code(f"https://soccer-quant-vip.streamlit.app/?vip={token}", language="text")
                    else: st.warning("請先輸入會員暱稱！")
            
            st.markdown("---")
            st.markdown("##### 📱 已發放 / 已綁定 VIP 會員清單總覽")
            if not registry: st.caption("目前尚無發放或綁定的會員代碼。")
            else:
                for tok, info in list(registry.items()):
                    cu, cd, cb = st.columns([2, 3, 1])
                    with cu: st.write(f"👤 **{info['user_name']}**"); st.caption(f"通行碼: `{tok}`")
                    with cd: st.caption(f"發放日: {info['issue_date']} | 狀態: {'🟢已綁定手機' if info.get('dev_id') else '🟡未綁定'}")
                    with cb:
                        if st.button("🔓 一鍵解綁", key=f"unbind_{tok}", use_container_width=True):
                            del registry[tok]; st.success(f"已解綁 {info['user_name']}"); st.rerun()

    elif st.session_state.get("user_name"):
        st.info(f"✨ 歡迎 VIP 會員 **{st.session_state['user_name']}** ｜ 您的通行碼： `{st.session_state.get('current_token', '')}` ｜ 有效期剩餘： **{st.session_state.get('days_left', 7)} 天**")

    col_t, col_l = st.columns([4, 1])
    with col_t: st.header("🏆 職業體育雙向量化定價系統")
    with col_l:
        if st.button("登出", use_container_width=True):
            st.session_state["authenticated"] = False
            st.session_state["is_admin"] = False
            st.session_state["user_name"] = ""
            st.session_state["current_token"] = ""
            if "vip" in st.query_params: del st.query_params["vip"]
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    main_tab1, main_tab2 = st.tabs(["📊 賽前量化定價與回測 (Pre-Match)", "⚡ 即時走地公允定價試算器 (Live In-Play)"])

    with main_tab1:
        st.markdown("<br>", unsafe_allow_html=True)
        c_left, c_mid, c_right = st.columns([1, 2, 1])
        with c_mid:
            selected_sport = st.radio("切換賽前分析賽事", options=["⚽ 歐洲頂級足球", "⚾ MLB 美棒大聯盟 (V9.0)"], horizontal=True, label_visibility="collapsed")
        st.divider()

        if selected_sport == "⚽ 歐洲頂級足球":
            st.subheader("⚽ 歐洲五大聯賽與歐冠量化定價 (尾盤自動鎖死防護)")
            c_d1, c_d2 = st.columns([3, 1])
            with c_d1: selected_date = st.date_input("選擇足球賽事日期", value=date.today(), key="soccer_date")
            with c_d2:
                st.write(""); st.write("")
                if st.button("🔄 強制重抓/清空快取", use_container_width=True): st.cache_data.clear(); st.rerun()
            
            date_str = selected_date.strftime("%Y-%m-%d")
            if st.button("🔍 獲取足球即時量化與回測報告", use_container_width=True, type="primary"):
                with st.spinner(f"正在同步 ClubElo 與 ESPN 盤口數據庫 {date_str}..."):
                    count, elo_len, report_html = generate_soccer_report(date_str)
                    if count == 0: st.warning(f"📅 【{date_str}】 當日歐洲五大聯賽與歐冠「無比賽場次」。")
                    else: st.success(f"✅ 成功同步 {elo_len} 隊歐洲戰力！已量化分析 {count} 場比賽 (尾盤鎖定生效中)！"); st.markdown(report_html, unsafe_allow_html=True)

        else:
            st.subheader("⚾ MLB 美國職棒大聯盟量化定價 (尾盤自動鎖死防護)")
            selected_date = st.date_input("選擇 MLB 賽事日期", value=date.today(), key="mlb_date")
            date_str = selected_date.strftime("%Y-%m-%d")
            if st.button("🔍 獲取 MLB 即時量化與回測報告", use_container_width=True, type="primary"):
                with st.spinner(f"正在抓取先發投手、氣象與開盤數據，啟動 10,000 次量化模擬 {date_str} 賽事..."):
                    count, report_html = generate_mlb_report_cached(date_str)
                    if count == 0: st.warning(f"📅 【{date_str}】 當日 MLB「無比賽場次」。")
                    else: st.success(f"✅ 成功抓取 {count} 場 MLB 比賽，並完成尾盤追蹤與防護鎖死！"); st.markdown(report_html, unsafe_allow_html=True)

    with main_tab2:
        st.markdown("<br>", unsafe_allow_html=True)
        c_left2, c_mid2, c_right2 = st.columns([1, 2, 1])
        with c_mid2:
            live_sport = st.radio("選擇走地試算項目", options=["⚽ 歐洲足球走地定價", "⚾ MLB 美棒走地定價 (RE24)"], horizontal=True, label_visibility="collapsed")
        st.divider()
        if live_sport == "⚽ 歐洲足球走地定價": render_soccer_inplay_calculator()
        else: render_mlb_inplay_calculator()

if not st.session_state["authenticated"]: login_view()
else: dashboard_view()
