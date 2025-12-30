import os
from datetime import datetime

import msal
import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
)

load_dotenv()

# ====== ENV CONFIG ======
TOKEN_CACHE_FILE = os.getenv("TEAMS_TOKEN_CACHE_FILE", "msal_cache.json-1")
TENANT_ID = os.getenv("TEAMS_TENANT_ID")
CLIENT_ID = os.getenv("TEAMS_CLIENT_ID")
CLIENT_SECRET = os.getenv("TEAMS_CLIENT_SECRET")  # not used in device code, but kept
DEFAULT_TEAM_ID = os.getenv("TEAMS_TEAM_ID")      # optional, used as default
DEFAULT_CHANNEL_ID = os.getenv("TEAMS_CHANNEL_ID")

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = [
    "ChannelMessage.Send",
    "Group.ReadWrite.All",  # needed for teams/channels
    "Team.ReadBasic.All",
    "User.Read",            # to call /me
]

GRAPH = "https://graph.microsoft.com/v1.0"

# ====== SLACK CONFIG ======
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")  # xoxb-... bot token


# ====== Flask App ======
app = Flask(__name__)
app.secret_key = "dev-secret-change-me"  # for flash() messages


# ====== MSAL Token Cache Helpers ======
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


def acquire_token():
    """
    Acquire an access token using:
      - cached account (silent)
      - OR device code flow (first time / expired)
    This will print device code instructions in the *terminal* once.
    """
    cache = load_cache()

    app_msal = msal.PublicClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        token_cache=cache,
    )

    accounts = app_msal.get_accounts()
    if accounts:
        result = app_msal.acquire_token_silent(SCOPES, account=accounts[0])
    else:
        result = None

    if not result:
        # Device code flow (interactive on the *terminal*)
        flow = app_msal.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise Exception(f"Failed to create device flow. Full response: {flow}")

        print("==== DEVICE CODE LOGIN ====")
        print("Go to:", flow["verification_uri"])
        print("Enter code:", flow["user_code"])
        print("===========================")

        result = app_msal.acquire_token_by_device_flow(flow)

    save_cache(cache)

    if "access_token" not in result:
        raise Exception(f"Could not get token: {result}")

    return result["access_token"]


def headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


# ====== Graph Helpers ======
def get_me(token):
    resp = requests.get(f"{GRAPH}/me?$select=displayName,userPrincipalName", headers=headers(token))
    resp.raise_for_status()
    return resp.json()


def get_joined_teams(token):
    url = f"{GRAPH}/me/joinedTeams?$select=id,displayName"
    resp = requests.get(url, headers=headers(token))
    resp.raise_for_status()
    return resp.json().get("value", [])


def get_channels_for_team(token, team_id):
    url = f"{GRAPH}/teams/{team_id}/channels?$select=id,displayName"
    resp = requests.get(url, headers=headers(token))
    resp.raise_for_status()
    return resp.json().get("value", [])


def send_message_to_channel(token, team_id, channel_id, content_html):
    url = f"{GRAPH}/teams/{team_id}/channels/{channel_id}/messages"
    payload = {
        "body": {
            "contentType": "html",
            "content": content_html,
        }
    }
    resp = requests.post(url, headers=headers(token), json=payload)
    resp.raise_for_status()
    return resp.json()


def slack_headers():
    if not SLACK_BOT_TOKEN:
        raise RuntimeError("SLACK_BOT_TOKEN is not configured in environment.")
    return {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}


def slack_list_channels():
    url = "https://slack.com/api/conversations.list"
    params = {
        "types": "public_channel,private_channel",
        "limit": 200,
    }
    resp = requests.get(url, headers=slack_headers(), params=params)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack API Error → {data}")
    return [c for c in data.get("channels", []) if not c.get("is_archived")]


def slack_send_message(channel_id: str, text: str):
    url = "https://slack.com/api/chat.postMessage"
    headers = slack_headers()
    headers["Content-Type"] = "application/json; charset=utf-8"
    payload = {
        "channel": channel_id,
        "text": text,
    }
    resp = requests.post(url, json=payload, headers=headers)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack API Error → {data}")
    return data


@app.route("/", methods=["GET"])
def index():
    try:
        token = acquire_token()
    except Exception as e:
        # This error basically means MSAL/Graph is misconfigured
        return f"Authentication failed: {e}", 500

    try:
        me = get_me(token)
        user_name = me.get("displayName") or me.get("userPrincipalName", "Unknown User")
    except Exception as e:
        print("Error fetching /me:", e)
        user_name = "Unknown User"

    try:
        teams = get_joined_teams(token)
    except Exception as e:
        print("Error fetching teams:", e)
        teams = []
    slack_channels = []
    slack_error = None
    if SLACK_BOT_TOKEN:
        try:
            slack_channels = slack_list_channels()
        except Exception as e:
            print("Error fetching Slack channels:", e)
            slack_error = "Could not load Slack channels. Check SLACK_BOT_TOKEN and scopes."
    else:
        slack_error = "SLACK_BOT_TOKEN not configured; Slack sender disabled."

    return render_template(
        "index.html",
        user_name=user_name,
        teams=teams,
        default_team_id=DEFAULT_TEAM_ID or "",
        default_channel_id=DEFAULT_CHANNEL_ID or "",
        slack_channels=slack_channels,
        slack_error=slack_error,
    )


@app.route("/channels")
def channels():
    """
    Return channels for a given Team as JSON.
    Called via JS when user selects a team.
    """
    team_id = request.args.get("team_id")
    if not team_id:
        return jsonify({"error": "team_id is required"}), 400

    try:
        token = acquire_token()
        channels = get_channels_for_team(token, team_id)
        return jsonify(channels)
    except Exception as e:
        print("Error fetching channels:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/send", methods=["POST"])
def send():
    """
    Send a message to the selected Teams team/channel.
    """
    team_id = request.form.get("team_id")
    channel_id = request.form.get("channel_id")
    message = request.form.get("message", "").strip()

    if not team_id or not channel_id or not message:
        flash("Please select a Team, a Channel, and enter a message.", "error")
        return redirect(url_for("index"))

    try:
        token = acquire_token()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        content_html = f"<b>{now}</b> — {message}"
        send_message_to_channel(token, team_id, channel_id, content_html)
        flash("Teams message sent successfully ✅", "success")
    except Exception as e:
        print("Error sending Teams message:", e)
        flash(f"Failed to send Teams message: {e}", "error")

    return redirect(url_for("index"))


@app.route("/slack/send", methods=["POST"])
def slack_send():
    channel_id = request.form.get("slack_channel_id")
    message = request.form.get("slack_message", "").strip()

    if not channel_id or not message:
        flash("Please select a Slack channel and enter a message.", "error")
        return redirect(url_for("index"))

    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = f"{now} — {message}"
        slack_send_message(channel_id, text)
        flash("Slack message sent successfully ✅", "success")
    except Exception as e:
        print("Error sending Slack message:", e)
        flash(f"Failed to send Slack message: {e}", "error")

    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
