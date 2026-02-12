# FILE: linkedin_scraper_pkg/config.py
import os
import random

COOKIES_FILE = os.environ.get("LINKEDIN_COOKIES_PATH", "cookies.json")
SLOW_MO_MS = int(os.environ.get("SCRAPER_SLOW_MO_MS", "50")) # Sedikit slow-mo biar render sempat jalan
BLOCK_IMAGES = os.environ.get("SCRAPER_BLOCK_IMAGES", "true").lower() != "false"
USE_CDP = os.environ.get("SCRAPER_USE_CDP", "false").lower() in ["1", "true", "yes"]
CDP_URL = os.environ.get("SCRAPER_CDP_URL", "http://127.0.0.1:9222")

def user_agents():
    """Return list of recent user agent strings to avoid detection."""
    return [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ]

def random_user_agent():
    return random.choice(user_agents())