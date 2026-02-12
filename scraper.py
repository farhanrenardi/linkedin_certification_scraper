# FILE: scraper.py
#!/usr/bin/env python3
"""
LinkedIn Certificate Scraper - Savage & Adaptive Edition
"""

import asyncio
import sys
import json
import argparse
import traceback
import random

from linkedin_scraper_pkg.models import LinkedInRequest, CertificateItem
from linkedin_scraper_pkg.browser import launch_browser, new_context, apply_stealth, connect_over_cdp
from linkedin_scraper_pkg.cookies_auth import load_cookies, apply_cookies, check_login_status
from linkedin_scraper_pkg.navigation import goto_with_retry, random_delay
from linkedin_scraper_pkg.extraction import extract_items
from linkedin_scraper_pkg.response import build_response, build_error
from linkedin_scraper_pkg.config import COOKIES_FILE, random_user_agent, USE_CDP, CDP_URL
from linkedin_scraper_pkg.selectors import find_cert_section, find_show_all_button

# --- UTILS ---

async def aggressive_scroll(page):
    """Scroll 'Shake' untuk memaksa Lazy Loading LinkedIn."""
    print("   📜 Aggressive Scroll initiated...")
    
    # Scroll to top first to ensure we start from a known position
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(0.5)
    
    # Scroll ke bawah bertahap dengan lebih banyak steps
    for i in range(5):
        await page.mouse.wheel(0, 800)
        await asyncio.sleep(0.7)
    
    # Scroll ke paling bawah
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await asyncio.sleep(2)
    
    # Scroll sedikit ke atas (trik ajaib untuk memicu elemen yang stuck)
    await page.mouse.wheel(0, -500)
    await asyncio.sleep(1)
    
    # Balik ke bawah
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await asyncio.sleep(2)
    
    # Extra scroll to middle to trigger any lazy content
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
    await asyncio.sleep(1)
    
    # Back to bottom
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await asyncio.sleep(2)
    
    print("   ✅ Scroll finished.")
    await asyncio.sleep(3)  # Extra wait untuk render full DOM setelah scroll

async def safe_close(page=None, browser=None, use_cdp=False):
    if page: 
        try: await page.close()
        except: pass
    if browser and not use_cdp: 
        try: await browser.close()
        except: pass

async def scrape_attempt(page, data, is_guest):
    """
    Logika Scraping Adaptif: 
    1. Coba Direct Link Detail (Paling bersih).
    2. Jika gagal/redirect, Scan Profile Utama.
    3. Jika ketemu tombol 'Show all', klik dan scan lagi.
    """
    extracted = []
    logs = []

    # 1. Bersihkan URL
    base_url = data.url.split("?")[0].rstrip("/")

    # STRATEGY 1: Direct to Details
    details_url = f"{base_url}/details/certifications/"
    print(f"   🔄 STRATEGY 1: Direct Attack -> {details_url}")
    ok, err = await goto_with_retry(page, details_url, data.max_wait)
    if not ok:
        logs.append(f"GotoErr:{err[:30]}")
    await aggressive_scroll(page)

    # Check if really on details (no redirect)
    if "details/certifications" in page.url:
        print("   ✅ Landed on Details Page.")
        items = await extract_items(page, "", "DetailView", root=page.locator("main"))
        extracted += items
        if items: 
            return extracted, is_guest, logs
        else:
            print("   ⚠️ Details page loaded but extraction returned 0. Trying harder...")
    else:
        print("   ⚠️ Redirect detected. Details page not accessible.")

    # STRATEGY 2: Fallback to Main Profile
    print(f"   🔄 STRATEGY 2: Fallback to Main Profile -> {base_url}")
    await goto_with_retry(page, base_url, data.max_wait)
    await aggressive_scroll(page)

    section, method = await find_cert_section(page)
    if section:
        print(f"   ✅ Section Found via: {method}")
        items = await extract_items(page, "", f"MainProfile_{method}", root=section)
        extracted += items
        if items: return extracted, is_guest, logs

    # STRATEGY 3: Click "Show All" if exists
    if data.click_show_all and section:
        btn = await find_show_all_button(section)
        if btn:
            print("   🔄 Clicking 'Show All'...")
            await btn.click()
            await asyncio.sleep(2)  # Wait for load
            await aggressive_scroll(page)
            items = await extract_items(page, "", "ShowAllView")
            extracted += items

    return extracted, is_guest, logs

async def scrape_linkedin(data: LinkedInRequest) -> dict:
    debug_msg = [f"Headless:{data.headless}", f"Proxy:{data.proxy}", f"UseCDP:{data.use_cdp}"]
    browser = None
    context = None
    cookies_loaded = False
    is_guest = True

    if data.use_cdp:
        print(f"🚀 Connecting via CDP: {data.cdp_url}")
        browser = await connect_over_cdp(data.cdp_url or CDP_URL)
        # PERBAIKAN: Hilangkan 'await' karena browser.contexts[0] bukan awaitable
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
    else:
        browser = await launch_browser(headless=data.headless or True, proxy=data.proxy)
        context = await new_context(browser, user_agent=random_user_agent())
        await apply_stealth(context)
        try:
            cookies = await load_cookies(COOKIES_FILE)
            cookies_loaded, _ = await apply_cookies(context, cookies)
        except: pass

    try:
        page = await context.new_page()
        
        # RETRY LOOP (Retry 2x max)
        MAX_RETRIES = 2
        for attempt in range(1, MAX_RETRIES + 1):
            print(f"\n⚡ ATTEMPT {attempt}/{MAX_RETRIES}")
            
            if attempt == 1:
                try:
                    await page.goto("https://www.linkedin.com", timeout=15000)
                    is_guest, _ = await check_login_status(page)
                    if is_guest: print("⚠️ Warning: Guest Mode Detected (Login required for best results)")
                except: pass

            certs, guest_stat, logs = await scrape_attempt(page, data, is_guest)
            extracted_certs = certs
            
            if extracted_certs:
                print(f"🎉 SUCCESS: Found {len(certs)} items.")
                break
            else:
                print("⚠️ No items found. Retrying with fresh reload...")
                await asyncio.sleep(2)
        
        return build_response(data, [CertificateItem(**i) for i in extracted_certs], cookies_loaded, is_guest, debug_msg)

    except Exception as e:
        print(f"❌ Fatal Error: {e}")
        traceback.print_exc()
        return build_error(data, str(e), debug_msg)
    finally:
        await safe_close(page, browser, data.use_cdp)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--output", "-o")
    parser.add_argument("--cookies")
    args = parser.parse_args()
    
    if args.cookies:
        import linkedin_scraper_pkg.config as c
        c.COOKIES_FILE = args.cookies
        
    req = LinkedInRequest(url=args.url, use_cdp=True, cdp_url=CDP_URL, debug=True)
    res = asyncio.run(scrape_linkedin(req))
    
    print(json.dumps(res, indent=2))
    if args.output:
        with open(args.output, "w") as f: json.dump(res, f, indent=2)

if __name__ == "__main__":
    main()