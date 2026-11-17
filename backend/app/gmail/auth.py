"""One-time OAuth consent. Run: uv run python -m app.gmail.auth

Opens a browser for Google consent (scope: gmail.readonly) and saves the
token to backend/secrets/token.json with mode 600.
"""

import sys

from google_auth_oauthlib.flow import InstalledAppFlow

from app.config import settings
from app.gmail.client import SCOPES, GmailClient, save_token


def main() -> None:
    secret = settings.gmail_client_secret
    if not secret.exists():
        sys.exit(f"Missing {secret}. Download the 'Desktop app' OAuth client JSON from Google Cloud.")
    flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
    creds = flow.run_local_server(
        host="localhost", port=0, open_browser=True, access_type="offline", prompt="consent"
    )
    if not creds.refresh_token:
        sys.exit("Google returned no refresh token. Remove the app's access in your Google Account and retry.")
    save_token(creds)
    email = GmailClient(creds).profile()["emailAddress"]
    print(f"OK. Token saved to {settings.gmail_token} for {email}.")


if __name__ == "__main__":
    main()
