"""HaveIBeenPwned v3 client. The API key stays on the backend and never reaches the browser."""
import asyncio
import html
import re
from urllib.parse import quote

import httpx

from ..config import settings

TAG_RE = re.compile(r"<[^>]+>")
MAX_RATE_LIMIT_RETRIES = 2
MAX_RETRY_WAIT_SECONDS = 30


class HibpError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _clean_breach(raw: dict) -> dict:
    # HIBP descriptions contain HTML, so reduce them to plain text.
    description = html.unescape(TAG_RE.sub("", raw.get("Description") or ""))
    return {
        "name": raw.get("Title") or raw.get("Name") or "Unknown",
        "domain": raw.get("Domain") or "",
        "breach_date": raw.get("BreachDate"),
        "pwn_count": raw.get("PwnCount"),
        "data_classes": raw.get("DataClasses") or [],
        "description": description,
        "is_verified": raw.get("IsVerified", False),
    }


async def check_email(email: str, transport: httpx.AsyncBaseTransport | None = None) -> list[dict]:
    if not settings.hibp_api_key:
        raise HibpError("No HIBP API key set. Add HIBP_API_KEY to the .env file and restart.", 503)

    url = f"{settings.hibp_base_url}/breachedaccount/{quote(email, safe='')}"
    headers = {"hibp-api-key": settings.hibp_api_key, "user-agent": settings.hibp_user_agent}

    async with httpx.AsyncClient(timeout=20, transport=transport) as client:
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            try:
                response = await client.get(url, headers=headers, params={"truncateResponse": "false"})
            except httpx.HTTPError as exc:
                raise HibpError(f"Could not reach HaveIBeenPwned: {type(exc).__name__}") from exc

            if response.status_code == 200:
                return [_clean_breach(item) for item in response.json()]
            if response.status_code == 404:
                return []
            if response.status_code == 429:
                wait = float(response.headers.get("retry-after", 2)) + 0.5
                if attempt < MAX_RATE_LIMIT_RETRIES and wait <= MAX_RETRY_WAIT_SECONDS:
                    await asyncio.sleep(wait)
                    continue
                raise HibpError("HIBP rate limit reached. Try again shortly.", 429)
            if response.status_code == 401:
                raise HibpError("HIBP rejected the API key. Check HIBP_API_KEY in .env.", 401)
            if response.status_code == 403:
                raise HibpError("HIBP refused the request (403).", 403)
            raise HibpError(f"HIBP returned an unexpected status ({response.status_code}).")
    raise HibpError("HIBP rate limit reached. Try again shortly.", 429)


def fallback_advice(account_name: str, breaches: list[dict]) -> str:
    """Used when no LLM is available, so a breach always comes with next steps."""
    exposed = sorted({item for breach in breaches for item in breach.get("data_classes", [])})
    lines = [f"{account_name} was found in {len(breaches)} breach(es)."]
    if exposed:
        lines.append(f"Exposed data includes: {', '.join(exposed)}.")
    lines += [
        "1. Change the password on every breached service and anywhere you reused it.",
        "2. Turn on a hardware key or TOTP for this account.",
        "3. Delete accounts on breached services you no longer use.",
    ]
    return "\n".join(lines)
