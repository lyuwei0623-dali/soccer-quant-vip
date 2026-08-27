import streamlit as st
import numpy as np
import pandas as pd
import requests
import hashlib
import io
from datetime import datetime, date

# 1. 頁面設定（手機端自適應）
st.set_page_config(
    page_title="歐洲足球量化定價系統 (VIP)",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ================= 密碼與金鑰設定 =================
MASTER_PASSCODE = "ADMIN999"      # 管理員萬能通行碼
SECRET_SALT = "MySecretKey2026"  # 專屬私鑰

def get_today_passcode(date_str: str = None) -> str:
    """每日 00:00 自動更換 6 碼動態通行碼"""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    raw_hash = hashlib.sha256(f"{date_str}_{SECRET_SALT}".encode()).hexdigest()
    return raw_hash[:6].upper()

# 2. 手機捷徑防斷線：自動檢查 URL 參數
today_code = get_today_passcode()
url_passcode = st.query_params.get("key", "").upper()

if "authenticated" not in st.session_state:
    if url_passcode in [MASTER_PASSCODE, today_code]:
        st.session_state["authenticated"] = True
        st.session_state["is_admin"] = (url_passcode == MASTER_PASSCODE)
    else:
        st.session_state["authenticated"] = False
        st.session_state["is_admin"] = False

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

# ================= 高效快取連線引擎 =================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_clubelo_cached(date_str: str):
    """快取 ClubElo 即時評分 (1小時自動刷新)"""
    elo_db = BASE_ELO_FALLBACK.copy()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    urls = [
        f"http://api.clubelo.com/{date_str}",
        "http://api.clubelo.com/today"
    ]
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
    """快取賽程抓取 (5分鐘自動刷新)"""
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
    """一鍵快取全天報告 (15分鐘快取，秒開不卡頓)"""
    elo_db = fetch_clubelo_cached(date_str)
    all_matches = fetch_all_matches_cached(date_str)
    
    total_matches_count = sum(len(m) for m in all_matches.values())
    if total_matches_count == 0:
        return 0, len(elo_db), ""
        
    html_blocks = []
    for league_name, matches in all_matches.items():
        rows = "".join([simulate_match(m["home_team"], m["away_team"], m["actual_score"], m["league_slug"], elo_db) for m in matches])
        
        # 手機硬體加速與平滑滑動容器
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
        st.caption("請輸入會員專屬通行碼以解鎖今日數據分析。")
        
        passcode = st.text_input("會員通行碼", type="password", placeholder="請輸入 6 位數每日動態通行碼")
        
        if st.button("確認進入", use_container_width=True, type="primary"):
            input_clean = passcode.strip().upper()
            if input_clean == MASTER_PASSCODE or input_clean == today_code:
                st.session_state["authenticated"] = True
                st.session_state["is_admin"] = (input_clean == MASTER_PASSCODE)
                st.query_params["key"] = input_clean
                st.rerun()
            else:
                st.error("通行碼無效或已過期，請每日向管理員領取最新密碼。")

def dashboard_view():
    if st.session_state.get("is_admin", False):
        today_str = datetime.now().strftime("%Y-%m-%d")
        st.info(f"🔑 **管理員控制台** ｜ 今日 ({today_str}) 發放通行碼： `{get_today_passcode()}`")

    col_title, col_logout = st.columns([4, 1])
    with col_title:
        st.header("⚽ 歐洲頂級聯賽量化定價與回測")
    with col_logout:
        if st.button("登出", use_container_width=True):
            st.session_state["authenticated"] = False
            st.session_state["is_admin"] = False
            if "key" in st.query_params:
                del st.query_params["key"]
            st.rerun()

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