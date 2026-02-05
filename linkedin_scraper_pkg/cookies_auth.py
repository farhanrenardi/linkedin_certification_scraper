import json
import os
import re
from typing import List, Tuple
from playwright.async_api import BrowserContext, Page
from .config import COOKIES_FILE


async def load_cookies(path: str = COOKIES_FILE) -> List[dict]:
    """Load and sanitize cookies JSON for LinkedIn domains only.

    - Removes whitespace from values
    - Normalizes domain to start with `.linkedin.com`
    - Normalizes `sameSite` values
    - Filters out entries missing name/value
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            cookies = json.load(f)
    except Exception:
        return []

    clean: List[dict] = []
    for c in cookies:
        if not isinstance(c, dict):
            continue
        if "value" in c and isinstance(c["value"], str):
            c["value"] = re.sub(r"\s+", "", c["value"])  # strip whitespace/newlines
        domain = c.get("domain", "")
        if domain and not domain.startswith("."):
            domain = "." + domain
        if "linkedin.com" not in domain:
            continue
        c["domain"] = domain

        if "sameSite" in c:
            ss = str(c["sameSite"]).lower()
            if ss in ["no_restriction", "none"]:
                c["sameSite"] = "None"
            elif ss in ["lax", "strict"]:
                c["sameSite"] = ss.capitalize()
            else:
                c["sameSite"] = "Lax"

        for k in ["hostOnly", "session", "storeId", "id"]:
            c.pop(k, None)

        if not c.get("name") or not c.get("value"):
            continue

        clean.append(c)
    return clean


async def apply_cookies(context: BrowserContext, cookies: List[dict]) -> Tuple[bool, bool]:
    """Apply cookies to the context and return (cookies_loaded, has_li_at).

    The presence of `li_at` is a strong indicator of authenticated sessions.
    """
    has_li_at = any(c.get("name") == "li_at" for c in cookies)
    if cookies:
        try:
            await context.add_cookies(cookies)
            return True, has_li_at
        except Exception:
            return False, has_li_at
    return False, has_li_at


async def check_login_status(page: Page) -> Tuple[bool, List[str]]:
    """Detect guest/authwall state using multiple non-brittle signals.

    We avoid relying on dynamic class names and prefer stable attributes or
    semantic text to identify restricted views.
    """
    debug: List[str] = []
    is_guest = False
    try:
        selectors = [
            ".authwall-join-form",
            "form.authwall-join-form",
            "[data-test-id='join-form']",
        ]
        for sel in selectors:
            if await page.locator(sel).count() > 0:
                is_guest = True
                debug.append(f"Authwall:{sel}")
                break

        url = page.url
        if any(k in url for k in ["signup", "login", "authwall"]):
            is_guest = True
            debug.append(f"URL:{url}")

        # Stable header button used in guest headers on some locales
        if await page.locator("[data-test-id='header-join']").count() > 0:
            is_guest = True
            debug.append("GuestHeader")
    except Exception as e:
        debug.append(f"LoginCheckErr:{str(e)[:30]}")

    return is_guest, debug
