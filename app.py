import streamlit as st
import numpy as np
import pandas as pd
import requests
import hashlib
import io
import time
from datetime import datetime, date, timedelta

# 1. 頁面設定（支援手機響應式寬度）
st.set_page_config(
    page_title="VIP 雙運動量化定價系統",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ================= 密碼與金鑰設定 =================
MASTER_PASSCODE = "ADMIN999"      # 管理員萬能通行碼
SECRET_SALT = "MySecretKey2026"  # 專屬私鑰 (防偽簽名)

# 2. 全局雲端裝置綁定資料庫 (0 延遲記憶體快取)
@st.cache_resource
def get_device_registry():
    return {}

def get_client_fingerprint():
    """獲取客戶端裝置指紋 (防止跨裝置轉發)"""
    try:
        ua = st.context.headers.get("User-Agent", "default_ua")
        return hashlib.md5(ua.encode()).hexdigest()[:10]
    except Exception:
        return "device_default"

def generate_vip_token(user_name: str, issue_date: date = None) -> str:
    """生成精簡版通行碼 (格式: 會員名_4碼簽名)"""
    if not issue_date:
        issue_date = date.today()
    user_clean = user_name.strip().replace(" ", "").upper()
    date_str = issue_date.strftime("%Y-%m-%d")
    sig = hashlib.sha256(f"{user_clean}_{date_str}_{SECRET_SALT}".encode()).hexdigest()[:4].upper()
    return f"{user_clean}_{sig}"

def parse_and_validate_token(token: str):
    """智慧滾動驗證：自動比對過去 7 天簽名"""
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
            remaining_days = 7 - i
            return True, user_name, check_date, remaining_days
            
    return False, None, None, 0

# ================= 一機一碼核心驗證邏輯 =================
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
        return False, "⛔ 通行碼無效或已過期，請向管理員領取最新通行碼！"
        
    if clean not in registry:
        registry[clean] = {
            "user_name": u_name,
            "issue_date": issue_dt.strftime("%Y-%m-%d"),
            "dev_id": dev_fp,
            "bound_at": datetime.now().strftime("%m-%d %H:%M")
        }
    else:
        bound_dev = registry[clean].get("dev_id", "")
        if bound_dev and bound_dev != dev_fp and bound_dev != "device_default":
            return False, "⛔ 訪問被拒：此 VIP 代碼已綁定其他手機，嚴禁轉傳！若更換手機請聯繫管理員解綁。"
            
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

# ================= 模組一：歐洲足球量化引擎 =================
BASE_SOCCER_ELO = {
    "Real Madrid": 2010.0, "Barcelona": 1935.0, "Atletico Madrid": 1865.0, "Girona": 1785.0,
    "Athletic Club": 1805.0, "Athletic": 1805.0, "Real Sociedad": 1775.0, "Villarreal": 1775.0,
    "Real Betis": 1745.0, "Sevilla": 1710.0, "Celta Vigo": 1685.0, "Celta": 1685.0,
    "Osasuna": 1675.0, "Mallorca": 1680.0, "Valencia": 1690.0, "Rayo Vallecano": 1680.0,
    "Las Palmas": 1650.0, "Getafe": 1660.0, "Alaves": 1660.0, "Leganes": 1635.0,
    "Espanyol": 1655.0, "Valladolid": 1625.0, "Manchester City": 2020.0, "Arsenal": 1985.0,
    "Liverpool": 1970.0, "Chelsea": 1835.0, "Tottenham": 1815.0, "Newcastle": 1815.0,
    "Aston Villa": 1835.0, "Manchester United": 1785.0, "Brighton": 1775.0, "West Ham": 1725.0,
    "Bayern Munich": 1955.0, "Bayer Leverkusen": 1945.0, "Borussia Dortmund": 1875.0, "RB Leipzig": 1875.0,
    "Inter": 1975.0, "Internazionale": 1975.0, "Atalanta": 1885.0, "Juventus": 1875.0, "Milan": 1865.0,
    "Paris Saint-Germain": 1925.0, "Monaco": 1835.0, "Lille": 1815.0, "Marseille": 1785.0
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
    "Tottenham Hotspur": "熱刺", "Tottenham": "熱刺", "Manchester United": "曼聯", "Newcastle United": "紐卡索聯",
    "Aston Villa": "阿斯頓維拉", "Brighton & Hove Albion": "布萊頓", "Brighton": "布萊頓", "West Ham United": "西漢姆聯",
    "West Ham": "西漢姆聯", "Fulham": "富勒姆", "Wolverhampton Wanderers": "狼隊", "Wolves": "狼隊",
    "Everton": "艾佛頓", "Brentford": "布倫特福德", "Crystal Palace": "水晶宮", "Bournemouth": "伯恩茅斯",
    "Nottingham Forest": "諾丁漢森林", "Leicester City": "萊斯特城", "Ipswich Town": "伊普斯維奇", "Southampton": "南安普敦",
    "Real Madrid": "皇家馬德里", "Barcelona": "巴塞隆納", "Atlético Madrid": "馬德里競技", "Atletico Madrid": "馬德里競技",
    "Girona": "赫羅納", "Athletic Club": "畢爾包競技", "Real Sociedad": "皇家社會", "Real Betis": "皇家貝提斯",
    "Villarreal": "比利亞雷亞爾", "Sevilla": "塞維亞", "Valencia": "瓦倫西亞", "Osasuna": "奧薩蘇納",
    "Celta Vigo": "塞爾塔", "Celta de Vigo": "塞爾塔", "Mallorca": "馬約卡", "Rayo Vallecano": "巴列卡諾",
    "Las Palmas": "拉斯帕爾馬斯", "Getafe": "赫塔菲", "Alavés": "阿拉維斯", "Alaves": "阿拉維斯",
    "Espanyol": "西班牙人", "Leganés": "萊加內斯", "Leganes": "萊加內斯", "Real Valladolid": "瓦拉多利德",
    "Bayern Munich": "拜仁慕尼黑", "Bayer Leverkusen": "勒沃庫森", "Borussia Dortmund": "多特蒙德",
    "RB Leipzig": "RB萊比錫", "Internazionale": "國際米蘭", "Inter Milan": "國際米蘭", "AC Milan": "AC米蘭",
    "Juventus": "尤文圖斯", "Paris Saint-Germain": "巴黎聖日耳曼"
}

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_clubelo_cached(date_str: str):
    elo_db = BASE_SOCCER_ELO.copy()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for url in [f"http://api.clubelo.com/{date_str}", "http://api.clubelo.com/today"]:
        try:
            res = requests.get(url, headers=headers, timeout=4)
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

@st.cache_data(ttl=300, show_spinner=False)
def fetch_soccer_matches_cached(date_str: str):
    date_formatted = date_str.replace("-", "")
    all_matches = {}
    session = requests.Session()
    for league_name, league_slug in SOCCER_LEAGUES.items():
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_slug}/scoreboard?dates={date_formatted}"
        matches = []
        try:
            res = session.get(url, timeout=3).json()
            for event in res.get("events", []):
                comp = event.get("competitions", [{}])[0]
                is_completed = comp.get("status", {}).get("type", {}).get("completed", False)
                h_team, a_team = "TBD", "TBD"
                h_score, a_score = None, None
                for c in comp.get("competitors", []):
                    t = c.get("team", {}).get("name", "")
                    if c.get("homeAway") == "home":
                        h_team = t
                        if is_completed: h_score = c.get("score")
                    else:
                        a_team = t
                        if is_completed: a_score = c.get("score")
                act_str = f"{h_score}:{a_score}" if is_completed and h_score is not None else "未完賽"
                matches.append({"home": h_team, "away": a_team, "score": act_str, "league": league_slug})
        except Exception:
            pass
        if matches:
            all_matches[league_name] = matches
    return all_matches

@st.cache_data(ttl=900, show_spinner=False)
def generate_soccer_report_cached(date_str: str):
    elo_db = fetch_clubelo_cached(date_str)
    all_matches = fetch_soccer_matches_cached(date_str)
    tot = sum(len(m) for m in all_matches.values())
    if tot == 0: return 0, len(elo_db), ""
    
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
            ov_p = np.mean((hg + ag) > 2.5)
            btts_p = np.mean((hg > 0) & (ag > 0))
            
            g_diff = hg - ag
            h_cov_1 = np.mean(g_diff > 1)
            h_cov_half = np.mean(g_diff > 0)
            a_cov_half = np.mean(g_diff <= 0)
            
            if hw_p >= 0.55:
                spread_p = f"{h_cn} 讓-1 ({h_cov_1*100:.1f}%)" if h_cov_1 >= 0.42 else f"{h_cn} 讓-0.5 ({h_cov_half*100:.1f}%)"
            elif aw_p >= 0.48:
                spread_p = f"{a_cn} 讓-0.5 ({aw_p*100:.1f}%)"
            else:
                spread_p = f"{a_cn} 受+0.5 ({a_cov_half*100:.1f}%)" if aw_p > hw_p else f"{h_cn} 讓-0.5 ({h_cov_half*100:.1f}%)"

            p_1x2 = f"{h_cn} 主勝 ({hw_p*100:.1f}%)" if hw_p >= max(dr_p, aw_p) else (f"{a_cn} 客勝 ({aw_p*100:.1f}%)" if aw_p >= dr_p else f"平局 ({dr_p*100:.1f}%)")
            p_ou = f"大 2.5 ({ov_p*100:.1f}%)" if ov_p >= 0.5 else f"小 2.5 ({(1-ov_p)*100:.1f}%)"
            p_btts = f"是 ({btts_p*100:.1f}%)" if btts_p >= 0.5 else f"否 ({(1-btts_p)*100:.1f}%)"
            
            rows.append(f'<tr><td style="padding: 8px 6px; border: 1px solid #cbd5e1; font-weight: bold; font-size: 12px; color: #0f172a; white-space: nowrap;">{h_cn} vs {a_cn}</td><td style="padding: 6px 3px; border: 1px solid #cbd5e1; text-align: center; font-size: 11px; color: #334155; white-space: nowrap;">{int(h_elo)} vs {int(a_elo)}</td><td style="padding: 6px 3px; border: 1px solid #cbd5e1; text-align: center; color: #e11d48; font-weight: bold; font-size: 12px; white-space: nowrap;">{lh:.2f}:{la:.2f}</td><td style="padding: 6px 3px; border: 1px solid #cbd5e1; text-align: center; font-weight: bold; font-size: 12px; color: #0f172a; white-space: nowrap;">{m["score"]}</td><td style="padding: 6px 4px; border: 1px solid #cbd5e1; text-align: center; font-weight: 600; font-size: 11.5px; color: #0f172a; white-space: nowrap;">{p_1x2}</td><td style="padding: 6px 4px; border: 1px solid #cbd5e1; text-align: center; font-weight: 600; font-size: 11px; color: #0f172a; white-space: nowrap;">{spread_p}</td><td style="padding: 6px 4px; border: 1px solid #cbd5e1; text-align: center; font-weight: 600; font-size: 11.5px; color: #0f172a; white-space: nowrap;">{p_ou}</td><td style="padding: 6px 3px; border: 1px solid #cbd5e1; text-align: center; font-size: 11px; color: #334155; white-space: nowrap;">{p_btts}</td></tr>')
            
        t_block = f'<div style="margin-bottom: 22px; width: 100%; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif;"><div style="background: linear-gradient(90deg, #0f172a, #334155); color: #ffffff; padding: 8px 12px; border-radius: 6px 6px 0 0; font-size: 13px; font-weight: bold;">{l_name}</div><div style="overflow-x: auto; -webkit-overflow-scrolling: touch; border: 1px solid #cbd5e1; border-top: none; border-radius: 0 0 6px 6px;"><table style="width: 100%; min-width: 780px; border-collapse: collapse; font-size: 12px; background-color: #ffffff;"><thead><tr style="background-color: #f1f5f9; text-align: center; color: #0f172a; font-weight: bold;"><th style="padding: 8px 6px; border: 1px solid #cbd5e1; color: #0f172a;">對戰組合</th><th style="padding: 8px 3px; border: 1px solid #cbd5e1; color: #0f172a;">ClubElo</th><th style="padding: 8px 3px; border: 1px solid #cbd5e1; color: #0f172a;">預估 xG</th><th style="padding: 8px 3px; border: 1px solid #cbd5e1; color: #0f172a;">真實比分</th><th style="padding: 8px 4px; border: 1px solid #cbd5e1; color: #0f172a;">獨贏推薦</th><th style="padding: 8px 4px; border: 1px solid #cbd5e1; color: #0f172a;">讓球推薦</th><th style="padding: 8px 4px; border: 1px solid #cbd5e1; color: #0f172a;">大小 (2.5)</th><th style="padding: 8px 3px; border: 1px solid #cbd5e1; color: #0f172a;">雙進</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></div>'
        html_blocks.append(t_block)
    return tot, len(elo_db), "".join(html_blocks)

# ================= 模組二：MLB 美棒量化系統 V9.0 (核心引擎) =================
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
            "San Diego Padres": 0.95, "Oakland Athletics": 0.94, "Athletics": 0.94, 
            "Seattle Mariners": 0.91
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
            temp_effect = (temp_f - 72) * 0.003
            wind_effect = (wind_mph / 10) * 0.015 
            multiplier = 1.0 + temp_effect + wind_effect
            desc = f"{temp_f}°F, 風 {wind_mph}mph"
            return round(multiplier, 3), desc
        except Exception:
            return 1.0, "天氣預設 (無數據)"

    def calculate_yesterday_bullpen_fatigue(self, target_date_str: str):
        try:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
            yesterday_str = (target_date - timedelta(days=1)).strftime("%Y-%m-%d")
            url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={yesterday_str}&hydrate=boxscore"
            res = requests.get(url, timeout=4).json()
            for d in res.get("dates", []):
                for game in d.get("games", []):
                    for side in ["away", "home"]:
                        team_name = game["teams"][side]["team"]["name"]
                        boxscore = game.get("boxscore", {}).get("teams", {}).get(side, {})
                        pitchers = boxscore.get("pitchers", [])
                        total_bp_pitches = 0
                        if len(pitchers) > 1:
                            for pid in pitchers[1:]:
                                p_stats = boxscore.get("players", {}).get(f"ID{pid}", {}).get("stats", {}).get("pitching", {})
                                total_bp_pitches += p_stats.get("numberOfPitches", 0)
                        
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
        url = f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}?hydrate=stats(group=[pitching],type=[season])"
        try:
            res = requests.get(url, timeout=4).json()
            stats_groups = res.get("people", [{}])[0].get("stats", [])
            for group in stats_groups:
                if group.get("type", {}).get("displayName") == "season":
                    splits = group.get("splits", [])
                    if splits:
                        stat = splits[0].get("stat", {})
                        ip_str = str(stat.get("inningsPitched", "0"))
                        if "." in ip_str:
                            full, part = ip_str.split(".")
                            ip = float(full) + (float(part) / 3.0)
                        else:
                            ip = float(ip_str)
                            
                        if ip < 15.0: return None 
                        hr, bb, hbp, k = int(stat.get("homeRuns", 0)), int(stat.get("baseOnBalls", 0)), int(stat.get("hitByPitch", 0)), int(stat.get("strikeOuts", 0))
                        fip = ((13 * hr) + (3 * (bb + hbp)) - (2 * k)) / ip + self.fip_constant
                        return round(fip, 2)
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

    def get_games_and_scores(self, date_str: str):
        url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}&hydrate=probablePitcher,linescore,officials"
        try:
            res = requests.get(url, timeout=5).json()
        except Exception:
            return pd.DataFrame()
        
        games = []
        for d in res.get("dates", []):
            for game in d.get("games", []):
                status = game.get("status", {}).get("abstractGameState", "Preview")
                away_score = game["teams"]["away"].get("score", None)
                home_score = game["teams"]["home"].get("score", None)
                
                away_team = game["teams"]["away"]["team"]["name"]
                home_team = game["teams"]["home"]["team"]["name"]
                
                away_sp_info = game["teams"]["away"].get("probablePitcher", {})
                home_sp_info = game["teams"]["home"].get("probablePitcher", {})
                
                umpire_name = "未公布 (TBD)"
                officials = game.get("officials", [])
                for official in officials:
                    if official.get("officialType") == "Home Plate":
                        umpire_name = official.get("official", {}).get("fullName", "未公布")
                        break
                        
                games.append({
                    "away_team": away_team, "away_sp": away_sp_info.get("fullName", "TBD"), "away_sp_id": away_sp_info.get("id", None),
                    "home_team": home_team, "home_sp": home_sp_info.get("fullName", "TBD"), "home_sp_id": home_sp_info.get("id", None),
                    "status": status, "away_score": away_score, "home_score": home_score, "umpire": umpire_name
                })
        return pd.DataFrame(games)

    def run_daily_pipeline(self, date_str: str = "2026-08-27", market_line: float = 8.5):
        self.calculate_yesterday_bullpen_fatigue(date_str)
        df_games = self.get_games_and_scores(date_str)
        if df_games.empty:
            return 0, ""
            
        rows_html = []
        for _, row in df_games.iterrows():
            away_data = self.fetch_metrics(row["away_team"], row["away_sp"], row["away_sp_id"])
            home_data = self.fetch_metrics(row["home_team"], row["home_sp"], row["home_sp_id"])
            
            away_cn = self.team_cn_names.get(row["away_team"], row["away_team"])
            home_cn = self.team_cn_names.get(row["home_team"], row["home_team"])
            
            hfa = 1.03 
            unearned_run_multiplier = 1.05 
            park_factor = self.park_factors.get(row["home_team"], 1.00) 
            weather_multiplier, weather_desc = self.get_weather_data(row["home_team"])
            
            umpire = row["umpire"]
            ump_factor = self.umpire_factors.get(umpire, 1.00)
            umpire_display = f"{umpire}<br><span style='color:#e91e63; font-size:10px;'>(係數 {ump_factor:.2f})</span>"
            
            target_xwOBA_home = home_data["xwOBA_vs_L"] if away_data["hand"] == "LHP" else home_data["xwOBA_vs_R"]
            target_xwOBA_away = away_data["xwOBA_vs_L"] if home_data["hand"] == "LHP" else away_data["xwOBA_vs_R"]
            
            firepower_home = (target_xwOBA_home / 0.315) ** 2.5
            firepower_away = (target_xwOBA_away / 0.315) ** 2.5
            
            pitching_base_away = (away_data["sp_advanced"] / 9.0) * 5.1 + (away_data["bp_siera_real"] / 9.0) * 3.9
            pitching_base_home = (home_data["sp_advanced"] / 9.0) * 5.1 + (home_data["bp_siera_real"] / 9.0) * 3.9
            
            lambda_home = pitching_base_away * firepower_home * park_factor * weather_multiplier * ump_factor * hfa * unearned_run_multiplier
            lambda_away = pitching_base_home * firepower_away * park_factor * weather_multiplier * ump_factor * unearned_run_multiplier
            
            home_runs = self.generate_negative_binomial_runs(lambda_home, self.simulations)
            away_runs = self.generate_negative_binomial_runs(lambda_away, self.simulations)
            
            ties = (home_runs == away_runs)
            tie_home_wins = np.random.binomial(1, 0.54, size=np.sum(ties))
            total_home_wins = np.sum(home_runs > away_runs) + np.sum(tie_home_wins == 1)
            home_ml_prob = total_home_wins / self.simulations
            away_ml_prob = 1.0 - home_ml_prob
            
            run_diff = home_runs - away_runs 
            home_cover_minus1 = np.mean(run_diff > 1)      
            away_cover_plus1 = np.mean(run_diff < 1)       
            away_cover_minus1 = np.mean(run_diff < -1)     
            home_cover_plus1 = np.mean(run_diff > -1)      
            
            if home_ml_prob >= 0.5:
                if home_cover_minus1 >= 0.45:
                    spread_pick = f"{home_cn} 讓-1 ({home_cover_minus1*100:.1f}%)"
                    spread_target = "HOME_COVER"
                else:
                    spread_pick = f"{away_cn} 受+1 ({away_cover_plus1*100:.1f}%)"
                    spread_target = "AWAY_COVER"
            else:
                if away_cover_minus1 >= 0.45:
                    spread_pick = f"{away_cn} 讓-1 ({away_cover_minus1*100:.1f}%)"
                    spread_target = "AWAY_COVER_FAV"
                else:
                    spread_pick = f"{home_cn} 受+1 ({home_cover_plus1*100:.1f}%)"
                    spread_target = "HOME_COVER_DOG"

            total_runs = home_runs + away_runs
            over_prob = np.mean(total_runs > market_line)
            under_prob = np.mean(total_runs < market_line)
            
            model_ml_pick_name = home_cn if home_ml_prob >= 0.5 else away_cn
            model_ou_pick = "大分" if over_prob >= 0.5 else "小分"
            
            ml_text = f"{model_ml_pick_name} ({max(home_ml_prob, away_ml_prob)*100:.1f}%)"
            ou_text = f"{model_ou_pick} ({max(over_prob, under_prob)*100:.1f}%)"
            
            ml_style = "padding: 6px 4px; border: 1px solid #cbd5e1; text-align: center; color: #0f172a; font-weight: 600;"
            spread_style = "padding: 6px 4px; border: 1px solid #cbd5e1; text-align: center; color: #0f172a; font-weight: 600;"
            ou_style = "padding: 6px 4px; border: 1px solid #cbd5e1; text-align: center; color: #0f172a; font-weight: 600;"
            
            is_final = (row["status"] == "Final" and row["home_score"] is not None)
            if is_final:
                actual_score_str = f"{row['away_score']} : {row['home_score']}"
                actual_ml_winner_name = home_cn if row["home_score"] > row["away_score"] else away_cn
                actual_total = row["home_score"] + row["away_score"]
                actual_diff = row["home_score"] - row["away_score"]
                
                ml_style += "background-color: #dcfce7; color: #15803d;" if model_ml_pick_name == actual_ml_winner_name else "background-color: #fee2e2; color: #b91c1c;"
                    
                if spread_target == "HOME_COVER":
                    spread_style += "background-color: #dcfce7; color: #15803d;" if actual_diff > 1 else ("background-color: #fef9c3; color: #854d0e;" if actual_diff == 1 else "background-color: #fee2e2; color: #b91c1c;")
                elif spread_target == "AWAY_COVER":
                    spread_style += "background-color: #dcfce7; color: #15803d;" if actual_diff <= 0 else ("background-color: #fef9c3; color: #854d0e;" if actual_diff == 1 else "background-color: #fee2e2; color: #b91c1c;")
                elif spread_target == "AWAY_COVER_FAV":
                    spread_style += "background-color: #dcfce7; color: #15803d;" if actual_diff < -1 else ("background-color: #fef9c3; color: #854d0e;" if actual_diff == -1 else "background-color: #fee2e2; color: #b91c1c;")
                elif spread_target == "HOME_COVER_DOG":
                    spread_style += "background-color: #dcfce7; color: #15803d;" if actual_diff >= 0 else ("background-color: #fef9c3; color: #854d0e;" if actual_diff == -1 else "background-color: #fee2e2; color: #b91c1c;")
                    
                actual_ou = "大分" if actual_total > market_line else ("小分" if actual_total < market_line else "走盤")
                if model_ou_pick == actual_ou:
                    ou_style += "background-color: #dcfce7; color: #15803d;"
                elif actual_ou == "走盤":
                    ou_style += "background-color: #fef9c3; color: #854d0e;"
                else:
                    ou_style += "background-color: #fee2e2; color: #b91c1c;"
            else:
                actual_score_str = "未完賽"

            sp_text_away = f"{row['away_sp']}<br><span style='color: #475569; font-size:11px;'>({away_data['hand']} | FIP {away_data['sp_advanced']:.2f})</span>" if row['away_sp'] != "TBD" else "TBD"
            sp_text_home = f"{row['home_sp']}<br><span style='color: #475569; font-size:11px;'>({home_data['hand']} | FIP {home_data['sp_advanced']:.2f})</span>" if row['home_sp'] != "TBD" else "TBD"

            bp_text_away = f"<span style='font-size:10.5px; color: #0f172a;'>{away_data['fatigue_desc']}</span>"
            bp_text_home = f"<span style='font-size:10.5px; color: #0f172a;'>{home_data['fatigue_desc']}</span>"

            row_html = f'<tr><td style="padding: 8px 6px; border: 1px solid #cbd5e1; font-weight: bold; font-size: 12px; color: #0f172a; white-space: nowrap;">{away_cn} @ {home_cn}</td><td style="padding: 6px 3px; border: 1px solid #cbd5e1; font-size: 11.5px; text-align: center; color: #0f172a; white-space: nowrap;">{sp_text_away}<br>vs<br>{sp_text_home}</td><td style="padding: 6px 3px; border: 1px solid #cbd5e1; text-align: center; white-space: nowrap;">{bp_text_away}<br>{bp_text_home}</td><td style="padding: 6px 3px; border: 1px solid #cbd5e1; text-align: center; font-size: 11px; color: #0f172a; white-space: nowrap;">{umpire_display}</td><td style="padding: 6px 3px; border: 1px solid #cbd5e1; text-align: center; font-size: 11px; color: #0284c7; white-space: nowrap;">{weather_desc}</td><td style="padding: 6px 3px; border: 1px solid #cbd5e1; text-align: center; color: #e11d48; font-weight: bold; font-size: 12.5px; white-space: nowrap;">{lambda_away:.2f} : {lambda_home:.2f}</td><td style="padding: 6px 3px; border: 1px solid #cbd5e1; text-align: center; font-weight: bold; font-size: 12px; color: #0f172a; white-space: nowrap;">{actual_score_str}</td><td style="{ml_style}; font-size: 11.5px; white-space: nowrap;">{ml_text}</td><td style="{spread_style}; font-size: 11px; white-space: nowrap;">{spread_pick}</td><td style="{ou_style}; font-size: 11.5px; white-space: nowrap;">{ou_text}</td></tr>'
            rows_html.append(row_html)
            
        table_html = f'<div style="margin-bottom: 20px; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif;"><div style="background: linear-gradient(90deg, #1e3a8a, #0369a1); color: #ffffff; padding: 8px 12px; border-radius: 6px 6px 0 0; font-size: 13px; font-weight: bold;">⚾ 美國職棒大聯盟 (Major League Baseball)</div><div style="overflow-x: auto; -webkit-overflow-scrolling: touch; border: 1px solid #cbd5e1; border-top: none; border-radius: 0 0 6px 6px;"><table style="width: 100%; min-width: 900px; border-collapse: collapse; font-size: 12px; background-color: #ffffff;"><thead><tr style="background-color: #f1f5f9; text-align: center; color: #0f172a; font-weight: bold;"><th style="padding: 10px 8px; border: 1px solid #cbd5e1; color: #0f172a;">對戰組合</th><th style="padding: 10px 8px; border: 1px solid #cbd5e1; color: #0f172a;">先發 & 慣用手</th><th style="padding: 10px 8px; border: 1px solid #cbd5e1; color: #0f172a;">昨日牛棚狀態</th><th style="padding: 10px 8px; border: 1px solid #cbd5e1; color: #0f172a;">本壘板主審</th><th style="padding: 10px 8px; border: 1px solid #cbd5e1; color: #0f172a;">天氣與風向</th><th style="padding: 10px 8px; border: 1px solid #cbd5e1; color: #0f172a;">預估分(客:主)</th><th style="padding: 10px 8px; border: 1px solid #cbd5e1; color: #0f172a;">真實比分</th><th style="padding: 10px 8px; border: 1px solid #cbd5e1; color: #0f172a;">獨贏推薦</th><th style="padding: 10px 8px; border: 1px solid #cbd5e1; color: #0f172a;">讓分推薦 (±1)</th><th style="padding: 10px 8px; border: 1px solid #cbd5e1; color: #0f172a;">大小推薦 ({market_line})</th></tr></thead><tbody>{"".join(rows_html)}</tbody></table></div></div>'
        return len(df_games), table_html

@st.cache_data(ttl=900, show_spinner=False)
def generate_mlb_report_cached(date_str: str, market_line: float = 8.5):
    mlb_sys = AutomatedMLBQuantSystem(simulations=10000)
    return mlb_sys.run_daily_pipeline(date_str, market_line)

# ================= 介面視圖 =================
def login_view():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔒 雙運動 VIP 量化系統")
        st.caption("請輸入會員通行碼以解鎖賽事分析：")
        
        if auth_msg:
            st.error(auth_msg)
            
        passcode = st.text_input("通行碼", type="password", placeholder="請輸入專屬通行碼")
        
        if st.button("確認進入", use_container_width=True, type="primary"):
            ok, msg = try_authenticate(passcode)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

def dashboard_view():
    # 1. 管理員專屬控制台
    if st.session_state.get("is_admin", False):
        with st.expander("🛠️ **管理員控制台 (VIP 代碼生成與管理)**", expanded=True):
            st.markdown("##### 📌 一鍵生成 VIP 7 天防轉傳專屬代碼")
            col_in, col_gen = st.columns([3, 1])
            with col_in:
                new_user = st.text_input("輸入會員暱稱 / LINE 代號", placeholder="例如: TEST1 或 VIP888", label_visibility="collapsed")
            with col_gen:
                if st.button("⚡ 生成專屬通行碼", use_container_width=True, type="primary"):
                    if new_user:
                        token = generate_vip_token(new_user)
                        expire_str = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")
                        base_url = "https://soccer-quant-vip.streamlit.app"
                        full_url = f"{base_url}/?vip={token}"
                        
                        if token not in registry:
                            registry[token] = {
                                "user_name": new_user.strip().upper(),
                                "issue_date": date.today().strftime("%Y-%m-%d"),
                                "dev_id": "",
                                "bound_at": "尚未綁定 (發放中)"
                            }
                        
                        st.success(f"✅ 生成成功！有效期至 **{expire_str} 23:59**")
                        st.markdown(f"🔑 **會員通行密碼**： `{token}`")
                        st.markdown(f"🔗 **一鍵免密登入連結**：")
                        st.code(full_url, language="text")
                    else:
                        st.warning("請先輸入會員暱稱！")
            
            st.markdown("---")
            st.markdown("##### 📱 已發放 / 已綁定 VIP 會員清單總覽")
            if not registry:
                st.caption("目前尚無發放或綁定的會員代碼。")
            else:
                for tok, info in list(registry.items()):
                    cu, cd, cb = st.columns([2, 3, 1])
                    with cu:
                        st.write(f"👤 **{info['user_name']}**")
                        st.caption(f"通行碼: `{tok}`")
                    with cd:
                        bind_status = "🟢已綁定手機" if info.get("dev_id") else "🟡未綁定 (首次點開將自動鎖定)"
                        st.caption(f"發放日: {info['issue_date']} | 狀態: {bind_status}")
                    with cb:
                        if st.button("🔓 一鍵解綁", key=f"unbind_{tok}", use_container_width=True):
                            del registry[tok]
                            st.success(f"已解綁 {info['user_name']}")
                            st.rerun()

    # 2. 一般會員頂部歡迎條
    elif st.session_state.get("user_name"):
        rem = st.session_state.get("days_left", 7)
        curr_tok = st.session_state.get("current_token", "")
        st.info(f"✨ 歡迎 VIP 會員 **{st.session_state['user_name']}** ｜ 您的通行碼： `{curr_tok}` ｜ 有效期剩餘： **{rem} 天**")

    # 頂部導航
    col_t, col_l = st.columns([4, 1])
    with col_t:
        st.header("🏆 職業體育雙向量化定價系統")
    with col_l:
        if st.button("登出", use_container_width=True):
            st.session_state["authenticated"] = False
            st.session_state["is_admin"] = False
            st.session_state["user_name"] = ""
            st.session_state["current_token"] = ""
            if "vip" in st.query_params: del st.query_params["vip"]
            st.rerun()

    # ================= 畫面中央：運動項目切換區 =================
    st.markdown("<br>", unsafe_allow_html=True)
    c_left, c_mid, c_right = st.columns([1, 2, 1])
    with c_mid:
        selected_sport = st.radio(
            "切換分析賽事",
            options=["⚽ 歐洲頂級足球", "⚾ MLB 美棒大聯盟 (V9.0)"],
            horizontal=True,
            label_visibility="collapsed"
        )

    st.divider()

    # 足球查詢介面
    if selected_sport == "⚽ 歐洲頂級足球":
        st.subheader("⚽ 歐洲五大聯賽與歐冠量化定價")
        selected_date = st.date_input("選擇足球賽事日期", value=date.today(), key="soccer_date")
        date_str = selected_date.strftime("%Y-%m-%d")

        if st.button("🔍 獲取足球即時量化與回測報告", use_container_width=True, type="primary"):
            with st.spinner(f"正在同步 ClubElo 與運算 {date_str} 足球賽事..."):
                count, elo_len, report_html = generate_soccer_report_cached(date_str)
                if count == 0:
                    st.warning(f"📅 【{date_str}】 當日歐洲五大聯賽與歐冠「無比賽場次」。建議選擇週末賽事測試。")
                else:
                    st.success(f"✅ 成功同步 {elo_len} 隊歐洲戰力！已量化分析 {count} 場比賽！")
                    st.markdown(report_html, unsafe_allow_html=True)

    # MLB 查詢介面
    else:
        st.subheader("⚾ MLB 美國職棒大聯盟量化定價 (V9.0 負二項分佈)")
        col_d, col_m = st.columns([2, 1])
        with col_d:
            selected_date = st.date_input("選擇 MLB 賽事日期", value=date.today(), key="mlb_date")
        with col_m:
            market_line = st.number_input("市場基準大小分盤口", min_value=5.0, max_value=15.0, value=8.5, step=0.5)
        
        date_str = selected_date.strftime("%Y-%m-%d")

        if st.button("🔍 獲取 MLB 即時量化與回測報告", use_container_width=True, type="primary"):
            with st.spinner(f"正在抓取先發投手、昨日牛棚、主審與氣象數據，啟動 10,000 次量化模擬 {date_str} 賽事..."):
                count, report_html = generate_mlb_report_cached(date_str, market_line)
                if count == 0:
                    st.warning(f"📅 【{date_str}】 當日 MLB「無比賽場次」。")
                else:
                    st.success(f"✅ 成功抓取 {count} 場 MLB 比賽，完成 10,000 次負二項分佈量化模擬！")
                    st.markdown(report_html, unsafe_allow_html=True)

# ================= 流程路由控制 =================
if not st.session_state["authenticated"]:
    login_view()
else:
    dashboard_view()