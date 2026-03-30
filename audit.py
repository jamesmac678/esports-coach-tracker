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
LIQUIPEDIA_WIKIS_1V1 = {'crossfire': 'crossfire'}
LIQUIPEDIA_WIKIS_FFA = {
    'pubg': 'pubg',
    'free-fire': 'freefire',
    'call-of-duty-warzone': 'callofduty',
    'trackmania': 'trackmania'
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
        
        # --- PANDASCORE LOGIC (DIRECT SLUG FETCH) ---
        if game in PANDASCORE_GAMES:
            headers = {"Authorization": f"Bearer {PANDASCORE_API}"}
            
            # THE FIX: Ask PandaScore's global database directly for the exact slug
            team_url = f"https://api.pandascore.co/teams/{team_slug}"
            
            team_response = requests.get(team_url, headers=headers)
            actual_team_id = None
            
            if team_response.status_code == 200:
                team_data = team_response.json()
                # Handle both dict and list responses to be perfectly safe
                if isinstance(team_data, dict) and 'id' in team_data:
                    actual_team_id = team_data['id']
                elif isinstance(team_data, list) and len(team_data) > 0:
                    actual_team_id = team_data[0]['id']
            
            if actual_team_id:
                url = f"https://api.pandascore.co/teams/{actual_team_id}/matches?filter[status]=finished&range[end_at]={pandascore_start},{now.strftime('%Y-%m-%dT%H:%M:%SZ')}"
                response = requests.get(url, headers=headers)
                
                if response.status_code == 200:
                    for match in response.json():
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
                            
                        audit_log.append(f"{outcome} `{date}` | **{coach} ({game.upper()}):** {match_name}")
            else:
                print(f"❌ PandaScore lookup failed for {coach} ({game}). Is '{team_slug}' the correct slug?")
                    
        # --- LIQUIPEDIA LOGIC (1V1 GAMES) ---
        elif game in LIQUIPEDIA_WIKIS_1V1:
            wiki = LIQUIPEDIA_WIKIS_1V1[game]
            liquipedia_team = team_slug.replace('-', ' ').title()
            time.sleep(2)
            
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
                    for item in response.json()['cargoquery']:
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

                        audit_log.append(f"{outcome} `{date}` | **{coach} ({game.upper()}):** {tourney}")
            except Exception as e:
                print(f"Failed 1v1 Liquipedia for {coach}: {e}")

        # --- LIQUIPEDIA LOGIC (FREE-FOR-ALL / BATTLE ROYALE) ---
        elif game in LIQUIPEDIA_WIKIS_FFA:
            wiki = LIQUIPEDIA_WIKIS_FFA[game]
            liquipedia_participant = team_slug 
            time.sleep(2)
            
            url = f"https://liquipedia.net/{wiki}/api.php"
            params = {
                "action": "cargoquery", "format": "json", "tables": "Placement",
                "fields": "tournament, date, placement",
                "where": f"participant='{liquipedia_participant}' AND date >= '{liquipedia_start}'",
                "limit": "20"
            }
            headers = {"User-Agent": "EsportsCoachTracker/1.0"}
            
            try:
                response = requests.get(url, params=params, headers=headers)
                if response.status_code == 200 and 'cargoquery' in response.json():
                    for item in response.json()['cargoquery']:
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

                        audit_log.append(f"{outcome} `{date}` | **{coach} ({game.upper()}):** {tourney}")
            except Exception as e:
                print(f"Failed FFA Liquipedia for {coach}: {e}")

    if audit_log:
        send_discord_message("### 📋 Fortnightly Coach Tracker Audit (Last 14 Days)\n" + "\n".join(audit_log))
    else:
        send_discord_message("### 📋 Fortnightly Coach Tracker Audit\nNo matches found for any tracked teams in the last 14 days.")

if __name__ == "__main__":
    run_audit()
