import os
from urllib.parse import urlparse

from flask import Flask, redirect, request, session, url_for, render_template_string
from dotenv import load_dotenv
import msal

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret")

TOKEN_CACHE_FILE = os.getenv("TEAMS_TOKEN_CACHE_FILE")
TENANT_ID = os.getenv("TEAMS_TENANT_ID")
CLIENT_ID = os.getenv("TEAMS_CLIENT_ID")
CLIENT_SECRET = os.getenv("TEAMS_CLIENT_SECRET")
TEAM_ID = os.getenv("TEAMS_TEAM_ID")
CHANNEL_ID = os.getenv("TEAMS_CHANNEL_ID")

REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:5000/auth/callback")
SCOPES = [
    "ChannelMessage.Send",
    "Group.ReadWrite.All",  # optional but nice to have
    "Team.ReadBasic.All"
]

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"



HOME_HTML = """
<h2>Flask + Microsoft Login (Auth Code)</h2>
{% if user %}
  <p>✅ Logged in as: <b>{{ user.get('name') }}</b></p>
  <p>Preferred username: {{ user.get('preferred_username') }}</p>
  <p>Tenant: {{ user.get('tid') }}</p>
  <p><a href="{{ url_for('token') }}">View token (debug)</a></p>
  <p><a href="{{ url_for('logout') }}">Logout</a></p>
{% else %}
  <p>❌ Not logged in</p>
  <a href="{{ url_for('login') }}">Sign in with Microsoft</a>
{% endif %}
"""

TOKEN_HTML = """
<h3>Token (debug)</h3>
<p><b>Don't paste this into chat/tools.</b></p>
<pre style="white-space: pre-wrap;">{{ token }}</pre>
<p><a href="{{ url_for('home') }}">Back</a></p>
"""

def build_msal_app(cache=None):
    return msal.PublicClientApplication(
        client_id=CLIENT_ID,
        authority=AUTHORITY,
    )

@app.route("/")
def home():
    user = session.get("user")
    return render_template_string(HOME_HTML, user=user)

@app.route("/login")
def login():
    # state protects against CSRF
    flow = build_msal_app().initiate_auth_code_flow(
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    session["flow"] = flow
    print(session["flow"])
    return redirect(flow["auth_uri"])

@app.route("/auth/callback")
def auth_callback():
    # Microsoft redirects the browser here with ?code=...&state=...
    # Use and remove the flow from session to avoid replay on refresh/back.
    print(session)
    flow = session.pop("flow", None)
    if not flow:
        return "Missing auth flow in session. Start over at /login", 400

    # Basic CSRF / correlation check
    state_in_req = request.args.get("state")
    state_in_flow = flow.get("state")
    if not state_in_req or state_in_req != state_in_flow:
        return "Invalid state. Please try /login again.", 400

    # Exchange code -> tokens (server-to-server)
    try:
        result = build_msal_app().acquire_token_by_auth_code_flow(flow, request.args)
    except Exception as ex:
        # Avoid printing secrets; keep error generic.
        return f"Token exchange failed: {type(ex).__name__}", 500

    if not result or "error" in result:
        err = (result or {}).get("error", "unknown_error")
        desc = (result or {}).get("error_description", "No description.")
        # Don't echo the whole payload; it may contain sensitive fields.
        return f"Auth error: {err}<br>Description: {desc}", 400

    # Store minimal info. For production, store tokens in a secure server-side store.
    session["token_result"] = {
        "expires_in": result.get("expires_in"),
        "scope": result.get("scope"),
        "refresh_token_present": bool(result.get("refresh_token")),
    }
    session["user"] = result.get("id_token_claims", {})

    # If you need the access token later, store it server-side (not in a client cookie session).
    # access_token = result.get("access_token")

    return redirect(url_for("home"))

@app.route("/token")
def token():
    token_result = session.get("token_result")
    if not token_result:
        return redirect(url_for("home"))
    return render_template_string(TOKEN_HTML, token=token_result)

@app.route("/logout")
def logout():
    session.clear()

    # Optional: also sign out from Microsoft (front-channel logout)
    # You can keep it simple and just clear session for local dev.
    return redirect(url_for("home"))

if __name__ == "__main__":
    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError("Missing CLIENT_ID or CLIENT_SECRET in .env")
    app.run(host="127.0.0.1", port=5000, debug=True)
