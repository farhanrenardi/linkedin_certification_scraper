import os
import random


COOKIES_FILE = os.environ.get("LINKEDIN_COOKIES_PATH", "cookies.json")
SLOW_MO_MS = int(os.environ.get("SCRAPER_SLOW_MO_MS", "0"))
BLOCK_IMAGES = os.environ.get("SCRAPER_BLOCK_IMAGES", "true").lower() != "false"
USE_CDP = os.environ.get("SCRAPER_USE_CDP", "false").lower() in ["1", "true", "yes"]
CDP_URL = os.environ.get("SCRAPER_CDP_URL", "http://127.0.0.1:9222")


def user_agents():
    """Return a curated pool of desktop Chrome user agents.

    Rotating across a small, realistic set of user agents reduces the chance
    of fingerprinting correlating all requests to a single static UA.
    """
    return [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    ]


def random_user_agent():
    """Pick a random user agent from the pool.

    This function is purposely simple and predictable; callers can seed
    randomness externally if they need reproducibility in tests.
    """
    pool = user_agents()
    return random.choice(pool)
