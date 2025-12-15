import os
import requests
from dotenv import load_dotenv

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

if not SLACK_BOT_TOKEN:
    raise ValueError("Please set environment variable: SLACK_BOT_TOKEN")


def slack_get(url, params=None):
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    r = requests.get(url, headers=headers, params=params)
    return r.json()


def slack_post(url, payload=None):
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }
    r = requests.post(url, json=payload, headers=headers)
    return r.json()


def list_channels():
    resp = slack_get(
        "https://slack.com/api/conversations.list",
        {"types": "public_channel,private_channel", "limit": 200}
    )

    if not resp.get("ok"):
        raise RuntimeError(f"Slack API Error → {resp}")

    return resp.get("channels", [])


def join_channel(channel_id: str):
    resp = slack_post(
        "https://slack.com/api/conversations.join",
        {"channel": channel_id}
    )
    return resp


def send_message(channel_id: str, text: str):
    print(f"\n=== Attempting to join {channel_id} ===")
    join_resp = join_channel(channel_id)
    print("join →", join_resp)

    print(f"\n=== Sending Message to {channel_id} ===")
    msg_resp = slack_post(
        "https://slack.com/api/chat.postMessage",
        {"channel": channel_id, "text": text}
    )
    print("message →", msg_resp)


if __name__ == "__main__":
    print("=== Listing Channels ===")
    channels = list_channels()

    for c in channels:
        print(f"{c['name']:<20} → {c['id']}")

    for channel in channels:
        channel_id = channel["id"]
