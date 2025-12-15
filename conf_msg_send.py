import os
import msal
import requests


from dotenv import load_dotenv
import random
from datetime import datetime

load_dotenv()
CLIENT_SECRET = os.getenv("TEAMS_CLIENT_SECRET")

TENANT_ID = "112dbc6b-af5d-4564-b13a-22909f6d053e"
CLIENT_ID = "56276832-d861-47d5-b671-50200893cda0"

TEAM_ID = "89d8fa1f-940f-4236-b83a-1c3557c6916b"
CHANNEL_ID = "19:1cd74c12568d4b4897a9ed0264399595@thread.tacv2"

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["https://graph.microsoft.com/.default"]

app = msal.ConfidentialClientApplication(
    CLIENT_ID,
    authority=AUTHORITY,
    client_credential=CLIENT_SECRET,
)

result = app.acquire_token_for_client(scopes=SCOPES)

if "access_token" not in result:
    raise Exception(f"Could not get token: {result}")

access_token = result["access_token"]
resp = requests.get(
    f"https://graph.microsoft.com/v1.0/teams/{TEAM_ID}/members?$select=id,displayName,roles",
    headers={"Authorization": f"Bearer {access_token}"},
)
print(resp.json())


url = f"https://graph.microsoft.com/v1.0/teams/{TEAM_ID}/channels/{CHANNEL_ID}/messages"

payload = {
   "createdDateTime":"2019-02-04T19:58:15.511Z",
   "from":{
      "user":{
         "id":  "2312321",
         "displayName":"weugene",
      }
   },
   "body":{
      "contentType":"html",
      "content":"Hello World"
   }
}

headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
}

resp = requests.post(url, json=payload, headers=headers)
print("Status:", resp.status_code)
print("Response:", resp.text)