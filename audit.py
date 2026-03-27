import os
import json
import requests
import time
from datetime import datetime, timedelta

# 1. Grab our secret keys
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")
PANDASCORE_API = os.environ.get("PANDASCORE_API_KEY")

# 2. The Smart Lock: Run only on Even weeks
current_week = datetime.utcnow().isocalendar()[1]
# If it's an odd week AND this wasn't triggered manually by you, shut down.
if current_week % 2 != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
    print("Odd week detected. Skipping fortnightly audit.")
    exit()

# 3. Figure out the time window (Last 14 days)
now = datetime.utcnow()
fortnight_ago = now - timedelta(days=14)
pandascore_start = fortnight_ago.strftime('%Y-%m-%dT%H:%M:%SZ')
liquipedia_start = fortnight_ago.strftime('%Y-%m-%d %H:%M:%S')

# Route Mapping
PANDASCORE_GAMES = ['league-of-legends', 'valorant', 'csgo', 'dota-2', 'rocket-league']
LIQUIPEDIA_WIKIS = {
    'pubg': 'pubg',
    'free-fire': 'freefire',
    'crossfire': 'crossfire',
    'call-of-duty-warzone': 'callofduty',
    'trackmania': 'trackmania'
}

def send_discord_message(message):
    # Discord has a 2000 character limit per message.
    # If the 14-day audit is massive, we truncate it slightly to prevent a crash.
    if len(message) > 1990:
        message = message[:1990] + "\n...[List Truncated due to length]"
    data = {"content": message}
    requests.post(DISCORD_WEBHOOK, json=data)

def run_audit():
    with open('clients.json', 'r') as file:
        clients = json.load(file)

    audit_log = []
    
    for client in clients:
        coach = client['coach_name']
        game = client['game']
        team_slug = client['team_slug']
        
        # --- PANDASCORE LOGIC ---
        if game in PANDASCORE_GAMES:
            url = f"https://api.pandascore.co/teams/{team_slug}/matches?filter[status]=finished&range[end_at]={pandascore_start},{now.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            headers = {"Authorization": f"Bearer {PANDASCORE_API}"}
            
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                for match in response.json():
                    match_name = match.get('name', 'Unknown Match')
                    date = match.get('end_at', '')[:10] # Formats to just YYYY-MM-DD
                    audit_log.append(f"✅ `{date}` | **{coach} ({game.upper()}):** {match_name}")
                    
        # --- LIQUIPEDIA LOGIC ---
        elif game in LIQUIPEDIA_WIKIS:
            wiki = LIQUIPEDIA_WIKIS[game]
            liquipedia_team = team_slug.replace('-', ' ').title()
            
            time.sleep(2) # Safety brake
            
            url = f"https://liquipedia.net/{wiki}/api.php"
            params = {
                "action": "cargoquery",
                "format": "json",
                "tables": "Match2",
                "fields": "match2id, tournament, date",
                "where": f"(opponent1='{liquipedia_team}' OR opponent2='{liquipedia_team}') AND dateexact >= '{liquipedia_start}'",
                "limit": "20"
            }
            headers = {
                "User-Agent": "EsportsCoachTracker/1.0 (Automated Discord Alerts)"
            }
            
            try:
                response = requests.get(url, params=params, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if 'cargoquery' in data:
                        for item in data['cargoquery']:
                            tourney = item['title'].get('tournament', 'EWC Qualifier')
                            date = item['title'].get('date', '')[:10]
                            audit_log.append(f"✅ `{date}` | **{coach} ({game.upper()}):** {tourney}")
            except Exception as e:
                print(f"Failed to pull Liquipedia data for {coach}: {e}")

    # Send the final audit digest
    if audit_log:
        final_message = "### 📋 Fortnightly Coach Tracker Audit (Last 14 Days)\n" + "\n".join(audit_log)
        send_discord_message(final_message)
    else:
        send_discord_message("### 📋 Fortnightly Coach Tracker Audit\nNo matches found for any tracked teams in the last 14 days.")

if __name__ == "__main__":
    run_audit()
