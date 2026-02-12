#!/usr/bin/env python3
"""
Diagnostic tool for LinkedIn Certification Scraper
Helps troubleshoot why scraping might not be working for a specific URL.
"""

import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from playwright.async_api import async_playwright
from linkedin_scraper_pkg.browser import apply_stealth
from linkedin_scraper_pkg.config import random_user_agent
from linkedin_scraper_pkg.selectors import find_cert_section
from linkedin_scraper_pkg.extraction import extract_items

async def diagnose_url(url: str, output_dir: str = "/tmp"):
    """
    Comprehensive diagnostic for a LinkedIn profile URL.
    
    Args:
        url: LinkedIn profile URL to diagnose
        output_dir: Directory to save screenshots and HTML (default: /tmp)
    """
    print("\n" + "="*80)
    print(f"LinkedIn Scraper Diagnostic Tool")
    print("="*80)
    print(f"\nTarget URL: {url}")
    print(f"Output directory: {output_dir}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\n" + "="*80 + "\n")
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Generate safe filename from URL
    safe_name = url.split("/")[-2] or url.split("/")[-3] or "profile"
    safe_name = safe_name.replace("?", "_").replace("&", "_")
    
    results = {
        "url": url,
        "timestamp": datetime.now().isoformat(),
        "steps": []
    }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=random_user_agent())
        await apply_stealth(context)
        page = await context.new_page()
        
        try:
            # Step 1: Load main profile page
            step = {"step": 1, "action": "Load main profile page"}
            print("Step 1: Loading main profile page...")
            
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(3)
                final_url = page.url
                step["status"] = "success"
                step["final_url"] = final_url
                print(f"  ✅ Loaded successfully")
                print(f"  📍 Final URL: {final_url}")
                
                if final_url != url.rstrip("/") + "/" and final_url != url.rstrip("/"):
                    print(f"  ⚠️  URL changed (possible redirect)")
                
            except Exception as e:
                step["status"] = "failed"
                step["error"] = str(e)
                print(f"  ❌ Failed to load: {str(e)[:100]}")
                results["steps"].append(step)
                return results
            
            results["steps"].append(step)
            
            # Step 2: Save screenshot and HTML
            step = {"step": 2, "action": "Save page content"}
            print("\nStep 2: Saving page content...")
            
            try:
                screenshot_file = output_path / f"{safe_name}_main.png"
                await page.screenshot(path=str(screenshot_file), full_page=True)
                print(f"  💾 Screenshot: {screenshot_file}")
                step["screenshot"] = str(screenshot_file)
                
                html_file = output_path / f"{safe_name}_main.html"
                html_content = await page.content()
                with open(html_file, "w", encoding="utf-8") as f:
                    f.write(html_content)
                print(f"  💾 HTML: {html_file}")
                step["html"] = str(html_file)
                step["status"] = "success"
                
            except Exception as e:
                step["status"] = "failed"
                step["error"] = str(e)
                print(f"  ⚠️  Could not save content: {str(e)[:100]}")
            
            results["steps"].append(step)
            
            # Step 3: Check for certificate section
            step = {"step": 3, "action": "Find certificate section"}
            print("\nStep 3: Looking for certificate section...")
            
            try:
                section, method = await find_cert_section(page)
                
                if section:
                    step["status"] = "found"
                    step["method"] = method
                    print(f"  ✅ Found section using method: {method}")
                    
                    # Get section text preview
                    section_text = await section.text_content()
                    step["text_preview"] = section_text[:200] if section_text else ""
                    print(f"  📄 Section preview: {section_text[:200]}...")
                    
                else:
                    step["status"] = "not_found"
                    step["method"] = method
                    print(f"  ❌ Certificate section not found (method: {method})")
                    
                    # Check if page has any certification-related keywords
                    page_text = await page.text_content("body")
                    keywords = ["certification", "certificate", "license", "credential"]
                    found_keywords = [kw for kw in keywords if kw.lower() in page_text.lower()]
                    
                    if found_keywords:
                        print(f"  🔍 Page contains keywords: {', '.join(found_keywords)}")
                        print(f"     This suggests certificates exist but section detection failed")
                    else:
                        print(f"  ℹ️  No certification keywords found in page")
                
            except Exception as e:
                step["status"] = "error"
                step["error"] = str(e)
                print(f"  ❌ Error during section search: {str(e)[:100]}")
            
            results["steps"].append(step)
            
            # Step 4: Try extraction if section found
            if section:
                step = {"step": 4, "action": "Extract certificates"}
                print("\nStep 4: Attempting to extract certificates...")
                
                try:
                    items = await extract_items(page, "", "Diagnostic", root=section)
                    step["status"] = "success"
                    step["count"] = len(items)
                    step["certificates"] = [
                        {
                            "name": item.certificate_name,
                            "issuer": item.issuer,
                            "issue_date": item.issue_date,
                        }
                        for item in items
                    ]
                    
                    if items:
                        print(f"  ✅ Extracted {len(items)} certificate(s):")
                        for i, item in enumerate(items, 1):
                            print(f"     {i}. {item.certificate_name}")
                            if item.issuer:
                                print(f"        Issuer: {item.issuer}")
                            if item.issue_date:
                                print(f"        Issued: {item.issue_date}")
                    else:
                        print(f"  ⚠️  Section found but no certificates extracted")
                        print(f"     This suggests extraction logic needs improvement")
                    
                except Exception as e:
                    step["status"] = "error"
                    step["error"] = str(e)
                    print(f"  ❌ Extraction failed: {str(e)[:100]}")
                
                results["steps"].append(step)
            
            # Step 5: Try details page
            step = {"step": 5, "action": "Try details page"}
            print("\nStep 5: Checking details page...")
            
            try:
                base_url = url.split("?")[0].rstrip("/")
                details_url = f"{base_url}/details/certifications/"
                print(f"  🔗 Attempting: {details_url}")
                
                await page.goto(details_url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(3)
                
                final_details_url = page.url
                step["attempted_url"] = details_url
                step["final_url"] = final_details_url
                
                if "details/certifications" in final_details_url:
                    step["status"] = "accessible"
                    print(f"  ✅ Details page accessible")
                    
                    # Save details page content
                    screenshot_file = output_path / f"{safe_name}_details.png"
                    await page.screenshot(path=str(screenshot_file), full_page=True)
                    print(f"  💾 Screenshot: {screenshot_file}")
                    step["screenshot"] = str(screenshot_file)
                    
                    # Try extraction on details page
                    items = await extract_items(page, "", "DetailsPage", root=page.locator("main"))
                    step["extracted_count"] = len(items)
                    
                    if items:
                        print(f"  ✅ Extracted {len(items)} certificate(s) from details page")
                    else:
                        print(f"  ⚠️  Details page loaded but extraction returned 0")
                    
                else:
                    step["status"] = "redirected"
                    print(f"  ⚠️  Redirected to: {final_details_url}")
                    print(f"     Details page requires authentication")
                
            except Exception as e:
                step["status"] = "error"
                step["error"] = str(e)
                print(f"  ❌ Failed to load details page: {str(e)[:100]}")
            
            results["steps"].append(step)
            
        finally:
            await browser.close()
    
    # Save diagnostic results
    result_file = output_path / f"{safe_name}_diagnostic.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    
    print("\n" + "="*80)
    print(f"Diagnostic complete!")
    print(f"Results saved to: {result_file}")
    print("="*80 + "\n")
    
    return results

async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 diagnose.py <linkedin_profile_url> [output_dir]")
        print("\nExample:")
        print("  python3 diagnose.py https://www.linkedin.com/in/username/")
        print("  python3 diagnose.py https://www.linkedin.com/in/username/ /tmp/diagnostics")
        sys.exit(1)
    
    url = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "/tmp"
    
    try:
        await diagnose_url(url, output_dir)
    except KeyboardInterrupt:
        print("\n\nDiagnostic interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
