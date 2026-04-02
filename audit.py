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
LIQUIPEDIA_WIKIS = {
    'pubg': 'pubg',
    'free-fire': 'freefire',
    'crossfire': 'crossfire',
    'call-of-duty-warzone': 'callofduty',
    'trackmania': 'trackmania'
}

def send_discord_message(message):
    print("sending discord message")
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
            headers = {"Authorization": f"Bearer {PANDASCORE_API}"}
            search_name = team_slug.replace('-', ' ')
            team_url = f"https://api.pandascore.co/{game}/teams"
            #?search[name]={search_name}
            
            team_response = requests.get(team_url, headers=headers)
            print(team_response)
            if team_response.status_code == 200 and team_response.json():
                actual_team_id = team_response.json()[0]['id']
                
                url = f"https://api.pandascore.co/teams/{actual_team_id}/matches?filter[status]=finished&range[end_at]={pandascore_start},{now.strftime('%Y-%m-%dT%H:%M:%SZ')}"
                response = requests.get(url, headers=headers)
                
                if response.status_code == 200:
                    for match in response.json():
                        match_name = match.get('name', 'Unknown Match')
                        date = match.get('end_at', '')[:10]
                        winner_id = match.get('winner_id')
                        results = match.get('results', [])
                        
                        our_score = 0
                        their_score = 0
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
                print(f"status: {team_response.status_code}") 
                print(team_response)
                print(f"❌ PandaScore Auto-Discovery Failed for {coach} ({game})")
                    
        # --- LIQUIPEDIA LOGIC ---
        elif game in LIQUIPEDIA_WIKIS:
            wiki = LIQUIPEDIA_WIKIS[game]
            liquipedia_team = team_slug.replace('-', ' ').title()
            time.sleep(2)
            
            url = f"https://liquipedia.net/{wiki}/api.php"
            params = {
                "action": "cargoquery",
                "format": "json",
                "tables": "Match2",
                "fields": "match2id, tournament, date, opponent1, opponent2, winner, result1, result2",
                "where": f"(opponent1='{liquipedia_team}' OR opponent2='{liquipedia_team}') AND dateexact >= '{liquipedia_start}'",
                "limit": "20"
            }
            headers = {"User-Agent": "EsportsCoachTracker/1.0 (Automated Discord Alerts)"}
            
            try:
                response = requests.get(url, params=params, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if 'cargoquery' in data:
                        for item in data['cargoquery']:
                            title_data = item['title']
                            tourney = title_data.get('tournament', 'EWC Qualifier')
                            date = title_data.get('date', '')[:10]
                            opp1 = title_data.get('opponent1', '')
                            opp2 = title_data.get('opponent2', '')
                            winner_num = title_data.get('winner', '')
                            res1 = title_data.get('result1', '0') or '0'
                            res2 = title_data.get('result2', '0') or '0'

                            if opp1 == liquipedia_team:
                                our_score, their_score = res1, res2
                            else:
                                our_score, their_score = res2, res1
                                
                            scoreline = f"({our_score}-{their_score})"

                            if (winner_num == '1' and opp1 == liquipedia_team) or (winner_num == '2' and opp2 == liquipedia_team):
                                outcome = f"🟢 {scoreline}"
                            elif winner_num == '0' or not winner_num:
                                outcome = f"⚪ {scoreline}"
                            else:
                                outcome = f"🔴 {scoreline}"

                            audit_log.append(f"{outcome} `{date}` | **{coach} ({game.upper()}):** {tourney}")
            except Exception as e:
                print(f"Failed to pull Liquipedia data for {coach}: {e}")

    if audit_log:
        final_message = "### 📋 Fortnightly Coach Tracker Audit (Last 14 Days)\n" + "\n".join(audit_log)
        send_discord_message(final_message)
    else:
        send_discord_message("### 📋 Fortnightly Coach Tracker Audit\nNo matches found for any tracked teams in the last 14 days.")

if __name__ == "__main__":
    run_audit()
