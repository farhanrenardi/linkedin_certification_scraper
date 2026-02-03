import re
from fastapi import FastAPI
from playwright.async_api import Route

from linkedin_scraper.models import LinkedInRequest, CertificateItem
from linkedin_scraper.browser import launch_browser, new_context, apply_stealth, connect_over_cdp
from linkedin_scraper.cookies_auth import load_cookies, apply_cookies, check_login_status
from linkedin_scraper.navigation import (
    goto_with_retry,
    human_behavior,
    smooth_scroll_to,
    stabilize_detail_view,
    warm_up_scroll,
    deep_scroll,
    random_delay,
)
from linkedin_scraper.selectors import find_cert_section, find_show_all_button
from linkedin_scraper.extraction import extract_items
from linkedin_scraper.response import build_response, build_error
from linkedin_scraper.config import COOKIES_FILE, random_user_agent, BLOCK_IMAGES, USE_CDP, CDP_URL
from linkedin_scraper.logging import save_debug_files

app = FastAPI()

@app.post("/scrape/linkedin")
async def scrape_linkedin(data: LinkedInRequest):
    if not data.url or "linkedin.com" not in data.url:
        return {"url": data.url, "found": False, "error": "Invalid URL"}

    extracted_certs = []
    debug_msg = []
    cookies_loaded = False
    debug_files = None

    browser = None
    context = None
    page = None

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
        # Launch browser and context via modular helpers
        browser = await launch_browser(headless=(data.headless if data.headless is not None else True), proxy=data.proxy)
        context = await new_context(browser, locale="en-US", timezone_id="Asia/Jakarta", user_agent=random_user_agent())
        await apply_stealth(context)

        # Load and apply cookies only when we manage the context
        try:
            cookies = await load_cookies(COOKIES_FILE)
            cookies_loaded, has_li_at = await apply_cookies(context, cookies)
            if not has_li_at:
                print("⚠️ WARNING: li_at cookie not found. Auth will likely fail.")
        except Exception as e:
            print(f"⚠️ Cookie load error: {e}")

    async def _wire_blockers(p):
        if BLOCK_IMAGES and not data.debug:
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
        if browser:
            try:
                if not use_cdp:
                    await browser.close()
            except Exception:
                pass

    page = await context.new_page()
    await _wire_blockers(page)

    try:
        print(f"🚀 Opening: {data.url}")

        # Navigate dengan retry
        ok, err = await goto_with_retry(page, data.url, timeout_ms=max(20000, data.max_wait), tries=2)
        if not ok:
            print(f"❌ Navigation failed: {err}")
            return build_error(data, f"Navigation failed: {err}", debug_msg)
        if data.debug:
            await save_debug_files(page, "landing")

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
                ok, err = await goto_with_retry(page, data.url, timeout_ms=max(20000, data.max_wait), tries=2)
                if not ok:
                    return build_error(data, f"Navigation failed after CDP failover: {err}", debug_msg)
                if data.debug:
                    await save_debug_files(page, "landing_cdp")
            else:
                debug_msg.append("DOM_EMPTY_NO_FAILOVER")

        # 2. Check Login Status
        is_guest, login_debug = await check_login_status(page)
        debug_msg.extend(login_debug)

        if is_guest:
            print("⚠️ GUEST MODE - Limited access")
            debug_msg.append("GUEST_MODE")
            if data.debug:
                await save_debug_files(page, "guest_mode")
        else:
            print("✓ Logged in successfully")
            debug_msg.append("LOGGED_IN")

        # Human behavior simulation + warm-up scroll to trigger lazy load
        await human_behavior(page)
        await warm_up_scroll(page)
        # Additional deep scroll to force lazy-load sections
        await deep_scroll(page)

        # Direct detail-page handling to avoid missing items on /details pages
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

                # Scroll the main container to load more items if paginated
                try:
                    for _ in range(6):
                        await page.evaluate("document.querySelector('main')?.scrollBy(0, 1200)")
                        await page.wait_for_timeout(400)
                except Exception:
                    pass

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
                debug_files = await save_debug_files(page, "detail_direct_empty")

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

        # Optional: preview headings (kept minimal to avoid noisy logs)

        section = None
        section_found = False

        # If detail_only requested, jump straight to detail pages
        if not is_guest and data.detail_only:
            base_url = re.sub(r"[?#].*", "", data.url.rstrip("/"))
            for detail_url in [f"{base_url}/details/certifications/", f"{base_url}/details/licenses/"]:
                try:
                    await page.goto(detail_url, timeout=max(20000, data.max_wait), wait_until="networkidle")
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
                    await save_debug_files(page, "error_page")
                await browser.close()
                return build_error(data, "LinkedIn returned an error page (possible block/authwall)", debug_msg)
        except Exception:
            pass

        if section_found and section:
            print("✅ Certificate section located!")

            # Scroll ke section
            await smooth_scroll_to(page, section)

            scraped_details = False

            # Try to scrape from section FIRST before clicking show-all
            print("   Scraping from main section...")
            try:
                extracted_certs = [
                    i.dict() for i in await extract_items(page, "li, div[data-view-name='profile-component-entity']", "MainView", root=section, require_visible=False)
                ]
                print(f"   Got {len(extracted_certs)} certificates from MainView")
                debug_msg.append(f"Scraped:MainView:{len(extracted_certs)}")
                
                # If nothing, try broader selector
                if not extracted_certs:
                    print("   MainView empty, trying MainViewWide...")
                    extracted_certs = [
                        i.dict() for i in await extract_items(page, "li, div", "MainViewWide", root=section, require_visible=False)
                    ]
                    print(f"   Got {len(extracted_certs)} certificates from MainViewWide")
                    debug_msg.append(f"Scraped:MainViewWide:{len(extracted_certs)}")
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

            # Only skip show-all if we have certificates AND there's NO show-all button
            # If show-all button exists, always click it to get all certificates
            if extracted_certs and len(extracted_certs) > 0 and not has_show_all_btn:
                print(f"   ✅ Found {len(extracted_certs)} certs in MainView, no show-all button detected, skipping")
                debug_msg.append("SkipShowAll:NoMoreBtn")
            elif has_show_all_btn and not is_guest:
                show_all_btn = await find_show_all_button(section)

                if show_all_btn and await show_all_btn.count() > 0:
                    print(f"   ℹ️ Found {len(extracted_certs)} certs, but 'Show all' button exists, clicking...")
                    print("🔥 Attempting to expand details...")
                    try:
                        current_url = page.url
                        href_backup = await show_all_btn.get_attribute("href")
                        await show_all_btn.scroll_into_view_if_needed()
                        try:
                            await show_all_btn.click(timeout=min(12000, data.max_wait))
                        except Exception:
                            if href_backup:
                                await page.goto(
                                    f"https://www.linkedin.com{href_backup}",
                                    timeout=max(15000, data.max_wait // 2),
                                )
                        # Use domcontentloaded instead of networkidle to avoid timeout on infinite scroll
                        try:
                            await page.wait_for_load_state("domcontentloaded", timeout=max(10000, data.max_wait // 2))
                        except Exception:
                            print(f"⚠️ Page load timeout, continuing anyway...")
                            debug_msg.append("PageLoadTimeout")
                        
                        await page.wait_for_timeout(1500)  # Brief pause for rendering

                        # Check if redirected to external domain (e.g., Credly)
                        if "linkedin.com" not in page.url:
                            print(f"   🚫 External redirect detected: {page.url[:80]}")
                            debug_msg.append("ExternalRedirect")
                            # Go back to LinkedIn profile
                            await page.goto(current_url, timeout=max(15000, data.max_wait))
                            await page.wait_for_timeout(1500)

                        if "details/certifications" in page.url or "details/licenses" in page.url:
                            print("   ✓ Details page loaded")
                            await human_behavior(page)
                            await stabilize_detail_view(page, data.max_wait)
                            try:
                                await page.wait_for_selector(
                                    "main li, main [role='listitem'], div[role='listitem']",
                                    timeout=data.max_wait,
                                )
                            except Exception:
                                debug_msg.append("WaitDetailItemsTimeout")
                            try:
                                item_count = await page.locator("main li, main [role='listitem'], div[role='listitem']").count()
                                print(f"   Detail items detected: {item_count}")
                                debug_msg.append(f"DetailItems:{item_count}")
                            except Exception:
                                pass
                            extracted_certs = [
                                i.dict()
                                for i in await extract_items(
                                    page, "li", "DetailView", require_visible=False, root=page.locator("main ul").first
                                )
                            ]
                            scraped_details = True
                            debug_msg.append("Scraped: DetailView")
                            if data.debug and not extracted_certs:
                                await save_debug_files(page, "detail_empty")
                        else:
                            # If click failed but URL already moved to details by other means
                            if "details/" in page.url:
                                await human_behavior(page)
                                await stabilize_detail_view(page, data.max_wait)
                                extracted_certs = [
                                    i.dict()
                                    for i in await extract_items(
                                        page, "li", "DetailView", require_visible=False, root=page.locator("main ul").first
                                    )
                                ]
                                scraped_details = True
                                debug_msg.append("Scraped: DetailView-NoClick")
                    except Exception as e:
                        print(f"   ⚠️ Show all click failed: {e}")
                        debug_msg.append(f"ShowAllError: {str(e)[:30]}")

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
                                extracted_certs = [
                                    i.dict()
                                    for i in await extract_items(
                                        page, "li", "DetailView", require_visible=False, root=page.locator("main ul").first
                                    )
                                ]
                                scraped_details = True
                                debug_msg.append("Scraped:DetailViewRetry")
                                if data.debug and not extracted_certs:
                                    await save_debug_files(page, "detail_empty_retry")
                            else:
                                if "details/" in page.url:
                                    await human_behavior(page)
                                    await stabilize_detail_view(page, data.max_wait)
                                    extracted_certs = [
                                        i.dict()
                                        for i in await extract_items(
                                            page, "li", "DetailView", require_visible=False, root=page.locator("main ul").first
                                        )
                                    ]
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
                    base_url = re.sub(r"[?#].*", "", data.url.rstrip("/"))
                    detail_urls = [
                        f"{base_url}/details/certifications/",
                        f"{base_url}/details/licenses/"
                    ]
                    for detail_url in detail_urls:
                        print(f"🔄 Trying fallback URL: {detail_url}")
                        try:
                            ok2, err2 = await goto_with_retry(page, detail_url, timeout_ms=max(20000, data.max_wait), tries=1)
                            if not ok2:
                                continue
                            await human_behavior(page)
                            await stabilize_detail_view(page, data.max_wait)
                            try:
                                await page.wait_for_selector(
                                    "main li, main [role='listitem'], div[role='listitem']",
                                    timeout=data.max_wait,
                                )
                            except Exception:
                                debug_msg.append("WaitDetailItemsTimeoutFB")
                            try:
                                item_count_fb = await page.locator("main li, main [role='listitem'], div[role='listitem']").count()
                                print(f"   Detail items detected (fallback): {item_count_fb}")
                                debug_msg.append(f"DetailItemsFB:{item_count_fb}")
                            except Exception:
                                pass
                            extracted_certs = [
                                i.dict()
                                for i in await extract_items(
                                    page, "main, div[role='main']", "DetailFallback", require_visible=False
                                )
                            ]
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

        if data.debug and len(extracted_certs) == 0:
            debug_files = await save_debug_files(page, "no_results")

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

@app.get("/health")
def health(): return {"status": "ok"}
