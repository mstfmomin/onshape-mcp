#!/usr/bin/env python3
"""
Onshape OAuth Token Setup for MCP Server.

Usage:
  1. Create an OAuth app in Onshape Developer Portal
  2. Run: python oauth_setup.py --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET
  3. Browser opens → approve access
  4. Copy the token and set ONSHAPE_OAUTH_TOKEN env var
"""

import argparse
import http.server
import json
import sys
import threading
import urllib.parse
import webbrowser

import httpx

ONSHAPE_AUTH_URL = "https://oauth.onshape.com/oauth/authorize"
ONSHAPE_TOKEN_URL = "https://oauth.onshape.com/oauth/token"
REDIRECT_PORT = 8099
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"

# Onshape OAuth scopes
SCOPES = "OAuth2Read OAuth2Write OAuth2Delete"


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handle OAuth callback from Onshape."""

    auth_code = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: #1B5E20;">Onshape Authorization Successful</h1>
                <p>You can close this window and return to the terminal.</p>
                </body></html>
            """)
        else:
            error = params.get("error", ["unknown"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"<html><body><h1>Error: {error}</h1></body></html>".encode())

    def log_message(self, format, *args):
        pass  # Suppress logs


def get_auth_code(client_id: str) -> str:
    """Open browser for user authorization and capture the code."""
    auth_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": "palki-mcp-setup",
    }
    auth_url = f"{ONSHAPE_AUTH_URL}?{urllib.parse.urlencode(auth_params)}"

    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), OAuthCallbackHandler)
    server.timeout = 120  # 2 min timeout

    print(f"\nOpening browser for Onshape authorization...")
    print(f"If browser doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Wait for callback
    while OAuthCallbackHandler.auth_code is None:
        server.handle_request()

    server.server_close()
    return OAuthCallbackHandler.auth_code


def exchange_code_for_token(client_id: str, client_secret: str, code: str) -> dict:
    """Exchange authorization code for access + refresh tokens."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
    }

    response = httpx.post(ONSHAPE_TOKEN_URL, data=data)
    response.raise_for_status()
    return response.json()


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    """Get a new access token using a refresh token."""
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    response = httpx.post(ONSHAPE_TOKEN_URL, data=data)
    response.raise_for_status()
    return response.json()


def main():
    parser = argparse.ArgumentParser(description="Set up Onshape OAuth for MCP Server")
    parser.add_argument("--client-id", required=True, help="OAuth Client ID from Onshape Developer Portal")
    parser.add_argument("--client-secret", required=True, help="OAuth Client Secret")
    parser.add_argument("--refresh", help="Refresh token (to get new access token without browser)")
    args = parser.parse_args()

    if args.refresh:
        print("Refreshing access token...")
        tokens = refresh_access_token(args.client_id, args.client_secret, args.refresh)
    else:
        code = get_auth_code(args.client_id)
        print(f"Authorization code received. Exchanging for tokens...")
        tokens = exchange_code_for_token(args.client_id, args.client_secret, code)

    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token", "")
    expires_in = tokens.get("expires_in", "unknown")

    print(f"\n{'='*60}")
    print(f"ACCESS TOKEN (expires in {expires_in}s):")
    print(f"{access_token}")
    print(f"\nREFRESH TOKEN (save this — use to get new access tokens):")
    print(f"{refresh_token}")
    print(f"{'='*60}")

    print(f"\nTo use with MCP server, set:")
    print(f'  export ONSHAPE_OAUTH_TOKEN="{access_token}"')

    print(f"\nTo refresh later:")
    print(f'  python oauth_setup.py --client-id {args.client_id} --client-secret {args.client_secret} --refresh "{refresh_token}"')

    # Save tokens to file
    token_file = "onshape_tokens.json"
    with open(token_file, "w") as f:
        json.dump(tokens, f, indent=2)
    print(f"\nTokens saved to {token_file}")


if __name__ == "__main__":
    main()
