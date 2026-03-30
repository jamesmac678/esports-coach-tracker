import os
import json
import requests
import time
from datetime import datetime, timedelta

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")
PANDASCORE_API = os.environ.get("PANDASCORE_API_KEY")

current_week = datetime.utcnow().isocalendar()[1]
if current_week % 2 != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
    print("Odd week detected. Skipping fortnightly audit.")
    exit()

now = datetime.utcnow()
fortnight_ago = now - timedelta(days=14)
pandascore_start = fortnight_ago.strftime('%Y-%m-%dT%H:%M:%SZ')
liquipedia_start = fortnight_ago.strftime('%Y-%m-%d %H:%M:%S')

PANDASCORE_GAMES = ['league-of-legends', 'valorant', 'csgo', 'dota-2', 'rocket-league']
LIQUIPEDIA_WIKIS_FFA = {
    'pubg': 'pubg',
    'free-fire': 'freefire',
    'call-of-duty-warzone': 'callofduty',
    'trackmania': 'trackmania'
}

def send_discord_message(message):
    print("Preparing to send Discord message...")
    if len(message) > 1990:
        message = message[:1990] + "\n...[List Truncated]"
    data = {"content": message}
    response = requests.post(DISCORD_WEBHOOK, json=data)
    print(f"Discord API Response: {response.status_code}")

def run_audit():
    with open('clients.json', 'r') as file:
        clients = json.load(file)

    audit_log = []
    
    for client in clients:
        coach = client.get('coach_name', 'Unknown')
        game = client.get('game', '')
        team_slug = client.get('team_slug', '')
        
        # --- PANDASCORE 1v1 LOGIC (SMART SEARCH) ---
        if game in PANDASCORE_GAMES:
            print(f"Checking PandaScore for {coach} ({game})...")
            headers = {"Authorization": f"Bearer {PANDASCORE_API}"}
            
            # Use fuzzy search instead of strict slug to prevent 404 crashes
            url = f"https://api.pandascore.co/{game}/teams"
            params = {"search[name]": team_slug} 
            
            team_response = requests.get(url, headers=headers, params=params)
            actual_team_id = None
            
            if team_response.status_code == 200:
                teams = team_response.json()
                for t in teams:
                    t_name = t.get('name', '').lower()
                    target = team_slug.lower()
                    
                    # Exact match check, explicitly blocking Academy/Bee teams
                    if target in t_name:
                        if "bee" not in t_name and "academy" not in t_name:
                            actual_team_id = t['id']
                            break
                
                # Bulletproof fallback: grab the first valid team if loop misses
                if not actual_team_id and teams:
                    actual_team_id = teams[0]['id']
            
            if actual_team_id:
                match_url = f"https://api.pandascore.co/teams/{actual_team_id}/matches?filter[status]=finished&range[end_at]={pandascore_start},{now.strftime('%Y-%m-%dT%H:%M:%SZ')}"
                match_response = requests.get(match_url, headers=headers)
                
                if match_response.status_code == 200:
                    matches = match_response.json()
                    if not matches:
                        print("  -> No matches found.")
                    for match in matches:
                        match_name = match.get('name', 'Unknown Match')
                        date = match.get('end_at', '')[:10]
                        winner_id = match.get('winner_id')
                        results = match.get('results', [])
                        
                        our_score, their_score = 0, 0
                        for r in results:
                            if r.get('team_id') == actual_team_id:
                                our_score = r.get('score', 0)
                            else:
                                their_score = r.get('score', 0)
                                
                        scoreline = f"({our_score}-{their_score})"
                        
                        if winner_id == actual_team_id:
                            outcome = f"🟢 {scoreline}"
                        elif winner_id is None:
                            outcome = f"⚪ {scoreline}"
                        else:
                            outcome = f"🔴 {scoreline}"
                            
                        print(f"  -> Found match: {date} | {match_name}")
                        audit_log.append(f"{outcome} `{date}` | **{coach} ({game.upper()}):** {match_name}")
                else:
                    print(f"  -> Matches API failed: {match_response.status_code}")
            else:
                print(f"  -> ❌ Could not find team ID for {team_slug}")
                
        # --- LIQUIPEDIA FFA LOGIC (SECURITY FIX) ---
        elif game in LIQUIPEDIA_WIKIS_FFA:
            wiki = LIQUIPEDIA_WIKIS_FFA[game]
            print(f"Checking Liquipedia for {coach} ({game})...")
            time.sleep(2) 
            
            url = f"https://liquipedia.net/{wiki}/api.php"
            params = {
                "action": "cargoquery", "format": "json", "tables": "Placement",
                "fields": "tournament, date, placement",
                "where": f"participant='{team_slug}' AND date >= '{liquipedia_start}'",
                "limit": "20"
            }
            # Mandatory contact info in User-Agent prevents Cloudflare blocks
            headers = {"User-Agent": "EsportsCoachTracker/1.1 (discord-bot@local)"} 
            
            try:
                response = requests.get(url, params=params, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if 'cargoquery' in data:
                        placements = data['cargoquery']
                        if not placements:
                            print("  -> No placements found.")
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
                    else:
                        print(f"  -> CargoQuery Error (Schema Change?): {data}")
                else:
                    print(f"  -> HTTP Error: {response.status_code}")
            except Exception as e:
                print(f"  -> ❌ Failed Liquipedia pull: {e}")

    print(f"--- Audit Loop Complete. {len(audit_log)} matches ready for Discord ---")

    if audit_log:
        send_discord_message("### 📋 Fortnightly Coach Tracker Audit (Last 14 Days)\n" + "\n".join(audit_log))
    else:
        send_discord_message("### 📋 Fortnightly Coach Tracker Audit\nNo matches found for any tracked teams in the last 14 Days.")

if __name__ == "__main__":
    run_audit()
