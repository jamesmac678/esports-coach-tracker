import os
import json
import requests
import time
from datetime import datetime, timedelta

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")

# Smart Lock: Run only on Even weeks
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
        
        if game not in WIKI_MAP:
            continue
            
        wiki, match_type = WIKI_MAP[game]
        time.sleep(2) # Safe 2-second brake for Liquipedia limits
        
        # --- 1v1 GAMES (LoL, CSGO, Valorant, etc.) ---
        if match_type == '1v1':
            # Auto-formats hyphenated slugs (e.g., 'team-vitality' -> 'Team Vitality')
            liquipedia_team = team_slug
            
            url = f"https://liquipedia.net/{wiki}/api.php"
            params = {
                "action": "cargoquery", "format": "json", "tables": "Match2",
                "fields": "tournament, date, opponent1, opponent2, winner, result1, result2",
                "where": f"(opponent1='{liquipedia_team}' OR opponent2='{liquipedia_team}') AND dateexact >= '{liquipedia_start}'",
                "limit": "20"
            }
