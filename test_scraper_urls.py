#!/usr/bin/env python3
"""
Test script to validate scraper improvements with mock LinkedIn responses.
This script can be used when LinkedIn is accessible to test the real scraping.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from linkedin_scraper_pkg.models import LinkedInRequest
from scraper import scrape_linkedin

async def test_single_url(url, use_cdp=False):
    """Test a single LinkedIn profile URL"""
    print(f"\n{'='*80}")
    print(f"Testing: {url}")
    print(f"{'='*80}")
    
    req = LinkedInRequest(
        url=url,
        use_cdp=use_cdp,
        headless=True if not use_cdp else None,
        debug=True,
        max_wait=30000,
        click_show_all=True
    )
    
    result = await scrape_linkedin(req)
    return result

async def main():
    """Test all three provided LinkedIn profiles"""
    
    # Test URLs from the issue
    test_urls = [
        "https://www.linkedin.com/in/bella-harum-ashari-2ba7b7115/",
        "https://www.linkedin.com/in/dimas-ewin-ashari-b4aba9138/",
        "https://www.linkedin.com/in/najibfaqihfathan/",
    ]
    
    results = {}
    
    print("\n" + "="*80)
    print("LinkedIn Certification Scraper - Test Suite")
    print("="*80)
    print("\nTesting Mode: Without CDP (headless)")
    print("Note: Requires active internet connection to LinkedIn")
    print("\n" + "="*80)
    
    for url in test_urls:
        try:
            result = await test_single_url(url, use_cdp=False)
            results[url] = result
            
            # Print summary
            if result.get("found"):
                print(f"\n✅ SUCCESS: Found {result.get('total_certificates', 0)} certificates")
                if result.get("certificates_list") != "not found":
                    for cert in result.get("certificates_list", []):
                        print(f"   - {cert.get('certificate_name', 'Unknown')}")
            else:
                print(f"\n⚠️  No certificates found or error occurred")
                print(f"   Guest mode: {result.get('guest_mode', 'unknown')}")
                print(f"   Debug: {result.get('debug', 'N/A')}")
                
        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            results[url] = {"error": str(e), "traceback": traceback.format_exc()}
    
    # Save results
    output_file = Path("/tmp/linkedin_scraper_test_results.json")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    print("\n" + "="*80)
    print(f"Results saved to: {output_file}")
    print("="*80)
    
    # Summary
    success_count = sum(1 for r in results.values() if isinstance(r, dict) and r.get("found"))
    print(f"\nSummary: {success_count}/{len(test_urls)} profiles successfully scraped")
    
    return results

if __name__ == "__main__":
    try:
        results = asyncio.run(main())
        # Exit with appropriate code
        success_count = sum(1 for r in results.values() if isinstance(r, dict) and r.get("found"))
        sys.exit(0 if success_count > 0 else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
