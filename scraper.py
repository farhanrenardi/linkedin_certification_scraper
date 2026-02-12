#!/usr/bin/env python3
"""
LinkedIn Certificate Scraper - CLI Standalone Version

A command-line tool to scrape LinkedIn certification data from a user-provided profile URL.
Supports both local Playwright-launched browsers and remote CDP (Chrome DevTools Protocol) connections.

Usage:
    python scraper.py <LINKEDIN_URL> [OPTIONS]

Example:
    python scraper.py https://www.linkedin.com/in/johndoe/ --debug
    python scraper.py https://www.linkedin.com/in/johndoe/ --use-cdp --cdp-url http://localhost:9222
"""

import asyncio
import sys
import json
import argparse
import re
from pathlib import Path
from typing import Optional

from linkedin_scraper_pkg.models import LinkedInRequest, CertificateItem
from linkedin_scraper_pkg.browser import launch_browser, new_context, apply_stealth, connect_over_cdp, launch_persistent_context
from linkedin_scraper_pkg.cookies_auth import load_cookies, apply_cookies, check_login_status
from linkedin_scraper_pkg.navigation import (
    goto_with_retry,
    navigate_via_js,
    human_behavior,
    smooth_scroll_to,
    stabilize_detail_view,
    warm_up_scroll,
    deep_scroll,
    random_delay,
)
from linkedin_scraper_pkg.selectors import find_cert_section, find_show_all_button
from linkedin_scraper_pkg.extraction import extract_items, extract_new_layout_items
from linkedin_scraper_pkg.response import build_response, build_error
from linkedin_scraper_pkg.config import COOKIES_FILE, random_user_agent, BLOCK_IMAGES, USE_CDP, CDP_URL
from linkedin_scraper_pkg import scraper_logging


async def scrape_linkedin(data: LinkedInRequest) -> dict:
    """
    Scrape LinkedIn certificates from the provided profile URL.
    
    Args:
        data: LinkedInRequest object containing URL and scraping options
        
    Returns:
        Dictionary containing scraped certificates and metadata
    """
    if not data.url or "linkedin.com" not in data.url:
        return {"url": data.url, "found": False, "error": "Invalid URL"}

    extracted_certs = []
    debug_msg = []
    cookies_loaded = False
    debug_files = None

    browser = None
    context = None
    page = None

    def merge_cert_lists(primary: list[dict], secondary: list[dict]) -> list[dict]:
        """Merge two certificate lists, deduplicating by certificate_name.

        Prefer entries that have credential_id or verify_link.
        """
        combined = (primary or []) + (secondary or [])
        dedup: dict[str, dict] = {}
        for c in combined:
            if not isinstance(c, dict):
                continue
            name = (c.get("certificate_name") or "").strip()
            if not name:
                continue
            prev = dedup.get(name)
            score = int(bool(c.get("credential_id"))) + int(bool(c.get("verify_link")))
            prev_score = int(bool(prev and prev.get("credential_id"))) + int(bool(prev and prev.get("verify_link")))
            if prev is None or score >= prev_score:
                dedup[name] = c
        return list(dedup.values())

    async def extract_detail_items(label: str) -> list[dict]:
        """Extract detail items from multiple roots to handle layout changes."""
        combined: list[dict] = []
        
        # First try the new SDUI layout extraction (most reliable)
        try:
            new_layout_items = await extract_new_layout_items(page, label)
            if new_layout_items:
                print(f"      [extract_detail_items] {len(new_layout_items)} items from SDUI layout")
                combined = [i.dict() for i in new_layout_items]
                # SDUI extraction is authoritative; skip legacy fallbacks
                return combined
        except Exception as e:
            print(f"      [extract_detail_items] SDUI extraction error: {e}")
        
        # Legacy selectors as fallback only when SDUI found nothing
        roots = [
            page.locator("main"),
            page.locator("main ul"),
            page.locator("main div[role='list']"),
            page.locator(".scaffold-finite-scroll__content"),
            page.locator(".pvs-list__outer-container"),
        ]
        selectors = [
            "li.pvs-list__paged-list-item",
            "li.artdeco-list__item",
            "div[data-view-name='profile-component-entity']",
        ]
        for root in roots:
            for sel in selectors:
                try:
                    part = [
                        i.dict()
                        for i in await extract_items(
                            page,
                            sel,
                            label,
                            require_visible=False,
                            root=root,
                        )
                    ]
                    if part:
                        print(f"      [extract_detail_items] {len(part)} items from legacy selector")
                    combined = merge_cert_lists(combined, part)
                except Exception:
                    continue
        return combined

    async def scroll_detail_until_stable(max_rounds: int = 12) -> None:
        """Scroll likely containers until item count stops increasing."""
        stable_rounds = 0
        last_count = 0
        
        for rnd in range(max_rounds):
            # Scroll both main container and body
            try:
                await page.evaluate("document.querySelector('main')?.scrollBy(0, 1500)")
            except Exception:
                pass
            try:
                await page.evaluate("window.scrollBy(0, 1500)")
            except Exception:
                pass
            
            await page.wait_for_timeout(600)
            
            # Count items: both legacy and SDUI
            current = 0
            try:
                legacy = await page.locator("main li, main [role='listitem'], div[role='listitem']").count()
                sdui = await page.locator('[data-view-name="license-certifications-lockup-view"]').count()
                current = max(legacy, sdui)
            except Exception:
                pass
            
            print(f"      [scroll_detail] Round {rnd+1}: {current} items visible")
            
            if current == last_count:
                stable_rounds += 1
            else:
                stable_rounds = 0
            
            last_count = current
            
            if stable_rounds >= 3:  # Wait for 3 stable rounds
                print(f"      [scroll_detail] Stable after {rnd+1} rounds with {current} items")
                break

    async def expand_detail_list(max_clicks: int = 20) -> None:
        """Click "Show more" / "Load more" buttons in detail pages to load additional items."""
        consecutive_failures = 0
        for i in range(max_clicks):
            clicked = False
            try:
                # Try multiple button patterns - be very aggressive
                patterns = [
                    r"show\s+more|show\s+all|show\s+more\s+results|see\s+more|tampilkan\s+lebih",
                    r"load\s+more|muat\s+lebih|muat\s+selengkapnya",
                    r"view\s+more",
                ]
                for pattern in patterns:
                    try:
                        btns = page.get_by_role("button", name=re.compile(pattern, re.I))
                        btn_count = await btns.count()
                        if btn_count > 0:
                            # Take the first visible button
                            for j in range(btn_count):
                                btn = btns.nth(j)
                                try:
                                    if await btn.is_visible():
                                        await btn.scroll_into_view_if_needed()
                                        await btn.click(timeout=8000)
                                        print(f"      [expand_detail] Clicked button #{j} matching '{pattern}' (round {i+1})")
                                        await page.wait_for_timeout(1500)
                                        clicked = True
                                        consecutive_failures = 0
                                        break
                                except:
                                    continue
                            if clicked:
                                break
                    except:
                        continue
                
                if not clicked:
                    # Also try finding by text content with more variations
                    try:
                        text_patterns = [
                            "Load more", "Show more", "Show all", "View more",
                            "Tampilkan lebih", "Muat lebih", "Lihat selengkapnya"
                        ]
                        for text_pat in text_patterns:
                            load_more = page.locator(f"button:has-text('{text_pat}')")
                            if await load_more.count() > 0:
                                visible_count = 0
                                for idx in range(await load_more.count()):
                                    btn = load_more.nth(idx)
                                    try:
                                        if await btn.is_visible():
                                            await btn.scroll_into_view_if_needed()
                                            await btn.click(timeout=8000)
                                            print(f"      [expand_detail] Clicked '{text_pat}' (round {i+1})")
                                            await page.wait_for_timeout(1500)
                                            clicked = True
                                            consecutive_failures = 0
                                            break
                                    except:
                                        continue
                                if clicked:
                                    break
                    except:
                        pass
                
                if not clicked:
                    consecutive_failures += 1
                    if consecutive_failures >= 2:
                        print(f"      [expand_detail] No more buttons after {consecutive_failures} attempts, stopping")
                        break
            except Exception as e:
                consecutive_failures += 1
                print(f"      [expand_detail] Error: {e}")
                if consecutive_failures >= 2:
                    break


    async def try_detail_fallback(tag: str) -> list[dict]:
        """Navigate directly to details pages to capture full certificate list."""
        results: list[dict] = []
        try:
            base_url = re.sub(r"[?#].*", "", data.url).rstrip("/")
            detail_urls = [
                f"{base_url}/details/certifications/",
                f"{base_url}/details/licenses/",
            ]
            for detail_url in detail_urls:
                # Skip licenses page if certifications page already found results
                if results and "licenses" in detail_url:
                    print(f"      → Skipping {detail_url} (already found {len(results)} certs)")
                    break
                
                print(f"      → Trying: {detail_url}")
                ok2, err2 = await navigate_via_js(page, detail_url, timeout_ms=max(15000, data.max_wait))
                if not ok2:
                    print(f"      ✗ Navigation failed: {err2}")
                    continue

                # Quick check for error/404 pages
                await page.wait_for_timeout(2000)
                try:
                    body_text = await page.locator("body").inner_text()
                    if "page doesn't exist" in body_text.lower() or "page not found" in body_text.lower():
                        print(f"      ✗ Page doesn't exist, skipping")
                        debug_msg.append(f"Detail404:{detail_url.split('/')[-2]}")
                        continue
                except Exception:
                    pass
                
                # Check if URL actually loaded (didn't redirect back to profile/feed)
                if not ("details/" in page.url):
                    print(f"      ✗ Redirected away from detail page: {page.url}")
                    continue
                
                await human_behavior(page)
                await stabilize_detail_view(page, data.max_wait)
                
                # Moderate scrolling
                for scroll_round in range(2):
                    await scroll_detail_until_stable(max_rounds=6)
                    await expand_detail_list(max_clicks=10)
                    await page.wait_for_timeout(600)
                
                # Final scroll to bottom
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000)
                
                detail_certs = await extract_detail_items(tag)
                print(f"      ✓ Extracted {len(detail_certs)} certificates")
                if detail_certs:
                    results = merge_cert_lists(results, detail_certs)
        except Exception as e:
            print(f"      ✗ Detail fallback error: {e}")
            debug_msg.append(f"DetailFallbackErr:{str(e)[:30]}")
        return results

    # Decide whether to use CDP (real Chrome) or Playwright-launched Chromium
    use_cdp = USE_CDP or getattr(data, "use_cdp", False)
    cdp_url = getattr(data, "cdp_url", None) or CDP_URL

    if use_cdp:
        print(f"🚀 Connecting via CDP: {cdp_url}")
        try:
            browser = await connect_over_cdp(cdp_url)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            debug_msg.append("CDP_MODE")
        except Exception as e:
            print(f"❌ CDP connection failed: {e}. Falling back to launch_browser")
            use_cdp = False
            debug_msg.append("CDP_FAIL_FALLBACK")
    
    if not use_cdp:
        # Use persistent context as primary approach (preserves cookies automatically)
        user_data_dir = Path("browser_data")
        auth_state_file = Path("auth_state.json")
        use_persistent = True

        try:
            context = await launch_persistent_context(
                str(user_data_dir),
                headless=(data.headless if data.headless is not None else True),
                proxy=data.proxy,
            )
            await apply_stealth(context)
            browser = None  # persistent context does not have a separate browser
            cookies_loaded = True

            # Also apply cookies from file if they exist (for first-time setup)
            if not (user_data_dir / "Default" / "Cookies").exists():
                try:
                    if auth_state_file.exists():
                        import json as _json
                        with open(auth_state_file) as _f:
                            state = _json.load(_f)
                        if state.get("cookies"):
                            await context.add_cookies(state["cookies"])
                            debug_msg.append("AUTH_STATE_LOADED")
                    else:
                        cookies = await load_cookies(COOKIES_FILE)
                        cookies_loaded, has_li_at = await apply_cookies(context, cookies)
                        if not has_li_at:
                            print("⚠️ WARNING: li_at cookie not found. Auth will likely fail.")
                except Exception as e:
                    print(f"⚠️ Cookie load error: {e}")
        except Exception as e:
            print(f"⚠️ Persistent context failed: {e}, falling back to regular browser")
            use_persistent = False
            browser = await launch_browser(headless=(data.headless if data.headless is not None else True), proxy=data.proxy)
            if auth_state_file.exists():
                context = await browser.new_context(
                    storage_state=str(auth_state_file),
                    user_agent=random_user_agent(),
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                    timezone_id="Asia/Jakarta",
                )
                await apply_stealth(context)
                cookies_loaded = True
                debug_msg.append("AUTH_STATE_LOADED_FALLBACK")
            else:
                context = await new_context(browser, locale="en-US", timezone_id="Asia/Jakarta", user_agent=random_user_agent())
                await apply_stealth(context)
                try:
                    cookies = await load_cookies(COOKIES_FILE)
                    cookies_loaded, has_li_at = await apply_cookies(context, cookies)
                    if not has_li_at:
                        print("⚠️ WARNING: li_at cookie not found. Auth will likely fail.")
                except Exception as e:
                    print(f"⚠️ Cookie load error: {e}")

    async def _wire_blockers(p):
        if BLOCK_IMAGES and not data.debug:
            from playwright.async_api import Route
            async def _block_images(route: Route):
                await route.abort()
            await p.route("**/*.{png,jpg,jpeg,gif,svg,ico}", _block_images)

    async def _cleanup():
        # Always close the tab; close whole browser only when we launched it
        try:
            if page:
                await page.close()
        except Exception:
            pass
        try:
            if context:
                await context.close()
        except Exception:
            pass
        if browser:
            try:
                if not use_cdp:
                    await browser.close()
            except Exception:
                pass

    page = await context.new_page()
    await _wire_blockers(page)

    try:
        # Warm-up: visit LinkedIn feed first to establish session before profile
        print("🔑 Establishing LinkedIn session...")
        try:
            await page.goto("https://www.linkedin.com/feed/", timeout=max(15000, data.max_wait), wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            # Check if we ended up on authwall/login
            if any(k in page.url for k in ["authwall", "/login", "/signup"]):
                print("⚠️ Session warm-up hit authwall, continuing anyway...")
                debug_msg.append("WARMUP_AUTHWALL")
            else:
                print("✅ Session established")
                debug_msg.append("SESSION_OK")
        except Exception as e:
            print(f"⚠️ Session warm-up failed: {e}")
            debug_msg.append(f"WARMUP_ERR:{str(e)[:30]}")

        print(f"🚀 Opening: {data.url}")

        # Navigate via JS to bypass LinkedIn's SDUI client-side interception
        ok, err = await navigate_via_js(page, data.url, timeout_ms=max(20000, data.max_wait))
        if not ok:
            # Fallback to standard navigation
            print(f"⚠️ JS navigation failed ({err}), trying standard goto...")
            debug_msg.append("JS_NAV_FAILED")
            ok, err = await goto_with_retry(page, data.url, timeout_ms=max(20000, data.max_wait), tries=2)
            if not ok:
                print(f"❌ Navigation failed: {err}")
                return build_error(data, f"Navigation failed: {err}", debug_msg)

        # If redirected away from target, retry
        if any(k in page.url for k in ["authwall", "/login", "/signup"]) or ("/feed" in page.url and "/in/" in data.url):
            print("⚠️ Redirected away from profile, retrying...")
            debug_msg.append("REDIRECT_RETRY")
            await page.wait_for_timeout(2000)
            ok, err = await navigate_via_js(page, data.url, timeout_ms=max(20000, data.max_wait))
            if not ok:
                print(f"❌ Retry navigation failed: {err}")
                return build_error(data, f"Navigation retry failed: {err}", debug_msg)

        if data.debug:
            await scraper_logging.save_debug_files(page, "landing")

        # Wait a bit for page to stabilize
        await page.wait_for_timeout(2000)

        # Detect empty/blocked DOM early and fallback to CDP when available
        dom_empty = False
        try:
            sec_count = await page.locator("section").count()
            main_text = ""
            try:
                main_text = await page.locator("main").inner_text()
            except Exception:
                pass
            if sec_count == 0 or len(main_text.strip()) < 20:
                dom_empty = True
                print(f"⚠️ DOM appears empty (sections: {sec_count}, main_text: {len(main_text)})")
        except Exception:
            pass

        if dom_empty:
            debug_msg.append("DOM_EMPTY_PRIMARY")
            print("⚠️ DOM appears empty/blocked")
            if not use_cdp and USE_CDP:
                print("🔄 Retrying via CDP failover...")
                await browser.close()
                browser = await connect_over_cdp(cdp_url)
                context = browser.contexts[0] if browser.contexts else await browser.new_context()
                page = await context.new_page()
                await _wire_blockers(page)
                use_cdp = True
                debug_msg.append("CDP_FAILOVER")
                ok, err = await navigate_via_js(page, data.url, timeout_ms=max(20000, data.max_wait))
                if not ok:
                    return build_error(data, f"Navigation failed after CDP failover: {err}", debug_msg)
                if data.debug:
                    await scraper_logging.save_debug_files(page, "landing_cdp")
            else:
                debug_msg.append("DOM_EMPTY_NO_FAILOVER")

        # 2. Check Login Status
        is_guest, login_debug = await check_login_status(page)
        debug_msg.extend(login_debug)

        if is_guest:
            print("⚠️ GUEST MODE - Limited access")
            debug_msg.append("GUEST_MODE")
            if data.debug:
                await scraper_logging.save_debug_files(page, "guest_mode")
        else:
            print("✓ Logged in successfully")
            debug_msg.append("LOGGED_IN")

        # Human behavior simulation + warm-up scroll to trigger lazy load
        await human_behavior(page)
        await warm_up_scroll(page)
        # Additional deep scroll to force lazy-load sections
        await deep_scroll(page)

        # Direct detail-page handling to avoid missing items on /details pages
        import re
        is_detail_url = any(
            k in page.url or k in data.url for k in [
                "details/certifications",
                "details/licenses",
            ]
        )
        if is_detail_url:
            try:
                await stabilize_detail_view(page, data.max_wait)
                try:
                    await page.wait_for_selector(
                        "main ul li",
                        timeout=data.max_wait,
                    )
                except Exception:
                    debug_msg.append("DetailDirect:WaitTimeout")

                # Very aggressive scrolling
                print("   🔄 Aggressive detail page scrolling...")
                for scroll_round in range(8):
                    print(f"   [DetailDirect Scroll {scroll_round+1}/8]")
                    await scroll_detail_until_stable(max_rounds=20)
                    await expand_detail_list(max_clicks=15)
                    await page.wait_for_timeout(700)
                
                # Final bottom scroll
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1200)
                
                for _ in range(10):
                    await page.evaluate("document.querySelector('main')?.scrollBy(0, 2000)")
                    await page.wait_for_timeout(400)

                # Extract from all main > ul lists
                extracted_certs = []
                uls = page.locator("main ul")
                try:
                    ul_count = await uls.count()
                    debug_msg.append(f"DetailULs:{ul_count}")
                except Exception:
                    ul_count = 0
                for i_ul in range(ul_count):
                    root_ul = uls.nth(i_ul)
                    try:
                        part = [
                            i.dict()
                            for i in await extract_items(
                                page,
                                "li",
                                "DetailDirect",
                                require_visible=False,
                                root=root_ul,
                            )
                        ]
                        if part:
                            extracted_certs.extend(part)
                    except Exception:
                        continue

                # Deduplicate by certificate_name
                if extracted_certs:
                    dedup = {}
                    for c in extracted_certs:
                        name = c.get("certificate_name") or ""
                        if not name:
                            continue
                        # prefer entries with credential_id or verify_link
                        prev = dedup.get(name)
                        score = int(bool(c.get("credential_id"))) + int(bool(c.get("verify_link")))
                        prev_score = int(bool(prev and prev.get("credential_id"))) + int(bool(prev and prev.get("verify_link")))
                        if prev is None or score >= prev_score:
                            dedup[name] = c
                    extracted_certs = list(dedup.values())

                debug_msg.append(f"DetailDirect:{len(extracted_certs)}")
            except Exception as e:
                debug_msg.append(f"DetailDirectErr:{str(e)[:30]}")

            if data.debug and len(extracted_certs) == 0:
                debug_files = await scraper_logging.save_debug_files(page, "detail_direct_empty")

            debug_msg.append(f"FinalURL:{page.url}")
            print(f"✅ Scraping complete (detail direct): {len(extracted_certs)} certificates found")
            return build_response(
                data,
                [CertificateItem(**i) for i in extracted_certs],
                cookies_loaded,
                is_guest,
                debug_msg,
                debug_files,
            )

        # 3. FIND CERTIFICATE SECTION - Multiple strategies
        print("🔍 Searching for certificates section...")

        section = None
        section_found = False

        # If detail_only requested, jump straight to detail pages
        if not is_guest and data.detail_only:
            base_url = re.sub(r"[?#].*", "", data.url).rstrip("/")
            for detail_url in [f"{base_url}/details/certifications/", f"{base_url}/details/licenses/"]:
                try:
                    await navigate_via_js(page, detail_url, timeout_ms=max(20000, data.max_wait))
                    await random_delay(2, 4)
                    debug_msg.append("Jump:DetailOnly")
                    break
                except Exception:
                    continue

        section, strat = await find_cert_section(page)
        if section:
            section_found = True
            debug_msg.append(f"FindSection:{strat}")
        else:
            try:
                section_count = await page.locator("section").count()
                print(f"   Sections available before retry: {section_count}")
                debug_msg.append(f"SectionCount:{section_count}")
            except Exception:
                pass

        # Early error-page detection (e.g., "Something went wrong")
        try:
            err_locator = page.get_by_text("Something went wrong", exact=False)
            if await err_locator.count() > 0:
                debug_msg.append("ErrorPage:SomethingWentWrong")
                if data.debug:
                    await scraper_logging.save_debug_files(page, "error_page")
                await browser.close()
                return build_error(data, "LinkedIn returned an error page (possible block/authwall)", debug_msg)
        except Exception:
            pass

        if section_found and section:
            print("✅ Certificate section located!")

            # Scroll ke section
            await smooth_scroll_to(page, section)

            scraped_details = False

            # Try SDUI extraction first (most reliable on new LinkedIn layout)
            print("   Scraping from main section...")
            try:
                sdui_main = await extract_new_layout_items(page, "MainView")
                if sdui_main:
                    extracted_certs = [i.dict() for i in sdui_main]
                    print(f"   Got {len(extracted_certs)} certificates from MainView (SDUI)")
                    debug_msg.append(f"Scraped:MainViewSDUI:{len(extracted_certs)}")
            except Exception as e:
                print(f"   ⚠️ MainView SDUI extraction failed: {e}")
            
            # Fallback to legacy selectors if SDUI found nothing
            if not extracted_certs:
                try:
                    extracted_certs = [
                        i.dict() for i in await extract_items(page, "li, div[data-view-name='profile-component-entity']", "MainView", root=section, require_visible=False)
                    ]
                    print(f"   Got {len(extracted_certs)} certificates from MainView (legacy)")
                    debug_msg.append(f"Scraped:MainView:{len(extracted_certs)}")
                except Exception as e:
                    print(f"   ⚠️ MainView extraction failed: {e}")
                    debug_msg.append(f"MainViewError:{str(e)[:30]}")

            # Check if there's a "Show all" button indicating more certificates exist
            has_show_all_btn = False
            if not is_guest:
                try:
                    show_all_btn = await find_show_all_button(section)
                    has_show_all_btn = show_all_btn and await show_all_btn.count() > 0
                except Exception:
                    has_show_all_btn = False

            # ALWAYS try to get full list from details page when logged in
            # Main view typically only shows 3-4 certificates
            if not is_guest:
                print("   🔄 Navigating to details page for full certificate list...")
                
                # First try: click show-all button if found
                show_all_btn = await find_show_all_button(section)
                clicked_show_all = False

                if show_all_btn and await show_all_btn.count() > 0:
                    print(f"   ℹ️ Found 'Show all' button, clicking...")
                    try:
                        current_url = page.url
                        href_backup = await show_all_btn.get_attribute("href")
                        await show_all_btn.scroll_into_view_if_needed()
                        try:
                            await show_all_btn.click(timeout=min(12000, data.max_wait))
                            clicked_show_all = True
                        except Exception:
                            if href_backup:
                                full_href = href_backup if href_backup.startswith("http") else f"https://www.linkedin.com{href_backup}"
                                ok_nav, _ = await navigate_via_js(page, full_href, timeout_ms=max(15000, data.max_wait))
                                clicked_show_all = ok_nav
                        
                        if clicked_show_all:
                            try:
                                await page.wait_for_load_state("domcontentloaded", timeout=max(10000, data.max_wait // 2))
                            except Exception:
                                pass
                            
                            await page.wait_for_timeout(2000)

                            # Check if redirected to external domain
                            if "linkedin.com" not in page.url:
                                print(f"   🚫 External redirect detected: {page.url[:80]}")
                                debug_msg.append("ExternalRedirect")
                                ok_back, _ = await navigate_via_js(page, current_url, timeout_ms=15000)
                                await page.wait_for_timeout(1500)
                                clicked_show_all = False
                    except Exception as e:
                        print(f"   ⚠️ Show all click failed: {e}")
                        debug_msg.append(f"ShowAllError: {str(e)[:30]}")
                        clicked_show_all = False
                
                # If click worked and we're on details page, extract from it
                if clicked_show_all and "details/" in page.url:
                    print(f"   ✓ Details page loaded: {page.url}")
                    await human_behavior(page)
                    await stabilize_detail_view(page, data.max_wait)
                    
                    for scroll_round in range(4):
                        await scroll_detail_until_stable(max_rounds=10)
                        await expand_detail_list(max_clicks=10)
                        await page.wait_for_timeout(600)
                    
                    # Extra scrolls to bottom to ensure lazy-loaded items appear
                    for _ in range(5):
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await page.wait_for_timeout(800)
                    
                    detail_certs = await extract_detail_items("DetailView")
                    print(f"   Extracted {len(detail_certs)} certificates from detail page")
                    extracted_certs = merge_cert_lists(extracted_certs, detail_certs)
                    scraped_details = True
                    debug_msg.append(f"Scraped:DetailView:{len(detail_certs)}")
                
                # If click worked but URL didn't change to details, try SDUI on current page
                elif clicked_show_all:
                    print(f"   Show all clicked, URL: {page.url}")
                    await page.wait_for_timeout(2000)
                    await human_behavior(page)
                    
                    # Try SDUI extraction on current page (might have loaded more items)
                    try:
                        sdui_post_click = await extract_new_layout_items(page, "PostClick")
                        if sdui_post_click:
                            post_click_certs = [i.dict() for i in sdui_post_click]
                            print(f"   Got {len(post_click_certs)} certs after Show All click (SDUI)")
                            extracted_certs = merge_cert_lists(extracted_certs, post_click_certs)
                            scraped_details = True
                            debug_msg.append(f"Scraped:PostClick:{len(post_click_certs)}")
                    except Exception as e:
                        print(f"   ⚠️ Post-click SDUI extraction failed: {e}")
                
                # Fallback: direct navigation to details page
                if not scraped_details:
                    print("   ↪️ Directly navigating to details page...")
                    detail_certs = await try_detail_fallback("DetailDirect")
                    if detail_certs:
                        extracted_certs = merge_cert_lists(extracted_certs, detail_certs)
                        scraped_details = True
                        debug_msg.append(f"Scraped:DetailDirect:{len(detail_certs)}")

            # Fallback: Scrape from main view (if not already scraped and show-all didn't work)
            if not scraped_details and not extracted_certs:
                print("   Scraping from main section (fallback)...")
                if section:
                    extracted_certs = [
                        i.dict() for i in await extract_items(page, "li, div[data-view-name='profile-component-entity']", "MainViewFallback", root=section, require_visible=False)
                    ]
                    debug_msg.append(f"Scraped:MainViewFallback:{len(extracted_certs)}")
                    if not extracted_certs:
                        extracted_certs = [
                            i.dict() for i in await extract_items(page, "li, div", "MainViewWideFallback", root=section, require_visible=False)
                        ]
                        debug_msg.append(f"Scraped:MainViewWideFallback:{len(extracted_certs)}")
                else:
                    print("   ⚠️ No section found to scrape from")
                    debug_msg.append("NoSectionToScrape")
        else:
            print("❌ Certificate section not found!")
            debug_msg.append("SECTION_NOT_FOUND")

            # Retry after a deeper scroll in case the section was loaded late
            await deep_scroll(page, steps=8)
            section_retry, strat_retry = await find_cert_section(page)
            if section_retry:
                section = section_retry
                section_found = True
                debug_msg.append(f"RetryFindSection:{strat_retry}")
                print("✅ Certificate section found after retry!")
                await smooth_scroll_to(page, section)
                scraped_details = False

                if not is_guest:
                    show_all_btn = await find_show_all_button(section)

                    if show_all_btn and await show_all_btn.count() > 0:
                        print("🔥 Attempting to expand details (retry)...")
                        try:
                            href_backup = await show_all_btn.get_attribute("href")
                            await show_all_btn.scroll_into_view_if_needed()
                            try:
                                await show_all_btn.click(timeout=min(8000, data.max_wait))
                            except Exception:
                                if href_backup:
                                    await page.goto(
                                        f"https://www.linkedin.com{href_backup}",
                                        timeout=max(12000, data.max_wait // 2),
                                    )
                            # Use domcontentloaded instead of networkidle
                            try:
                                await page.wait_for_load_state("domcontentloaded", timeout=max(8000, data.max_wait // 3))
                            except Exception:
                                print(f"⚠️ Page load timeout (retry), continuing anyway...")
                                debug_msg.append("PageLoadTimeoutRetry")
                            
                            await page.wait_for_timeout(1500)

                            if "details/certifications" in page.url or "details/licenses" in page.url:
                                print("   ✓ Details page loaded (retry)")
                                await human_behavior(page)
                                await stabilize_detail_view(page, data.max_wait)
                                await expand_detail_list()
                                await scroll_detail_until_stable()
                                detail_certs = await extract_detail_items("DetailView")
                                extracted_certs = merge_cert_lists(extracted_certs, detail_certs)
                                scraped_details = True
                                debug_msg.append("Scraped:DetailViewRetry")
                                if data.debug and not extracted_certs:
                                    await scraper_logging.save_debug_files(page, "detail_empty_retry")
                            else:
                                if "details/" in page.url:
                                    await human_behavior(page)
                                    await stabilize_detail_view(page, data.max_wait)
                                    await expand_detail_list()
                                    await scroll_detail_until_stable()
                                    detail_certs = await extract_detail_items("DetailView")
                                    extracted_certs = merge_cert_lists(extracted_certs, detail_certs)
                                    scraped_details = True
                                    debug_msg.append("Scraped:DetailViewRetry-NoClick")
                        except Exception as e:
                            print(f"   ⚠️ Show all click failed (retry): {e}")
                            debug_msg.append(f"ShowAllErrorRetry:{str(e)[:30]}")

                if not scraped_details:
                    print("   Scraping from main section (retry)...")
                    if section:
                        extracted_certs = [
                            i.dict() for i in await extract_items(page, "li, div[data-view-name='profile-component-entity']", "MainViewRetry", root=section, require_visible=False)
                        ]
                        debug_msg.append(f"Scraped:MainViewRetry:{len(extracted_certs)}")
                        if not extracted_certs:
                            extracted_certs = [
                                i.dict() for i in await extract_items(page, "li, div", "MainViewRetryWide", root=section, require_visible=False)
                            ]
                            debug_msg.append(f"Scraped:MainViewRetryWide:{len(extracted_certs)}")

            # If still not found, continue with detail fallback below

            # Fallback: force navigate to details/certifications when logged in
            if not is_guest:
                try:
                    base_url = re.sub(r"[?#].*", "", data.url).rstrip("/")
                    detail_urls = [
                        f"{base_url}/details/certifications/",
                        f"{base_url}/details/licenses/"
                    ]
                    for detail_url in detail_urls:
                        # Skip licenses if certifications already found
                        if extracted_certs and "licenses" in detail_url:
                            break
                        
                        print(f"🔄 Trying fallback URL: {detail_url}")
                        try:
                            ok2, err2 = await navigate_via_js(page, detail_url, timeout_ms=max(15000, data.max_wait))
                            if not ok2:
                                continue
                            # Quick check for 404 / "page doesn't exist"
                            await page.wait_for_timeout(2000)
                            try:
                                body_text = await page.locator("body").inner_text()
                                if "page doesn't exist" in body_text.lower() or "page not found" in body_text.lower():
                                    print(f"   Page doesn't exist, skipping")
                                    continue
                            except Exception:
                                pass
                            
                            if "details/" not in page.url:
                                print(f"   Redirected away: {page.url}")
                                continue
                            
                            await human_behavior(page)
                            await stabilize_detail_view(page, data.max_wait)
                            await expand_detail_list()
                            await scroll_detail_until_stable()
                            
                            # Use extract_detail_items which tries SDUI first
                            extracted_certs = await extract_detail_items("DetailFallback")
                            print(f"   Extraction result: {len(extracted_certs)} certs")
                            
                            if extracted_certs:
                                debug_msg.append("Fallback:DetailPage")
                                section_found = True
                                break
                        except Exception as fe:
                            debug_msg.append(f"FallbackErr:{str(fe)[:30]}")
                except Exception as fe:
                    debug_msg.append(f"FallbackBuildErr:{str(fe)[:30]}")

            # Debug: List all sections
            try:
                all_sec = page.locator("section")
                count = await all_sec.count()
                debug_msg.append(f"TotalSections: {count}")

                # Capture preview of section headings for debugging
                previews = []
                for i in range(min(count, 10)):
                    sec = all_sec.nth(i)
                    try:
                        heading = await sec.locator("h2, h3, header, span").first.inner_text()
                    except Exception:
                        heading = ""
                    try:
                        snippet = await sec.inner_text()
                    except Exception:
                        snippet = ""
                    text = (heading or snippet).strip().replace("\n", " ")
                    if text:
                        previews.append(text[:80])
                if previews:
                    debug_msg.append("SectionPreview:" + " || ".join(previews))
            except Exception:
                pass

        debug_msg.append(f"FinalURL:{page.url}")

        # If only fallback items with no meaningful fields were gathered, treat as not found
        def _is_empty_fallback(item: dict) -> bool:
            return (
                "fallback" in item.get("source", "").lower()
                and not item.get("issuer")
                and not item.get("issue_date")
                and not item.get("expiry_date")
                and not item.get("credential_id")
                and not item.get("verify_link")
            )

        if extracted_certs and all(_is_empty_fallback(i) for i in extracted_certs):
            extracted_certs = []

        if extracted_certs:
            extracted_certs = merge_cert_lists(extracted_certs, [])

        if data.debug and len(extracted_certs) == 0:
            debug_files = await scraper_logging.save_debug_files(page, "no_results")

        print(f"✅ Scraping complete: {len(extracted_certs)} certificates found")
        return build_response(
            data,
            [CertificateItem(**i) for i in extracted_certs],
            cookies_loaded,
            is_guest,
            debug_msg,
            debug_files,
        )

    except Exception as e:
        print(f"❌ Fatal error: {e}")
        return build_error(data, str(e), debug_msg)

    finally:
        await _cleanup()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="LinkedIn Certificate Scraper - Scrape certificates from LinkedIn profiles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s https://www.linkedin.com/in/johndoe/
  %(prog)s https://www.linkedin.com/in/johndoe/ --debug
  %(prog)s https://www.linkedin.com/in/johndoe/ --use-cdp --cdp-url http://localhost:9222
  %(prog)s https://www.linkedin.com/in/johndoe/ --headless false --max-wait 30000
        """
    )
    
    parser.add_argument(
        "url",
        help="LinkedIn profile URL to scrape (e.g., https://www.linkedin.com/in/username/)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode to save screenshots and detailed logs"
    )
    parser.add_argument(
        "--headless",
        type=lambda x: x.lower() in ("true", "1", "yes"),
        default=True,
        help="Run browser in headless mode (default: true)"
    )
    parser.add_argument(
        "--max-wait",
        type=int,
        default=25000,
        help="Maximum wait time in milliseconds for page loads (default: 25000)"
    )
    parser.add_argument(
        "--use-cdp",
        action="store_true",
        help="Use Chrome DevTools Protocol (CDP) for remote browser connection"
    )
    parser.add_argument(
        "--cdp-url",
        default="http://127.0.0.1:9222",
        help="CDP endpoint URL (default: http://127.0.0.1:9222)"
    )
    parser.add_argument(
        "--detail-only",
        action="store_true",
        help="Only scrape from detail pages (/details/certifications/)"
    )
    parser.add_argument(
        "--proxy",
        help="Proxy URL to use for requests (e.g., http://proxy.example.com:8080)"
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path (JSON format). If not specified, prints to stdout"
    )
    parser.add_argument(
        "--cookies",
        help="Path to cookies.json file. If not specified, uses default location"
    )
    
    args = parser.parse_args()
    
    # Validate URL
    if not args.url.startswith("http"):
        args.url = f"https://{args.url}"
    
    if "linkedin.com" not in args.url:
        print(f"❌ Error: URL must be a LinkedIn profile URL")
        sys.exit(1)
    
    # Override cookies path if provided
    if args.cookies:
        import linkedin_scraper_pkg.config as config
        config.COOKIES_FILE = args.cookies
    
    # Create request object
    request_data = LinkedInRequest(
        url=args.url,
        debug=args.debug,
        headless=args.headless,
        max_wait=args.max_wait,
        use_cdp=args.use_cdp,
        cdp_url=args.cdp_url,
        detail_only=args.detail_only,
        proxy=args.proxy,
    )
    
    # Run scraper
    try:
        result = asyncio.run(scrape_linkedin(request_data))
        
        # Output result
        if args.output:
            with open(args.output, "w") as f:
                json.dump(result, f, indent=2)
            print(f"\n📁 Results saved to: {args.output}")
        else:
            print("\n📊 Scraping Results:")
            print(json.dumps(result, indent=2))
        
        # Exit with appropriate code
        if result.get("found", False) or result.get("certificates"):
            sys.exit(0)
        else:
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
