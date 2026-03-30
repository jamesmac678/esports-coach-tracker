import os
import json
import requests
import time
from datetime import datetime, timedelta

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")

now = datetime.utcnow()
yesterday = now - timedelta(days=1)
liquipedia_start = yesterday.strftime('%Y-%m-%d %H:%M:%S')

WIKI_MAP = {
    'league-of-legends': ('leagueoflegends', '1v1'),
    'valorant': ('valorant', '1v1'),
    'csgo': ('counterstrike', '1v1'),
    'dota-2': ('dota2', '1v1'),
    'rocket-league': ('rocketleague', '1v1'),
    'crossfire': ('crossfire', '1v1'),
    'pubg': ('pubg', 'ffa'),
    'free-fire': ('freefire', 'ffa'),
    'call-of-duty-warzone': ('callofduty', 'ffa'),
    'trackmania': ('trackmania', 'ffa')
}

def send_discord_message(message):
    data = {"content": message}
    requests.post(DISCORD_WEBHOOK, json=data)

def check_matches():
    with open('clients.json', 'r') as file:
        clients = json.load(file)

    updates = []
    
    for client in clients:
        coach = client['coach_name']
        game = client['game']
        team_slug = client['team_slug']
        
        if game not in WIKI_MAP:
            continue
            
        wiki, match_type = WIKI_MAP[game]
        time.sleep(2) # Safe 2-second brake for Liquipedia limits
        
        # --- 1v1 GAMES (LoL, CSGO, Valorant, etc.) ---
        if match_type == '1v1':
            liquipedia_team = team_slug.replace('-', ' ').title()
            url = f"https://liquipedia.net/{wiki}/api.php"
            params = {
                "action": "cargoquery", "format": "json", "tables": "Match2",
                "fields": "tournament, opponent1, opponent2, winner, result1, result2",
                "where": f"(opponent1='{liquipedia_team}' OR opponent2='{liquipedia_team}') AND dateexact >= '{liquipedia_start}'",
                "limit": "5"
            }
            headers = {"User-Agent": "EsportsCoachTracker/1.0"}
            
            try:
                response = requests.get(url, params=params, headers=headers)
                if response.status_code == 200 and 'cargoquery' in response.json():
                    for item in response.json()['cargoquery']:
                        t_data = item['title']
                        tourney = t_data.get('tournament', 'EWC Qualifier')
                        opp1, opp2 = t_data.get('opponent1', ''), t_data.get('opponent2', '')
                        win_num = t_data.get('winner', '')
                        res1, res2 = t_data.get('result1', '0') or '0', t_data.get('result2', '0') or '0'

                        our_score, their_score = (res1, res2) if opp1 == liquipedia_team else (res2, res1)
                        scoreline = f"({our_score}-{their_score})"

                        if (win_num == '1' and opp1 == liquipedia_team) or (win_num == '2' and opp2 == liquipedia_team):
                            outcome = f"🟢 **WIN {scoreline}**"
                        elif win_num == '0' or not win_num:
                            outcome = f"⚪ **DRAW {scoreline}**"
                        else:
                            outcome = f"🔴 **LOSS {scoreline}**"

                        updates.append(f"{outcome} | **{coach}'s Update ({game.upper()}):** {tourney}")
            except Exception as e:
                print(f"Failed Liquipedia pull for {coach}: {e}")

        # --- FREE FOR ALL GAMES (PUBG, Trackmania, etc.) ---
        elif match_type == 'ffa':
            url = f"https://liquipedia.net/{wiki}/api.php"
            params = {
                "action": "cargoquery", "format": "json", "tables": "Placement",
                "fields": "tournament, placement",
                "where": f"participant='{team_slug}' AND date >= '{liquipedia_start}'",
                "limit": "5"
            }
            headers = {"User-Agent": "EsportsCoachTracker/1.0"}
            
            try:
                response = requests.get(url, params=params, headers=headers)
                if response.status_code == 200 and 'cargoquery' in response.json():
                    for item in response.json()['cargoquery']:
                        t_data = item['title']
                        tourney = t_data.get('tournament', 'EWC Qualifier')
                        place = t_data.get('placement', 'N/A')
                        
                        if place == '1':
                            outcome = f"🟢 **1st Place**"
                        elif place in ['2', '3', '4']:
                            outcome = f"⚪ **{place}th Place**"
                        else:
                            outcome = f"🔴 **{place}th Place**"

                        updates.append(f"{outcome} | **{coach}'s Update ({game.upper()}):** {tourney}")
            except Exception as e:
                print(f"Failed Liquipedia pull for {coach}: {e}")

    if updates:
        send_discord_message("### 📊 Daily Coach Tracker Digest\n" + "\n".join(updates))
    else:
        print("No new matches in the last 24 hours.")

if __name__ == "__main__":
    check_matches()
