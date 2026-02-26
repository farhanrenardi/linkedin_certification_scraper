#!/usr/bin/env python3
"""Test scraping a single URL from the test file."""
import asyncio
import json
import sys
sys.path.insert(0, ".")
from linkedin_scraper_pkg.models import LinkedInRequest
from linkedin_scraper_pkg.config import CDP_URL
from scraper import scrape_linkedin

async def test_single():
    # Test with mungki (expected 7 certs, previously only found 2)
    url = "https://www.linkedin.com/in/mungki-sulistiono-2ab60110/"
    print(f"Testing: {url}")
    req = LinkedInRequest(
        url=url,
        debug=True,
        headless=False,
        max_wait=30000,
        detail_only=False,
        use_cdp=True,
        cdp_url=CDP_URL,
    )
    result = await scrape_linkedin(req)
    print("\n\n=== RESULT ===")
    print(json.dumps(result, indent=2, default=str))

asyncio.run(test_single())
