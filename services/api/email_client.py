from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger("auth.email")

RESEND_ENDPOINT = "https://api.resend.com/emails"


def _config() -> tuple[str | None, str, str]:
    """Return (api_key, from_address, app_base_url) loaded from the environment."""
    api_key = os.getenv("RESEND_API_KEY")
    from_address = os.getenv("RESET_EMAIL_FROM", "onboarding@resend.dev")
    app_base_url = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    return api_key, from_address, app_base_url


def build_reset_link(token: str) -> str:
    _, _, app_base_url = _config()
    return f"{app_base_url}/reset-password?token={token}"


def send_reset_email(to_address: str, token: str) -> bool:
    """Send a password-reset email via Resend. Returns True on success.

    Failures are logged and swallowed so the caller can keep the response
    identical for registered and unregistered addresses (no information leak).
    """
    api_key, from_address, _ = _config()
    if not api_key:
        logger.warning("RESEND_API_KEY is not set; skipping reset email to %s", to_address)
        return False

    reset_link = build_reset_link(token)
    payload = {
        "from": from_address,
        "to": [to_address],
        "subject": "Reset your password",
        "html": (
            "<p>We received a request to reset your password.</p>"
            f'<p><a href="{reset_link}">Click here to choose a new password</a>.</p>'
            "<p>If you did not request this, you can safely ignore this email. "
            "This link will expire shortly.</p>"
        ),
        "text": (
            "We received a request to reset your password.\n"
            f"Open this link to choose a new password: {reset_link}\n"
            "If you did not request this, you can ignore this email."
        ),
    }
    request = urllib.request.Request(
        RESEND_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Resend sits behind Cloudflare, which blocks the default
            # "Python-urllib/x.y" agent (error 1010); send an explicit agent.
            "User-Agent": "company-api-password-reset/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")
            logger.info("Resend accepted reset email to %s: %s", to_address, body)
            return True
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        logger.error("Resend rejected reset email to %s (%s): %s", to_address, error.code, detail)
        return False
    except urllib.error.URLError as error:
        logger.error("Could not reach Resend for %s: %s", to_address, error)
        return False
