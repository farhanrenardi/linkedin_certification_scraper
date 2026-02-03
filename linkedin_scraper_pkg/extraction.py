import re
from typing import List
from playwright.async_api import Page, Locator
from .models import CertificateItem


async def extract_items(
    page: Page,
    scope_selector: str,
    source: str,
    require_visible: bool = True,
    root: Page | Locator | None = None,
) -> List[CertificateItem]:
    """Extract certificate entries from the given scope.

    LinkedIn certificate items have a consistent structure:
    - Title: first t-bold or first span[aria-hidden]
    - Issuer: second span[aria-hidden] or company link text
    - Date: found in caption-wrapper
    - Skills: usually in separate section
    """
    results: List[CertificateItem] = []
    base = root or page

    # Find certificate item containers
    items = None
    
    # If scope_selector already contains comma-separated selectors, use it directly
    if "," in scope_selector:
        # Direct usage for multi-selectors like "li, div[data-view-name='profile-component-entity']"
        item_selectors = [scope_selector]
    else:
        # Legacy behavior for single selectors
        item_selectors = [
            "li.pvs-list__paged-list-item",      # Detail view paginated
            "li.artdeco-list__item",              # Static list items
            "li",                                  # Generic li
        ]
    
    for item_sel in item_selectors:
        try:
            candidate_items = base.locator(item_sel)
            count = await candidate_items.count()
            if count > 0:
                items = candidate_items
                break
        except Exception:
            continue

    if not items:
        return results

    count = await items.count()
    print(f"[extraction.py] Found {count} items with selector '{scope_selector}' (source: {source})")
    
    seen_names = set()  # Track seen certificate names to avoid duplicates
    
    for i in range(count):
        try:
            item = items.nth(i)
            
            # Skip non-visible items
            try:
                if require_visible and not await item.is_visible():
                    continue
            except Exception:
                pass

            # Skip zero-height items
            try:
                box = await item.bounding_box()
                if box and box.get("height", 0) < 8:
                    continue
            except Exception:
                pass

            text = await item.inner_text()
            if not text or len(text.strip()) < 5:
                continue

            lines = [l.strip() for l in text.split("\n") if l.strip()]
            
            # Filter garbage lines - AGGRESSIVE to avoid false positives
            garbage_patterns = [
                r"^(Show credential|See credential|Show all|Like|Share|View|Comment)$",
                r"^(Home|My Network|Jobs|Messaging|Notifications)$",
                r"^skills?:",  # Skills section header
                r"licenses.*certifications",  # Section header
                r"\.pdf$|\.png$|\.jpg$",  # Image/file extensions
                r"^(Message|Comment|Like|Share|Follow|Unfollow)$",  # Social actions
                r"^(For Business|Log in|Sign up|Help)$",  # Nav items
                r"^\d+\s+(new\s+)?notifications?$",  # Notification items
                r"^new\s+feed\s+updates",  # Feed items
            ]
            
            clean_lines = [l for l in lines if not any(re.search(p, l, re.I) for p in garbage_patterns) and len(l) > 1]
            if not clean_lines:
                continue

            # Prefer aria-hidden spans (often hold the real title) and avoid picking logo text
            try:
                aria_spans = await item.locator("span[aria-hidden='true']").all_inner_texts()
            except Exception:
                aria_spans = []

            candidate_names = []
            if aria_spans and aria_spans[0].strip():
                candidate_names.append(aria_spans[0].strip())
            candidate_names.extend(clean_lines)

            cert_name = candidate_names[0]
            if cert_name.lower().endswith("logo") and len(candidate_names) > 1:
                cert_name = candidate_names[1]

            # Skip items that are only logo labels
            if "logo" in cert_name.lower():
                continue
            
            # Skip if certificate name is too short or invalid
            if len(cert_name) < 5 or len(cert_name) > 500:
                continue
            
            # Skip person/comment interactions (e.g., "Name is Title at Company")
            if re.search(r"\s+is\s+", cert_name, re.I) and re.search(r"\s+at\s+", cert_name, re.I):
                continue
            
            # Skip if text looks like it's not a certificate
            bad_keywords = [
                "home", "network", "jobs", "messaging", "skills", "see all",
                "message", "notifications",
                "new feed", "for business", "log in", "sign up", "help",
                "comment", "follow", "unfollow", "commented", "reacted"
            ]
            if any(k in cert_name.lower() for k in bad_keywords):
                continue
            
            # Skip if we've already seen this certificate (deduplication)
            if cert_name in seen_names:
                print(f"  [SKIP DUPLICATE] {cert_name}")
                continue
            
            seen_names.add(cert_name)

            # aria_spans already retrieved above for title; reuse for issuer parsing

            # Extract issuer from spans
            # Usually: aria_spans[0] = title, aria_spans[1] = issuer
            issuer = ""
            if len(aria_spans) >= 2 and aria_spans[1]:
                candidate = aria_spans[1].strip()
                if candidate and candidate != cert_name:
                    issuer = candidate

            # If not found via spans, try company link
            if not issuer:
                try:
                    company_link = item.locator("a[href*='/company/']").first
                    if await company_link.count():
                        issuer = (await company_link.inner_text()).strip()
                except Exception:
                    pass

            # Extract dates
            issue_date = ""
            expiry_date = ""
            
            # Look for caption with date info
            try:
                captions = await item.locator(".pvs-entity__caption-wrapper span[aria-hidden='true']").all_inner_texts()
                for caption in captions:
                    caption = caption.strip()
                    if re.search(r"issued|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec", caption, re.I):
                        issue_date = caption
                    if re.search(r"expire|kedaluwarsa|berlaku sampai", caption, re.I):
                        expiry_date = caption
            except:
                pass

            # Fallback: extract from text lines if not found
            if not issue_date:
                for line in lines:
                    m = re.search(r"Issued\s*:?\s*(.+)", line, re.I)
                    if m:
                        issue_date = m.group(1).strip()
                        break

            if not expiry_date:
                for line in lines:
                    if re.search(r"Expire|kedaluwarsa", line, re.I):
                        m = re.search(r"Expire[sd]?\s*:?\s*(.+)", line, re.I)
                        if m:
                            expiry_date = m.group(1).strip()
                        elif "no expiration" in line.lower():
                            expiry_date = "No Expiration Date"
                        break

            # Extract credential ID
            cred_id = ""
            for line in lines:
                m = re.search(r"Credential ID\s*:?\s*([A-Za-z0-9\-\./:]+)", line, re.I)
                if m:
                    cred_id = m.group(1)
                    break

            # Extract verify link
            verify_link = ""
            try:
                # Look for credential/verify links
                links = item.locator("a[href]")
                link_count = await links.count()
                for j in range(link_count):
                    link = links.nth(j)
                    link_text = await link.inner_text()
                    if "credential" in link_text.lower() or "verify" in link_text.lower():
                        href = await link.get_attribute("href")
                        if href:
                            verify_link = href if href.startswith("http") else f"https://www.linkedin.com{href}"
                            break
                
                # Fallback: get first external link
                if not verify_link and link_count > 0:
                    href = await links.first.get_attribute("href")
                    if href and href.startswith("http"):
                        verify_link = href
            except Exception:
                pass

            # Skip media/gallery items that are not actual certificates
            if verify_link and "multiple-media-viewer" in verify_link:
                continue

            # Skip endorsement/connection profiles (verify_link points to /in/ profile)
            if verify_link and "/in/" in verify_link and "miniProfileUrn" in verify_link:
                continue

            # Skip if issuer is just endorsement count ("· 3rd+", etc) with no real issuer/date/credential
            if issuer and issuer.startswith("·") and not issue_date and not cred_id and not expiry_date:
                continue

            results.append(
                CertificateItem(
                    certificate_name=cert_name,
                    credential_id=cred_id,
                    issuer=issuer,
                    issue_date=issue_date,
                    expiry_date=expiry_date,
                    verify_link=verify_link,
                    source=source,
                )
            )
        except Exception:
            # Skip problematic items and continue
            continue

    return results
