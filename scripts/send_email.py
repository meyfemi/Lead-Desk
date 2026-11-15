#!/usr/bin/env python3
"""
Email sender via Mailtrap Sending API.
Reads credentials from .env in the project root.
Uses curl under the hood to avoid macOS Python TLS fingerprint issues with Cloudflare.
"""
import argparse
import json
import shutil
import subprocess
import sys

from config import load_env, identity


def send_email(to_email, to_name, subject, body_text, from_email, from_name, api_key):
    if not shutil.which("curl"):
        return False, {"error": "curl not found — install curl to send emails"}

    payload = {
        "from": {"email": from_email, "name": from_name},
        "to": [{"email": to_email, "name": to_name or to_email}],
        "subject": subject,
        "text": body_text,
    }

    cmd = [
        "curl", "--silent", "--show-error",
        "-X", "POST", "https://send.api.mailtrap.io/api/send",
        "-H", f"Authorization: Bearer {api_key}",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload),
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            return False, {"error": proc.stderr.strip()}
        result = json.loads(proc.stdout)
        success = result.get("success", False)
        return success, result
    except subprocess.TimeoutExpired:
        return False, {"error": "Request timed out after 30s"}
    except json.JSONDecodeError:
        return False, {"error": f"Non-JSON response: {proc.stdout[:200]}"}
    except Exception as e:
        return False, {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Send email via Mailtrap API")
    parser.add_argument("--to-email", required=True, help="Recipient email address")
    parser.add_argument("--to-name", default="", help="Recipient display name")
    parser.add_argument("--subject", required=True, help="Email subject line")
    parser.add_argument("--body-file", help="Path to plain text file with email body")
    parser.add_argument("--body", help="Email body as a string")
    args = parser.parse_args()

    env = load_env()
    api_key = env.get("MAILTRAP_API_KEY")
    who = identity(env)
    from_email = who["from_email"]
    from_name = who["from_name"]

    if not api_key:
        print(json.dumps({"status": "error", "message": "MAILTRAP_API_KEY not found in .env"}))
        sys.exit(1)
    if not from_email:
        print(json.dumps({"status": "error", "message": "MAIL_FROM_ADDRESS not found in .env"}))
        sys.exit(1)

    if args.body_file:
        with open(args.body_file, encoding="utf-8") as f:
            body = f.read()
    elif args.body:
        body = args.body
    else:
        body = sys.stdin.read()

    if not body.strip():
        print(json.dumps({"status": "error", "message": "Email body is empty"}))
        sys.exit(1)

    success, result = send_email(
        args.to_email, args.to_name, args.subject, body,
        from_email, from_name, api_key,
    )

    output = {"status": "sent" if success else "error", "result": result}
    print(json.dumps(output, indent=2))

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
