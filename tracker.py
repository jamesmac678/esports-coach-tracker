import os
import json
import requests
from datetime import datetime, timedelta

# 1. Grab our secret keys from GitHub Actions
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")
PANDASCORE_API = os.environ.get("PANDASCORE_API_KEY")

# 2. Figure out the time window (last 24 hours)
now = datetime.utcnow()
yesterday = now - timedelta(days=1)
start_time = yesterday.strftime('%Y-%m-%dT%H:%M:%SZ')

def send_discord_message(message):
    data = {"content": message}
    requests.post(DISCORD_WEBHOOK, json=data)

def check_matches():
    # Load your client roster
    with open('clients.json', 'r') as file:
        clients = json.load(file)

    updates = []
    
    for client in clients:
        coach = client['coach_name']
        team = client['team_slug']
        
        # Ask PandaScore for matches from the last 24 hours for this team
        url = f"https://api.pandascore.co/teams/{team}/matches?filter[status]=finished&range[end_at]={start_time},{now.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        headers = {"Authorization": f"Bearer {PANDASCORE_API}"}
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            matches = response.json()
            for match in matches:
                match_name = match.get('name', 'Unknown Match')
                updates.append(f"🚨 **{coach}'s Team Update:** {match_name} has finished. Time to check in!")
                
    # Send the daily digest to Discord
    if updates:
        final_message = "### 📊 Daily EWC Coach Tracker Digest\n" + "\n".join(updates)
        send_discord_message(final_message)
    else:
        print("No new matches in the last 24 hours.")

if __name__ == "__main__":
    check_matches()
