import streamlit as st
import numpy as np
import pandas as pd
import requests
import hashlib
import io
import time
from datetime import datetime, date, timedelta

# 1. 頁面設定（手機端自適應）
st.set_page_config(
    page_title="歐洲足球量化定價系統 (VIP)",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ================= 密碼與金鑰設定 =================
MASTER_PASSCODE = "ADMIN999"      # 管理員萬能通行碼
SECRET_SALT = "MySecretKey2026"  # 專屬私鑰 (防偽簽名)

# 2. 全局雲端裝置綁定資料庫 (記憶體級別，極速 0 延遲)
@st.cache_resource
def get_device_registry():
    # 結構: {token: {"dev_id": str, "user_name": str, "issue_date": str, "bound_at": str}}
    return {}

def generate_vip_token(user_name: str, issue_date: date = None) -> str:
    """生成包含會員名稱、日期與私鑰簽名的防偽 Token"""
    if not issue_date:
        issue_date = date.today()
    user_clean = user_name.strip().replace(" ", "").upper()
    date_str = issue_date.strftime("%Y-%m-%d")
    mmdd = issue_date.strftime("%m%d")
    sig = hashlib.sha256(f"{user_clean}_{date_str}_{SECRET_SALT}".encode()).hexdigest()[:4].upper()
    return f"VIP_{user_clean}_{mmdd}_{sig}"

def parse_and_validate_token(token: str):
    """驗證 Token 格式、防偽簽名與 7 天有效期"""
    if token == MASTER_PASSCODE:
        return True, "ADMIN", date.today(), 999
        
    parts = token.split("_")
    if len(parts) != 4 or parts[0] != "VIP":
        return False, None, None, 0
        
    user_name, mmdd, sig = parts[1], parts[2], parts[3]
    curr_year = date.today().year
    try:
        issue_dt = datetime.strptime(f"{curr_year}{mmdd}", "%Y%m%d").date()
    except ValueError:
        return False, None, None, 0
        
    # 驗證防偽簽名
    expected_sig = hashlib.sha256(f"{user_name}_{issue_dt.strftime('%Y-%m-%d')}_{SECRET_SALT}".encode()).hexdigest()[:4].upper()
    if sig != expected_sig:
        return False, None, None, 0
        
    # 計算 7 天剩餘天數
    days_elapsed = (date.today() - issue_dt).days
    if days_elapsed < 0 or days_elapsed >= 8:
        return False, user_name, issue_dt, 0
    else:
        remaining_days = 7 - days_elapsed
        return True, user_name, issue_dt, remaining_days

# ================= 一機一碼核心驗證邏輯 =================
registry = get_device_registry()
url_vip = st.query_params.get("vip", "").strip().upper()
url_dev = st.query_params.get("dev", "").strip()

auth_status = False
auth_msg = ""
is_admin_user = False
user_display_name = ""
days_left = 0

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
    st.session_state["is_admin"] = False
    st.session_state["user_name"] = ""

# 若 URL 帶有 VIP 專屬標籤，進行一機一碼綁定檢驗
if url_vip:
    if url_vip == MASTER_PASSCODE:
        st.session_state["authenticated"] = True
        st.session_state["is_admin"] = True
        st.session_state["user_name"] = "管理員"
    else:
        is_valid, u_name, issue_dt, rem_days = parse_and_validate_token(url_vip)
        if not is_valid:
            auth_msg = "⛔ 通行碼已失效或過期 (有效期限為 7 天)，請聯繫管理員續期！"
        else:
            # 檢查是否已綁定裝置
            if url_vip not in registry:
                # 首次開啟：自動生成唯一裝置識別碼並綁定
                client_dev_id = hashlib.md5(f"{url_vip}_{time.time()}_{np.random.rand()}".encode()).hexdigest()[:12]
                registry[url_vip] = {
                    "dev_id": client_dev_id,
                    "user_name": u_name,
                    "issue_date": issue_dt.strftime("%Y-%m-%d"),
                    "bound_at": datetime.now().strftime("%m-%d %H:%M")
                }
                st.query_params["dev"] = client_dev_id
                st.session_state["authenticated"] = True
                st.session_state["user_name"] = u_name
                st.session_state["days_left"] = rem_days
            else:
                # 再次開啟：比對裝置識別碼
                bound_info = registry[url_vip]
                if url_dev == bound_info["dev_id"]:
                    st.session_state["authenticated"] = True
                    st.session_state["user_name"] = u_name
                    st.session_state["days_left"] = rem_days
                else:
                    auth_msg = "⛔ 訪問被拒：此 VIP 專屬連結已被其他手機綁定！嚴禁轉傳分享。若更換手機請聯繫管理員解綁。"

# ================= 五大聯賽真實基準戰力庫 =================
BASE_ELO_FALLBACK = {
    # 西甲
    "Real Madrid": 2010.0, "Barcelona": 1935.0, "Atletico Madrid": 1865.0, "Girona": 1785.0,
    "Athletic Club": 1805.0, "Athletic": 1805.0, "Real Sociedad": 1775.0, "Villarreal": 1775.0,
    "Real Betis": 1745.0, "Sevilla": 1710.0, "Celta Vigo": 1685.0, "Celta": 1685.0,
    "Osasuna": 1675.0, "Mallorca": 1680.0, "Valencia": 1690.0, "Rayo Vallecano": 1680.0,
    "Las Palmas": 1650.0, "Getafe": 1660.0, "Alaves": 1660.0, "Leganes": 1635.0,
    "Espanyol": 1655.0, "Valladolid": 1625.0,
    # 英超
    "Manchester City": 2020.0, "Arsenal": 1985.0, "Liverpool": 1970.0, "Chelsea": 1835.0,
    "Tottenham": 1815.0, "Newcastle": 1815.0, "Aston Villa": 1835.0, "Manchester United": 1785.0,
    "Brighton": 1775.0, "West Ham": 1725.0, "Fulham": 1715.0, "Bournemouth": 1705.0,
    "Brentford": 1705.0, "Crystal Palace": 1715.0, "Wolves": 1685.0, "Everton": 1690.0,
    "Nottingham Forest": 1685.0, "Leicester": 1675.0, "Southampton": 1635.0, "Ipswich": 1615.0,
    # 德甲
    "Bayern Munich": 1955.0, "Bayer Leverkusen": 1945.0, "Borussia Dortmund": 1875.0,
    "RB Leipzig": 1875.0, "Stuttgart": 1835.0, "Eintracht Frankfurt": 1785.0, "Freiburg": 1745.0,
    "Wolfsburg": 1725.0, "Mainz": 1705.0, "Augsburg": 1705.0, "Werder Bremen": 1715.0,
    # 義甲
    "Inter": 1975.0, "Internazionale": 1975.0, "Atalanta": 1885.0, "Juventus": 1875.0,
    "Milan": 1865.0, "AC Milan": 1865.0, "Roma": 1805.0, "Lazio": 1805.0, "Napoli": 1825.0,
    "Bologna": 1815.0, "Fiorentina": 1775.0, "Torino": 1755.0,
    # 法甲
    "Paris Saint-Germain": 1925.0, "Monaco": 1835.0, "Lille": 1815.0, "Marseille": 1785.0,
    "Lyon": 1775.0, "Nice": 1775.0, "Lens": 1765.0, "Brest": 1765.0, "Rennes": 1755.0
}

LEAGUES_API = {
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 英格蘭超級聯賽 (Premier League)": "eng.1",
    "🇪🇸 西班牙甲級聯賽 (La Liga)": "esp.1",
    "🇩🇪 德國甲級聯賽 (Bundesliga)": "ger.1",
    "🇮🇹 義大利甲級聯賽 (Serie A)": "ita.1",
    "🇫🇷 法國甲級聯賽 (Ligue 1)": "fra.1",
    "🏆 歐洲冠軍聯賽 (UEFA Champions League)": "uefa.champions"
}

LEAGUE_GOALS = {
    "eng.1": {"home": 1.55, "away": 1.25},
    "esp.1": {"home": 1.40, "away": 1.10},
    "ger.1": {"home": 1.65, "away": 1.35},
    "ita.1": {"home": 1.45, "away": 1.15},
    "fra.1": {"home": 1.42, "away": 1.12},
    "uefa.champions": {"home": 1.58, "away": 1.28}
}

TEAM_CN_NAMES = {
    # 英超
    "Manchester City": "曼城", "Arsenal": "兵工廠", "Liverpool": "利物浦",
    "Chelsea": "切爾西", "Tottenham Hotspur": "熱刺", "Tottenham": "熱刺", 
    "Manchester United": "曼聯", "Newcastle United": "紐卡索聯", "Newcastle": "紐卡索聯", 
    "Aston Villa": "阿斯頓維拉", "Brighton & Hove Albion": "布萊頓", "Brighton": "布萊頓",
    "West Ham United": "西漢姆聯", "West Ham": "西漢姆聯", "Fulham": "富勒姆", 
    "Wolverhampton Wanderers": "狼隊", "Wolves": "狼隊", "Everton": "艾佛頓", 
    "Brentford": "布倫特福德", "Crystal Palace": "水晶宮", "AFC Bournemouth": "伯恩茅斯",
    "Bournemouth": "伯恩茅斯", "Nottingham Forest": "諾丁漢森林", "Leicester City": "萊斯特城", 
    "Ipswich Town": "伊普斯維奇", "Southampton": "南安普敦",
    # 西甲
    "Real Madrid": "皇家馬德里", "Barcelona": "巴塞隆納", "Atlético Madrid": "馬德里競技",
    "Atletico Madrid": "馬德里競技", "Girona": "赫羅納", "Athletic Club": "畢爾包競技", 
    "Real Sociedad": "皇家社會", "Real Betis": "皇家貝提斯", "Villarreal": "比利亞雷亞爾", 
    "Sevilla": "塞維亞", "Valencia": "瓦倫西亞", "Osasuna": "奧薩蘇納", "Celta Vigo": "塞爾塔",
    "Celta de Vigo": "塞爾塔", "Mallorca": "馬約卡", "Rayo Vallecano": "巴列卡諾", "Las Palmas": "拉斯帕爾馬斯", 
    "Getafe": "赫塔菲", "Alavés": "阿拉維斯", "Alaves": "阿拉維斯", "Espanyol": "西班牙人", "Leganés": "萊加內斯",
    "Leganes": "萊加內斯", "Real Valladolid": "瓦拉多利德", "Valladolid": "瓦拉多利德",
    # 德甲
    "Bayern Munich": "拜仁慕尼黑", "Bayer Leverkusen": "勒沃庫森", "Borussia Dortmund": "多特蒙德",
    "RB Leipzig": "RB萊比錫", "Eintracht Frankfurt": "法蘭克福", "VfB Stuttgart": "斯圖加特",
    "Stuttgart": "斯圖加特", "Borussia Mönchengladbach": "門興", "Wolfsburg": "狼堡",
    "SC Freiburg": "弗萊堡", "Freiburg": "弗萊堡", "FC Augsburg": "奧格斯堡", "Mainz": "美因茲",
    "Werder Bremen": "不萊梅", "Union Berlin": "柏林聯盟", "Heidenheim": "海登海姆",
    "St. Pauli": "聖保利", "Holstein Kiel": "基爾",
    # 義甲
    "Internazionale": "國際米蘭", "Inter Milan": "國際米蘭", "AC Milan": "AC米蘭", 
    "Juventus": "尤文圖斯", "Napoli": "拿坡里", "AS Roma": "羅馬", "Roma": "羅馬",
    "Lazio": "拉齊歐", "Atalanta": "亞特蘭大", "Fiorentina": "佛倫提那", "Bologna": "波隆那",
    "Torino": "杜林", "Udinese": "烏迪內斯", "Genoa": "熱那亞", "Parma": "帕爾馬",
    "Como": "科莫", "Cagliari": "卡利亞里", "Verona": "維羅納", "Empoli": "恩波利",
    "Monza": "蒙札", "Venezia": "威尼斯",
    # 法甲
    "Paris Saint-Germain": "巴黎聖日耳曼", "Monaco": "摩納哥", "Marseille": "馬賽",
    "Lille": "里爾", "Lyon": "里昂", "Nice": "尼斯", "Lens": "朗斯", "Rennes": "雷恩",
    "Reims": "漢斯", "Brest": "布雷斯特", "Strasbourg": "史特拉斯堡", "Toulouse": "土魯斯",
    "Auxerre": "歐塞爾", "Angers": "昂熱", "Saint-Étienne": "聖艾蒂安", "Nantes": "南特",
    "Le Havre": "勒阿弗爾", "Montpellier": "蒙彼利埃"
}

# ================= 快取連線引擎 =================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_clubelo_cached(date_str: str):
    elo_db = BASE_ELO_FALLBACK.copy()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    urls = [f"http://api.clubelo.com/{date_str}", "http://api.clubelo.com/today"]
    for url in urls:
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
def fetch_all_matches_cached(date_str: str):
    date_formatted = date_str.replace("-", "")
    all_league_matches = {}
    session = requests.Session()
    
    for league_name, league_slug in LEAGUES_API.items():
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_slug}/scoreboard?dates={date_formatted}"
        matches = []
        try:
            res = session.get(url, timeout=3).json()
            for event in res.get("events", []):
                comp = event.get("competitions", [{}])[0]
                status_type = comp.get("status", {}).get("type", {})
                is_completed = status_type.get("completed", False)
                
                home_team, away_team = "TBD", "TBD"
                home_score, away_score = None, None
                
                for competitor in comp.get("competitors", []):
                    t_name = competitor.get("team", {}).get("name", "")
                    if competitor.get("homeAway") == "home":
                        home_team = t_name
                        if is_completed: home_score = competitor.get("score")
                    else:
                        away_team = t_name
                        if is_completed: away_score = competitor.get("score")
                            
                actual_score_str = f"{home_score}:{away_score}" if is_completed and home_score is not None else "未完賽"
                matches.append({
                    "home_team": home_team,
                    "away_team": away_team,
                    "actual_score": actual_score_str,
                    "league_slug": league_slug
                })
        except Exception:
            pass
        if matches:
            all_league_matches[league_name] = matches
    return all_league_matches

def get_team_elo(team_name: str, elo_db: dict) -> float:
    clean = team_name.replace("FC", "").replace("CF", "").replace("RC", "").replace("CA", "").strip()
    if team_name in elo_db: return elo_db[team_name]
    if clean in elo_db: return elo_db[clean]
    
    aliases = {
        "Athletic Club": "Athletic", "Atlético Madrid": "Atleti", "Atletico Madrid": "Atleti",
        "Celta Vigo": "Celta", "Celta de Vigo": "Celta", "Real Betis": "Betis",
        "Real Sociedad": "Sociedad", "Espanyol": "Espanol", "Alavés": "Alaves",
        "Leganés": "Leganes", "Paris Saint-Germain": "PSG", "Inter Milan": "Inter",
        "AC Milan": "Milan", "Bayern Munich": "Bayern", "Bayer Leverkusen": "Leverkusen",
        "Borussia Dortmund": "Dortmund", "RB Leipzig": "Leipzig", "Manchester City": "Man City",
        "Manchester United": "Man United", "Newcastle United": "Newcastle", "Tottenham Hotspur": "Tottenham"
    }
    if team_name in aliases and aliases[team_name] in elo_db: return elo_db[aliases[team_name]]
    if clean in aliases and aliases[clean] in elo_db: return elo_db[aliases[clean]]

    for k, v in elo_db.items():
        if clean.lower() == k.lower() or (len(clean) >= 4 and clean.lower() in k.lower()) or (len(k) >= 4 and k.lower() in clean.lower()):
            return v
    return 1650.0

def simulate_match(home_team: str, away_team: str, actual_score: str, league_slug: str, elo_db: dict, simulations: int = 10000, market_total: float = 2.5):
    home_cn = TEAM_CN_NAMES.get(home_team, home_team)
    away_cn = TEAM_CN_NAMES.get(away_team, away_team)
    
    home_elo = get_team_elo(home_team, elo_db)
    away_elo = get_team_elo(away_team, elo_db)
    elo_diff = home_elo - away_elo
    
    base_goals = LEAGUE_GOALS.get(league_slug, {"home": 1.50, "away": 1.20})
    home_strength_mult = 1.0 + (elo_diff / 550.0)
    away_strength_mult = 1.0 - (elo_diff / 550.0)
    
    lambda_home = max(0.4, base_goals["home"] * home_strength_mult * 1.15)
    lambda_away = max(0.3, base_goals["away"] * away_strength_mult)
    
    home_goals = np.random.poisson(lambda_home, simulations)
    away_goals = np.random.poisson(lambda_away, simulations)
    
    home_win_prob = np.mean(home_goals > away_goals)
    draw_prob = np.mean(home_goals == away_goals)
    away_win_prob = np.mean(home_goals < away_goals)
    
    goal_diff = home_goals - away_goals
    home_cover_half = np.mean(goal_diff > 0)
    away_cover_half = np.mean(goal_diff <= 0)
    home_cover_one = np.mean(goal_diff > 1)
    
    if home_win_prob >= 0.55:
        spread_pick = f"{home_cn} 讓-1 ({home_cover_one*100:.1f}%)" if home_cover_one >= 0.42 else f"{home_cn} 讓-0.5 ({home_cover_half*100:.1f}%)"
    elif away_win_prob >= 0.48:
        spread_pick = f"{away_cn} 讓-0.5 ({away_win_prob*100:.1f}%)"
    else:
        spread_pick = f"{away_cn} 受+0.5 ({away_cover_half*100:.1f}%)" if away_win_prob > home_win_prob else f"{home_cn} 讓-0.5 ({home_cover_half*100:.1f}%)"

    total_goals = home_goals + away_goals
    over_prob = np.mean(total_goals > market_total)
    under_prob = np.mean(total_goals < market_total)
    btts_prob = np.mean((home_goals > 0) & (away_goals > 0))
    
    max_1x2 = max(home_win_prob, draw_prob, away_win_prob)
    if max_1x2 == home_win_prob:
        pick_1x2, target_1x2 = f"{home_cn} 主勝 ({home_win_prob*100:.1f}%)", "HOME"
    elif max_1x2 == away_win_prob:
        pick_1x2, target_1x2 = f"{away_cn} 客勝 ({away_win_prob*100:.1f}%)", "AWAY"
    else:
        pick_1x2, target_1x2 = f"平局 ({draw_prob*100:.1f}%)", "DRAW"
        
    pick_ou = f"大 {market_total} ({over_prob*100:.1f}%)" if over_prob >= 0.5 else f"小 {market_total} ({under_prob*100:.1f}%)"
    pick_btts = f"是 ({btts_prob*100:.1f}%)" if btts_prob >= 0.5 else f"否 ({(1-btts_prob)*100:.1f}%)"
    
    ml_style = "padding: 6px 4px; border: 1px solid #cbd5e1; text-align: center; color: #0f172a; font-weight: 600;"
    spread_style = "padding: 6px 4px; border: 1px solid #cbd5e1; text-align: center; color: #0f172a; font-weight: 600;"
    ou_style = "padding: 6px 4px; border: 1px solid #cbd5e1; text-align: center; color: #0f172a; font-weight: 600;"

    if actual_score != "未完賽" and ":" in actual_score:
        h_act, a_act = map(int, actual_score.split(":"))
        act_res = "HOME" if h_act > a_act else ("AWAY" if h_act < a_act else "DRAW")
        act_diff = h_act - a_act
        act_tot = h_act + a_act
        
        ml_style += "background-color: #dcfce7; color: #15803d;" if target_1x2 == act_res else "background-color: #fee2e2; color: #b91c1c;"
        
        if "-1" in spread_pick:
            spread_style += "background-color: #dcfce7; color: #15803d;" if act_diff > 1 else ("background-color: #fef9c3; color: #854d0e;" if act_diff == 1 else "background-color: #fee2e2; color: #b91c1c;")
        elif "-0.5" in spread_pick:
            spread_style += "background-color: #dcfce7; color: #15803d;" if act_diff > 0 else "background-color: #fee2e2; color: #b91c1c;"
        else:
            spread_style += "background-color: #dcfce7; color: #15803d;" if act_diff <= 0 else "background-color: #fee2e2; color: #b91c1c;"

        is_over = act_tot > market_total
        model_is_over = over_prob >= 0.5
        ou_style += "background-color: #dcfce7; color: #15803d;" if is_over == model_is_over else "background-color: #fee2e2; color: #b91c1c;"

    elo_display = f"<span style='font-size:11px; color:#475569; font-weight:500;'>{int(home_elo)} vs {int(away_elo)}</span>"
    score_display = f"<span style='color:#e11d48; font-weight:bold; font-size:12px;'>{lambda_home:.2f}:{lambda_away:.2f}</span>"

    return f'<tr><td style="padding: 7px 6px; border: 1px solid #cbd5e1; font-weight: bold; font-size: 12px; color: #0f172a; white-space: nowrap;">{home_cn} vs {away_cn}</td><td style="padding: 6px 3px; border: 1px solid #cbd5e1; text-align: center; white-space: nowrap;">{elo_display}</td><td style="padding: 6px 3px; border: 1px solid #cbd5e1; text-align: center; white-space: nowrap;">{score_display}</td><td style="padding: 6px 3px; border: 1px solid #cbd5e1; text-align: center; font-weight: bold; font-size: 12px; color: #0f172a; white-space: nowrap;">{actual_score}</td><td style="{ml_style}; font-size: 11.5px; white-space: nowrap;">{pick_1x2}</td><td style="{spread_style}; font-size: 11px; white-space: nowrap;">{spread_pick}</td><td style="{ou_style}; font-size: 11.5px; white-space: nowrap;">{pick_ou}</td><td style="padding: 6px 3px; border: 1px solid #cbd5e1; text-align: center; font-size: 11px; color: #334155; white-space: nowrap;">{pick_btts}</td></tr>'

@st.cache_data(ttl=900, show_spinner=False)
def generate_html_report_cached(date_str: str):
    elo_db = fetch_clubelo_cached(date_str)
    all_matches = fetch_all_matches_cached(date_str)
    
    total_matches_count = sum(len(m) for m in all_matches.values())
    if total_matches_count == 0:
        return 0, len(elo_db), ""
        
    html_blocks = []
    for league_name, matches in all_matches.items():
        rows = "".join([simulate_match(m["home_team"], m["away_team"], m["actual_score"], m["league_slug"], elo_db) for m in matches])
        
        table_section = (
            f'<div style="margin-bottom: 20px; width: 100%; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif;">'
            f'<div style="background: linear-gradient(90deg, #0f172a, #334155); color: #ffffff; padding: 8px 12px; border-radius: 6px 6px 0 0; font-size: 13px; font-weight: bold;">{league_name}</div>'
            f'<div style="overflow-x: auto; -webkit-overflow-scrolling: touch; border: 1px solid #cbd5e1; border-top: none; border-radius: 0 0 6px 6px;">'
            f'<table style="width: 100%; min-width: 780px; border-collapse: collapse; font-size: 12px; background-color: #ffffff;">'
            f'<thead><tr style="background-color: #f1f5f9; text-align: center; color: #1e293b; font-weight: bold;">'
            f'<th style="padding: 8px 6px; border: 1px solid #cbd5e1; width: 23%;">對戰組合 (主 vs 客)</th>'
            f'<th style="padding: 8px 3px; border: 1px solid #cbd5e1; width: 12%;">ClubElo</th>'
            f'<th style="padding: 8px 3px; border: 1px solid #cbd5e1; width: 11%;">預估 xG</th>'
            f'<th style="padding: 8px 3px; border: 1px solid #cbd5e1; width: 9%;">比分</th>'
            f'<th style="padding: 8px 4px; border: 1px solid #cbd5e1; width: 17%;">獨贏推薦 (1X2)</th>'
            f'<th style="padding: 8px 4px; border: 1px solid #cbd5e1; width: 14%;">讓球推薦</th>'
            f'<th style="padding: 8px 4px; border: 1px solid #cbd5e1; width: 10%;">大小 (2.5)</th>'
            f'<th style="padding: 8px 3px; border: 1px solid #cbd5e1; width: 7%;">雙進</th>'
            f'</tr></thead><tbody>{rows}</tbody></table></div></div>'
        )
        html_blocks.append(table_section)
        
    return total_matches_count, len(elo_db), "".join(html_blocks)

# ================= 介面視圖 =================
def login_view():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔒 會員專屬量化系統")
        st.caption("請使用管理員發放之專屬 VIP 連結進入，或手動輸入管理員萬能通行碼。")
        
        if auth_msg:
            st.error(auth_msg)
            
        passcode = st.text_input("管理員通行碼", type="password", placeholder="輸入通行碼")
        
        if st.button("確認進入", use_container_width=True, type="primary"):
            clean = passcode.strip().upper()
            if clean == MASTER_PASSCODE:
                st.session_state["authenticated"] = True
                st.session_state["is_admin"] = True
                st.session_state["user_name"] = "管理員"
                st.query_params["vip"] = MASTER_PASSCODE
                st.rerun()
            else:
                st.error("通行碼錯誤！一般會員請直接點擊專屬連結。")

def dashboard_view():
    # 1. 管理員專屬控制台 (會員生成器 + 裝置解綁管理)
    if st.session_state.get("is_admin", False):
        with st.expander("🛠️ **管理員控制台 (一機一碼會員管理)**", expanded=True):
            st.markdown("##### 📌 一鍵生成 VIP 7 天防轉傳專屬連結")
            col_in, col_gen = st.columns([3, 1])
            with col_in:
                new_user = st.text_input("輸入會員暱稱 / LINE 代號", placeholder="例如: VIP888 或 小明", label_visibility="collapsed")
            with col_gen:
                if st.button("⚡ 生成專屬連結", use_container_width=True, type="primary"):
                    if new_user:
                        token = generate_vip_token(new_user)
                        expire_str = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")
                        base_url = "https://soccer-quant-vip.streamlit.app"
                        full_vip_link = f"{base_url}/?vip={token}"
                        st.success(f"✅ 生成成功！有效期至 **{expire_str} 23:59**")
                        st.code(full_vip_link, language="text")
                        st.caption("💡 將上方整串網址私訊發給會員即可。該會員首次點開將自動綁定其手機，轉傳給其他人會立即失效！")
                    else:
                        st.warning("請先輸入會員暱稱！")
            
            # 檢視與解綁管理
            st.markdown("---")
            st.markdown("##### 📱 已綁定裝置管理")
            if not registry:
                st.caption("目前尚無會員綁定裝置。")
            else:
                for tok, info in list(registry.items()):
                    col_u, col_d, col_b = st.columns([2, 3, 1])
                    with col_u:
                        st.write(f"👤 **{info['user_name']}**")
                    with col_d:
                        st.caption(f"綁定時間: {info['bound_at']} | 裝置碼: `{info['dev_id']}`")
                    with col_b:
                        if st.button("🔓 一鍵解綁", key=f"unbind_{tok}", use_container_width=True):
                            del registry[tok]
                            st.success(f"已解綁 {info['user_name']}，會員可使用原連結綁定新手機。")
                            st.rerun()

    # 2. 一般會員頂部歡迎條
    elif st.session_state.get("user_name"):
        rem = st.session_state.get("days_left", 7)
        st.info(f"✨ 歡迎 VIP 會員 **{st.session_state['user_name']}** ｜ 專屬授權已綁定本機 ｜ 有效期剩餘： **{rem} 天**")

    # 3. 頂部導航
    col_title, col_logout = st.columns([4, 1])
    with col_title:
        st.header("⚽ 歐洲頂級聯賽量化定價與回測")
    with col_logout:
        if st.button("登出", use_container_width=True):
            st.session_state["authenticated"] = False
            st.session_state["is_admin"] = False
            st.session_state["user_name"] = ""
            if "vip" in st.query_params: del st.query_params["vip"]
            if "dev" in st.query_params: del st.query_params["dev"]
            st.rerun()

    # 4. 賽事日期選擇與運算
    selected_date = st.date_input("選擇賽事日期", value=date.today())
    date_str = selected_date.strftime("%Y-%m-%d")

    if st.button("🔍 獲取即時量化與回測報告", use_container_width=True, type="primary"):
        with st.spinner(f"正在載入與量化運算 {date_str} 賽事..."):
            total_count, elo_count, report_html = generate_html_report_cached(date_str)
            
            if total_count == 0:
                st.warning(f"📅 【{date_str}】 當日歐洲五大聯賽與歐冠「無比賽場次」。建議選擇週末賽事測試。")
            else:
                st.success(f"✅ 成功同步 {elo_count} 隊歐洲即時戰力！已量化分析 {total_count} 場比賽！")
                st.markdown(report_html, unsafe_allow_html=True)

# ================= 流程路由控制 =================
if not st.session_state["authenticated"]:
    login_view()
else:
    dashboard_view()