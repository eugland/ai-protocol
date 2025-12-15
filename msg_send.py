import os
import msal
import requests
from dotenv import load_dotenv
import random
from datetime import datetime

load_dotenv()

TOKEN_CACHE_FILE = os.getenv("TEAMS_TOKEN_CACHE_FILE")
TENANT_ID = os.getenv("TEAMS_TENANT_ID")
CLIENT_ID = os.getenv("TEAMS_CLIENT_ID")
CLIENT_SECRET = os.getenv("TEAMS_CLIENT_SECRET")
TEAM_ID = os.getenv("TEAMS_TEAM_ID")
CHANNEL_ID = os.getenv("TEAMS_CHANNEL_ID")

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = [
    "ChannelMessage.Send",
    "Group.ReadWrite.All",  # optional but nice to have
    "Team.ReadBasic.All"
]

# ====== Load / Save cache helpers ======

def load_cache():
    cache = msal.SerializableTokenCache()
    if os.path.exists(TOKEN_CACHE_FILE):
        with open(TOKEN_CACHE_FILE, "r") as f:
            cache.deserialize(f.read())
    return cache

def save_cache(cache):
    if cache and cache.has_state_changed:
        with open(TOKEN_CACHE_FILE, "w") as f:
            f.write(cache.serialize())

# ====== MSAL: Public client + device code ======

cache = load_cache()

app = msal.PublicClientApplication(
    CLIENT_ID,
    authority=AUTHORITY,
    token_cache=cache,   # <-- IMPORTANT: wire the cache in here
)

accounts = app.get_accounts()
print("Accounts in cache:", accounts)

if accounts:
    result = app.acquire_token_silent(SCOPES, account=accounts[0])
else:
    result = None

if not result:
    # Device code flow
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise Exception("Failed to create device flow. Full response: %s" % flow)

    print("==== DEVICE CODE LOGIN ====")
    print("Go to:", flow["verification_uri"])
    print("Enter code:", flow["user_code"])
    print("===========================")

    result = app.acquire_token_by_device_flow(flow)  # blocks until finished


save_cache(cache)

if "access_token" not in result:
    raise Exception(f"Could not get token: {result}")

access_token = result["access_token"]
token = access_token

GRAPH = "https://graph.microsoft.com/v1.0"

headers = lambda token: {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
}
token = access_token
# 1️⃣ Get Teams you are a member of
def get_joined_teams(access_token):
    url = f"{GRAPH}/me/joinedTeams?$select=id,displayName"
    resp = requests.get(url, headers=headers(access_token))
    print(resp.json())
    resp.raise_for_status()
    return resp.json()["value"]

# 2️⃣ Get channels for a given team
def get_channels_for_team(access_token, team_id):
    url = f"{GRAPH}/teams/{team_id}/channels?$select=id,displayName"
    resp = requests.get(url, headers=headers(access_token))
    print(resp.json())
    resp.raise_for_status()
    return resp.json()["value"]

# 3️⃣ Send a message to the channel saying who I am
def send_hello_message(access_token, team_id, channel_id, user_name):
    url = f"{GRAPH}/teams/{team_id}/channels/{channel_id}/messages"
    payload = {
        "body": {
            "contentType": "html",
            "content": f"Hello 👋 I am <b>{user_name}</b> and I can now message this channel 🎉"
        }
    }
    resp = requests.post(url, headers=headers(access_token), json=payload)
    print(resp.status_code, resp.text)
    resp.raise_for_status()

# 2️⃣ Who am I?
me = requests.get(f"{GRAPH}/me?$select=displayName", headers=headers(token)).json()
user_name = me.get("displayName", "Unknown User")

# 3️⃣ List teams
teams = get_joined_teams(token)
print("Teams:", teams)

team = teams[0]
team_id = team["id"]
print(f"Selected Team: {team['displayName']} ({team_id})")

# 4️⃣ List channels
channels = get_channels_for_team(token, team_id)
print("Channels:", channels)

channel = channels[0]
channel_id = channel["id"]
print(f"Selected Channel: {channel['displayName']} ({channel_id})")

# 5️⃣ Send message
send_hello_message(token, team_id, channel_id, user_name)