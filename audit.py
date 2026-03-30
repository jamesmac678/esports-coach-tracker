import os
import json
import requests
import time
from datetime import datetime, timedelta

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")

current_week = datetime.utcnow().isocalendar()[1]
if current_week % 2 != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
    print("Odd week detected. Skipping fortnightly audit.")
    exit()

now = datetime.utcnow()
fortnight_ago = now - timedelta(days=14)
liquipedia_start = fortnight_ago.strftime('%Y-%m-%d %H:%M:%S')

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
    print("Preparing to send Discord message...")
    if len(message) > 1990:
        message = message[:1990] + "\n...[List Truncated due to length]"
    data = {"content": message}
    response = requests.post(DISCORD_WEBHOOK, json=data)
    print(f"Discord API Response: {response.status_code}")

def run_audit():
    print("--- Starting Liquipedia Audit ---")
    
    try:
        with open('clients.json', 'r') as file:
            clients = json.load(file)
    except Exception as e:
        print(f"❌ CRITICAL: Could not read clients.json. Error: {e}")
        return

    print(f"Loaded {len(clients)} coaches from clients.json.")

    if len(clients) == 0:
        print("❌ CRITICAL: clients.json is empty. Aborting run.")
        return

    audit_log = []
    
    for client in clients:
        coach = client.get('coach_name', 'Unknown')
        game = client.get('game', '')
        team_slug = client.get('team_slug', '')
        
        if game not in WIKI_MAP:
            print(f"Skipping {coach} - '{game}' is not a valid game in WIKI_MAP.")
            continue
            
        wiki, match_type = WIKI_MAP[game]
        print(f"Checking Liquipedia for {coach} ({game})...")
        time.sleep(2) 
        
        # --- 1v1 GAMES ---
        if match_type == '1v1':
            liquipedia_team = team_slug 
            
            url = f"https://liquipedia.net/{wiki}/api.php"
            params = {
                "action": "cargoquery", "format": "json", "tables": "Match2",
                "fields": "tournament, date, opponent1, opponent2, winner, result1, result2",
                "where": f"(opponent1='{liquipedia_team}' OR opponent2='{liquipedia_team}') AND dateexact >= '{liquipedia_start}'",
                "limit": "20"
            }
            headers = {"User-Agent": "EsportsCoachTracker/1.0"}
            
            try:
                response = requests.get(url, params=params, headers=headers)
                if response.status_code == 200 and 'cargoquery' in response.json():
                    matches = response.json()['cargoquery']
                    if not matches:
                        print(f"  -> No matches found.")
                    for item in matches:
                        t_data = item['title']
                        tourney = t_data.get('tournament', 'EWC Qualifier')
                        date = t_data.get('date', '')[:10]
                        opp1, opp2 = t_data.get('opponent1', ''), t_data.get('opponent2', '')
                        win_num = t_data.get('winner', '')
                        res1, res2 = t_data.get('result1', '0') or '0', t_data.get('result2', '0') or '0'

                        our_score, their_score = (res1, res2) if opp1 == liquipedia_team else (res2, res1)
                        scoreline = f"({our_score}-{their_score})"

                        if (win_num == '1' and opp1 == liquipedia_team) or (win_num == '2' and opp2 == liquipedia_team):
                            outcome = f"🟢 {scoreline}"
                        elif win_num == '0' or not win_num:
                            outcome = f"⚪ {scoreline}"
                        else:
                            outcome = f"🔴 {scoreline}"

                        print(f"  -> Found match: {date} | {tourney}")
                        audit_log.append(f"{outcome} `{date}` | **{coach} ({game.upper()}):** {tourney}")
            except Exception as e:
                print(f"❌ Failed Liquipedia pull for {coach}: {e}")

        # --- FREE FOR ALL GAMES ---
        elif match_type == 'ffa':
            url = f"https://liquipedia.net/{wiki}/api.php"
            params = {
                "action": "cargoquery", "format": "json", "tables": "Placement",
                "fields": "tournament, date, placement",
                "where": f"participant='{team_slug}' AND date >= '{liquipedia_start}'",
                "limit": "20"
            }
            headers = {"User-Agent": "EsportsCoachTracker/1.0"}
            
            try:
                response = requests.get(url, params=params, headers=headers)
                if response.status_code == 200 and 'cargoquery' in response.json():
                    placements = response.json()['cargoquery']
                    if not placements:
                        print(f"  -> No placements found.")
                    for item in placements:
                        t_data = item['title']
                        tourney = t_data.get('tournament', 'EWC Qualifier')
                        date = t_data.get('date', '')[:10]
                        place = t_data.get('placement', 'N/A')
                        
                        if place == '1':
                            outcome = f"🟢 **1st**"
                        elif place in ['2', '3', '4']:
                            outcome = f"⚪ **{place}th**"
                        else:
                            outcome = f"🔴 **{place}th**"

                        print(f"  -> Found placement: {date} | {tourney}")
                        audit_log.append(f"{outcome} `{date}` | **{coach} ({game.upper()}):** {tourney}")
            except Exception as e:
                print(f"❌ Failed Liquipedia pull for {coach}: {e}")

    print(f"--- Audit Loop Complete. {len(audit_log)} matches ready for Discord ---")

    if audit_log:
        send_discord_message("### 📋 Fortnightly Coach Tracker Audit (Last 14 Days)\n" + "\n".join(audit_log))
    else:
        send_discord_message("### 📋 Fortnightly Coach Tracker Audit\nNo matches found for any tracked teams in the last 14 days.")

if __name__ == "__main__":
    run_audit()
