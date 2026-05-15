"""
Get Google OAuth2 tokens for Gmail and Calendar.
Prints the auth URL so you can paste it into any browser.

Usage:
    python scripts/get_google_token.py

After logging in and approving, paste the redirect URL back into the terminal.
"""
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import set_key
from google_auth_oauthlib.flow import InstalledAppFlow

CREDENTIALS_FILE = ROOT / "credentials.json"
TOKEN_PICKLE     = ROOT / "google_token.pickle"
ENV_FILE         = ROOT / ".env"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

if not CREDENTIALS_FILE.exists():
    print(f"ERROR: credentials.json not found at {CREDENTIALS_FILE}")
    sys.exit(1)

raw = json.loads(CREDENTIALS_FILE.read_text())

# Patch web -> installed so InstalledAppFlow accepts it
if "web" in raw and "installed" not in raw:
    patched = {"installed": raw["web"]}
    PATCHED_FILE = ROOT / "_credentials_patched.json"
    PATCHED_FILE.write_text(json.dumps(patched))
    creds_file = str(PATCHED_FILE)
else:
    creds_file = str(CREDENTIALS_FILE)

flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)

# Generate the auth URL (redirect to localhost:8080)
flow.redirect_uri = "http://localhost:8080/"
auth_url, _ = flow.authorization_url(
    access_type="offline",
    prompt="consent",  # force refresh token to be returned
)

print("\n" + "=" * 70)
print("STEP 1: Open this URL in your browser:")
print("=" * 70)
print(auth_url)
print("=" * 70)
print("\nSTEP 2: Log in, approve Gmail + Calendar access.")
print("STEP 3: You will be redirected to http://localhost:8080/?code=...")
print("        Copy that FULL redirect URL and paste it below.\n")

redirect_response = input("Paste the full redirect URL here: ").strip()

# Exchange the code for tokens
import urllib.parse
parsed = urllib.parse.urlparse(redirect_response)
params = urllib.parse.parse_qs(parsed.query)
code = params.get("code", [None])[0]

if not code:
    print("ERROR: Could not extract 'code' from URL. Make sure you pasted the full URL.")
    sys.exit(1)

flow.fetch_token(code=code)
creds = flow.credentials

# Save tokens into .env
set_key(str(ENV_FILE), "GOOGLE_ACCESS_TOKEN",  creds.token)
set_key(str(ENV_FILE), "GOOGLE_REFRESH_TOKEN", creds.refresh_token or "")

# Save pickle for future refresh
import pickle
with open(TOKEN_PICKLE, "wb") as f:
    pickle.dump(creds, f)

print("\n[OK] Tokens saved to .env!")
print(f"     Access  Token: {creds.token[:60]}...")
print(f"     Refresh Token: {(creds.refresh_token or 'N/A')[:60]}...")
print("\n[NEXT] Restart your MCP server. Gmail and Calendar will now fetch real data.")

# Cleanup
patched_path = ROOT / "_credentials_patched.json"
if patched_path.exists():
    patched_path.unlink()
