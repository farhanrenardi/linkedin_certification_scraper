#!/usr/bin/env python3
"""
Helper script to save LinkedIn authentication state.
Opens a persistent browser window for you to log in to LinkedIn.
Cookies are automatically saved to browser_data/ directory.
Auto-detects when login is complete (no need to press Enter).
"""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright


async def main():
    print("🔐 Opening browser for LinkedIn login...")
    print("   Please log in to LinkedIn in the browser window.")
    print("   The script will auto-detect when you're logged in.\n")
    
    user_data_dir = Path("browser_data")
    
    p = await async_playwright().start()
    context = await p.chromium.launch_persistent_context(
        str(user_data_dir),
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
        viewport={"width": 1280, "height": 900},
        locale="en-US",
    )
    
    # Inject stealth
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
    )
    
    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto("https://www.linkedin.com/login")
    
    # Wait for user to log in - detect by URL change to feed or other logged-in page
    print("⏳ Waiting for login... (navigate to any LinkedIn page after login)")
    max_wait = 300  # 5 minutes
    for i in range(max_wait):
        await asyncio.sleep(2)
        try:
            url = page.url
            # Check if we're on a logged-in page
            if any(k in url for k in ["/feed", "/mynetwork", "/in/", "/messaging"]):
                # Double check - look for feed content or nav bar
                try:
                    has_nav = await page.locator("[data-test-id='nav-bar'], nav.global-nav, #global-nav").count()
                    if has_nav > 0 or "/feed" in url:
                        print(f"\n✅ Login detected! (URL: {url[:60]})")
                        break
                except:
                    pass
            if "/authwall" not in url and "/login" not in url and "/signup" not in url and "/checkpoint" not in url:
                # Might be logged in if not on auth pages
                await asyncio.sleep(3)
                url = page.url
                if "/authwall" not in url and "/login" not in url:
                    print(f"\n✅ Login detected! (URL: {url[:60]})")
                    break
        except Exception:
            pass
        if i % 15 == 0 and i > 0:
            print(f"   Still waiting... ({i*2}s elapsed)")
    
    # Wait a bit more for page to stabilize
    await asyncio.sleep(3)
    
    # Also save cookies.json for backward compatibility
    cookies = await context.cookies()
    linkedin_cookies = [c for c in cookies if "linkedin.com" in c.get("domain", "")]
    
    with open("cookies.json", "w", encoding="utf-8") as f:
        json.dump(linkedin_cookies, f, indent=2)
    
    # Save auth_state.json
    await context.storage_state(path="auth_state.json")
    
    li_at = [c for c in linkedin_cookies if c["name"] == "li_at"]
    print(f"\n📁 Cookies saved to browser_data/ (persistent)")
    print(f"📁 Saved cookies.json ({len(linkedin_cookies)} cookies)")
    print(f"📁 Saved auth_state.json")
    print(f"   li_at cookie: {'✅ Found' if li_at else '❌ Not found'}")
    
    await context.close()
    await p.stop()


if __name__ == "__main__":
    asyncio.run(main())
