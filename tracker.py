import os
import json
import requests
import time
from datetime import datetime, timedelta

# 1. Grab our secret keys from GitHub Actions
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")
PANDASCORE_API = os.environ.get("PANDASCORE_API_KEY")

# 2. Figure out the time windows
now = datetime.utcnow()
yesterday = now - timedelta(days=1)
pandascore_start = yesterday.strftime('%Y-%m-%dT%H:%M:%SZ')
liquipedia_start = yesterday.strftime('%Y-%m-%d %H:%M:%S')

# 3. Route Mapping: Tell the script which API to use for which game
PANDASCORE_GAMES = ['league-of-legends', 'valorant', 'csgo', 'dota-2', 'rocket-league']

LIQUIPEDIA_WIKIS = {
    'pubg': 'pubg',
    'free-fire': 'freefire',
    'crossfire': 'crossfire',
    'call-of-duty-warzone': 'callofduty',
    'trackmania': 'trackmania'
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
        
        # --- PANDASCORE LOGIC (Major Titles) ---
        if game in PANDASCORE_GAMES:
            url = f"https://api.pandascore.co/teams/{team_slug}/matches?filter[status]=finished&range[end_at]={pandascore_start},{now.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            headers = {"Authorization": f"Bearer {PANDASCORE_API}"}
            
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                for match in response.json():
                    match_name = match.get('name', 'Unknown Match')
                    updates.append(f"🚨 **{coach}'s Update ({game.upper()}):** {match_name} has finished.")
                    
        # --- LIQUIPEDIA LOGIC (Minor Titles) ---
        elif game in LIQUIPEDIA_WIKIS:
            wiki = LIQUIPEDIA_WIKIS[game]
            
            # Liquipedia requires Title Case with spaces (e.g., "team-vitality" -> "Team Vitality")
            liquipedia_team = team_slug.replace('-', ' ').title()
            
            # SAFETY FEATURE: Sleep for 2 seconds to respect Liquipedia's strict rate limits
            time.sleep(2)
            
            url = f"https://liquipedia.net/{wiki}/api.php"
            params = {
                "action": "cargoquery",
                "format": "json",
                "tables": "Match2",
                "fields": "match2id, tournament",
                "where": f"(opponent1='{liquipedia_team}' OR opponent2='{liquipedia_team}') AND dateexact >= '{liquipedia_start}'",
                "limit": "5"
            }
            # SAFETY FEATURE: Liquipedia blocks scripts without a User-Agent
            headers = {
                "User-Agent": "EsportsCoachTracker/1.0 (Automated Discord Alerts)"
            }
            
            try:
                response = requests.get(url, params=params, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if 'cargoquery' in data:
                        for item in data['cargoquery']:
                            tourney = item['title'].get('tournament', 'an EWC Qualifier event')
                            updates.append(f"🚨 **{coach}'s Update ({game.upper()}):** A match at {tourney} has finished.")
            except Exception as e:
                print(f"Failed to pull Liquipedia data for {coach}: {e}")

    # Send the final daily digest
    if updates:
        final_message = "### 📊 Daily Coach Tracker Digest\n" + "\n".join(updates)
        send_discord_message(final_message)
    else:
        print("No new matches in the last 24 hours.")

if __name__ == "__main__":
    check_matches()
