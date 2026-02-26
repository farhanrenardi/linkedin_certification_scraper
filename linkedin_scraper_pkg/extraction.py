import re
from typing import List
from playwright.async_api import Page, Locator
from .models import CertificateItem


def _is_help_or_prefs_link(url: str) -> bool:
    if not url:
        return False
    lowered = url.lower()
    return (
        "linkedin.com/help" in lowered
        or "linkedin.com/mypreferences" in lowered
        or "linkedin.com/legal" in lowered
        or "/help/" in lowered
        or "/mypreferences/" in lowered
    )


async def extract_new_layout_items(page: Page, source: str) -> List[CertificateItem]:
    """Extract certificates from LinkedIn's SDUI layout.

    Uses three strategies in order:
      A. ``see-license-button`` anchors  – walk up from each credential
         button to the cert-row div (the one that has a ``<figure>``
         child for the issuer logo) and parse its text.
      B. HR-separated list container – on the detail page the cert items
         live inside a div whose direct children alternate ``div / hr``.
         Find it via ``<hr>`` inside ``profile-certifications-details-view``
         and iterate the ``<div>`` children.
      C. Old ``lockup-view`` selector (backward compat).
    """
    results: List[CertificateItem] = []
    seen_names: set = set()

    # ------------------------------------------------------------------
    # Strategy A – see-license-button anchors
    # ------------------------------------------------------------------
    buttons = page.locator(
        '[data-view-name="license-certifications-see-license-button"]'
    )
    btn_count = await buttons.count()
    print(
        f"[extraction.py] Found {btn_count} see-license-button elements "
        f"(source: {source})"
    )

    if btn_count > 0:
        for i in range(btn_count):
            try:
                btn = buttons.nth(i)

                # Walk up from button to the cert-row container.
                # The cert-row is the nearest ancestor <div> that has a
                # <figure> direct child (the issuer logo).
                cert_row = btn.locator("xpath=ancestor::div[child::figure]")
                row_count = await cert_row.count()
                if row_count == 0:
                    # Fallback: just grab inner_text of everything
                    # five levels above the <a> button tag.
                    cert_row = btn
                    for _ in range(5):
                        cert_row = cert_row.locator("xpath=..")
                else:
                    cert_row = cert_row.first

                text_content = ""
                try:
                    text_content = await cert_row.inner_text()
                except Exception:
                    continue

                if not text_content or len(text_content.strip()) < 5:
                    continue

                # Credential verify link from the button <a> href
                verify_link = ""
                try:
                    href = await btn.get_attribute("href")
                    if href:
                        verify_link = (
                            href
                            if href.startswith("http")
                            else f"https://www.linkedin.com{href}"
                        )
                except Exception:
                    pass

                result = _parse_cert_text(
                    text_content, verify_link, source + "_newLayout"
                )
                if result and result.certificate_name not in seen_names:
                    seen_names.add(result.certificate_name)
                    results.append(result)
            except Exception as e:
                print(
                    f"[extraction.py] Error processing see-license button {i}: {e}"
                )
                continue

    # ------------------------------------------------------------------
    # Strategy B – HR-separated list container
    # ------------------------------------------------------------------
    if not results:
        try:
            detail_view = page.locator(
                '[data-view-name="profile-certifications-details-view"]'
            )
            if await detail_view.count() > 0:
                hrs = detail_view.locator("hr")
                hr_count = await hrs.count()
                print(
                    f"[extraction.py] Found {hr_count} <hr> separators "
                    f"in details view (source: {source})"
                )

                if hr_count >= 1:
                    # Parent of the first HR is the list container
                    list_container = hrs.first.locator("xpath=..")
                    cert_divs = list_container.locator("xpath=child::div")
                    div_count = await cert_divs.count()
                    print(
                        f"[extraction.py] {div_count} direct div children "
                        f"in list container"
                    )

                    for j in range(div_count):
                        try:
                            item = cert_divs.nth(j)
                            text_content = await item.inner_text()
                            if not text_content or len(text_content.strip()) < 10:
                                continue

                            # Try to find a credential link inside this item
                            verify_link = ""
                            try:
                                see_btn = item.locator(
                                    '[data-view-name="license-certifications-see-license-button"]'
                                )
                                if await see_btn.count() > 0:
                                    href = await see_btn.first.get_attribute("href")
                                    if href:
                                        verify_link = (
                                            href
                                            if href.startswith("http")
                                            else f"https://www.linkedin.com{href}"
                                        )
                            except Exception:
                                pass

                            result = _parse_cert_text(
                                text_content, verify_link, source + "_listContainer"
                            )
                            if result and result.certificate_name not in seen_names:
                                seen_names.add(result.certificate_name)
                                results.append(result)
                        except Exception:
                            continue
        except Exception as e:
            print(f"[extraction.py] HR-list extraction error: {e}")

    # ------------------------------------------------------------------
    # Strategy C – lockup-view selector (always runs as supplement)
    # ------------------------------------------------------------------
    # Some certs have lockup-view elements but no see-license-button.
    # Always run to supplement results from Strategy A.
    if True:
        lockups = page.locator(
            '[data-view-name="license-certifications-lockup-view"]'
        )
        count = await lockups.count()
        if count > 0:
            print(
                f"[extraction.py] Strategy C: {count} lockup-view elements "
                f"(source: {source})"
            )

        for i in range(count):
            try:
                lockup = lockups.nth(i)
                parent = lockup.locator("xpath=..")
                if await parent.count() == 0:
                    continue

                text_content = ""
                try:
                    text_content = await parent.inner_text()
                except Exception:
                    continue

                if not text_content or len(text_content.strip()) < 5:
                    continue

                company_link = ""
                try:
                    href = await lockup.get_attribute("href")
                    if href:
                        company_link = (
                            href
                            if href.startswith("http")
                            else f"https://www.linkedin.com{href}"
                        )
                except Exception:
                    pass

                result = _parse_cert_text(
                    text_content, company_link, source + "_newLayout"
                )
                if result and result.certificate_name not in seen_names:
                    seen_names.add(result.certificate_name)
                    results.append(result)
            except Exception as e:
                print(f"[extraction.py] Error processing lockup {i}: {e}")
                continue

    # ------------------------------------------------------------------
    # Strategy D – figure-based cert cards (supplement + fallback)
    # ------------------------------------------------------------------
    # Some certs have no see-license-button and no lockup-view.
    # They appear as divs with a <figure> (issuer logo) child.
    # Always runs to pick up certs missed by earlier strategies.
    if True:
        try:
            # Find divs inside main that have a direct figure child
            figure_parents = page.locator("main div:has(> figure)")
            fp_count = await figure_parents.count()
            print(
                f"[extraction.py] Strategy D: {fp_count} figure-parent divs "
                f"(source: {source})"
            )

            for k in range(fp_count):
                try:
                    card = figure_parents.nth(k)
                    text_content = ""
                    try:
                        text_content = await card.inner_text()
                    except Exception:
                        continue

                    if not text_content or len(text_content.strip()) < 5:
                        continue

                    # Only consider items that look like certs
                    # (must have "Issued" or "Credential ID" in text)
                    if not re.search(
                        r"Issued|Credential ID|Diterbitkan|ID Kredensial",
                        text_content,
                        re.I,
                    ):
                        continue

                    # Try to find credential link
                    verify_link = ""
                    try:
                        a_link = card.locator(
                            'a[href*="credential"], '
                            'a[href*="redir/redirect"], '
                            '[data-view-name="license-certifications-see-license-button"]'
                        )
                        if await a_link.count() > 0:
                            href = await a_link.first.get_attribute("href")
                            if href:
                                verify_link = (
                                    href
                                    if href.startswith("http")
                                    else f"https://www.linkedin.com{href}"
                                )
                    except Exception:
                        pass

                    result = _parse_cert_text(
                        text_content, verify_link, source + "_figureCard"
                    )
                    if result and result.certificate_name not in seen_names:
                        seen_names.add(result.certificate_name)
                        results.append(result)
                except Exception:
                    continue
        except Exception as e:
            print(f"[extraction.py] Strategy D error: {e}")

    return results


def _parse_cert_text(text: str, company_link: str, source: str) -> "CertificateItem | None":
    """Parse cert text block into a CertificateItem.
    
    Expected text format:
      Cert Name
      Issuer Name
      Issued Aug 2023
      Credential ID XXX
      Skills: ...  (skip)
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    
    # Stop at "Skills:" line — everything after is not cert info
    clean_lines = []
    for l in lines:
        if l.lower().startswith("skills:") or l.lower().startswith("attached media"):
            break
        clean_lines.append(l)
    
    if not clean_lines:
        return None
    
    cert_name = ""
    issuer = ""
    issue_date = ""
    expiry_date = ""
    cred_id = ""
    verify_link = ""
    
    # First line = certificate name
    cert_name = clean_lines[0]
    
    # Process remaining lines
    for j in range(1, len(clean_lines)):
        line = clean_lines[j]
        
        # Check for "Issued XXX" pattern
        m_issued = re.search(r"^Issued\s+(.+)", line, re.I)
        if m_issued:
            issue_date = m_issued.group(1).strip()
            # Check for "Issued Aug 2023 · Expires Dec 2025" pattern
            if "·" in issue_date:
                parts = issue_date.split("·")
                issue_date = parts[0].strip()
                if len(parts) > 1:
                    exp_part = parts[1].strip()
                    m_exp = re.search(r"Expire[sd]?\s+(.+)", exp_part, re.I)
                    if m_exp:
                        expiry_date = m_exp.group(1).strip()
                    elif "no expiration" in exp_part.lower():
                        expiry_date = "No Expiration Date"
            continue
        
        # Check for "Expires XXX" pattern
        m_exp = re.search(r"^Expire[sd]?\s+(.+)", line, re.I)
        if m_exp:
            expiry_date = m_exp.group(1).strip()
            continue
        
        if "no expiration" in line.lower():
            expiry_date = "No Expiration Date"
            continue
        
        # Check for "Credential ID XXX" pattern
        m_cred = re.search(r"^Credential ID\s*:?\s*(.+)", line, re.I)
        if m_cred:
            cred_id = m_cred.group(1).strip()
            continue
        
        # If nothing matched and we haven't set issuer, this is the issuer
        if not issuer:
            issuer = line
    
    # Validate cert name
    if not cert_name or len(cert_name) < 2:
        return None
    
    # Skip if cert_name looks like garbage
    if cert_name.lower() in ["show all", "show credential", "see credential"]:
        return None
    
    # If cert_name looks like a URL or LinkedIn internal action link,
    # fall back to the issuer name as the cert name
    if (
        re.match(r'^https?://', cert_name, re.I)
        or re.match(r'^www\.', cert_name, re.I)
        or 'linkedin.com/profile/add' in cert_name.lower()
    ):
        if issuer:
            cert_name = issuer
            issuer = ""
        else:
            return None
    
    # Use company link as verify_link if available
    if company_link and not _is_help_or_prefs_link(company_link):
        verify_link = company_link
    
    return CertificateItem(
        certificate_name=cert_name,
        credential_id=cred_id,
        issuer=issuer,
        issue_date=issue_date,
        expiry_date=expiry_date,
        verify_link=verify_link,
        source=source,
    )


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

            # Skip LinkedIn help/account/privacy links
            if _is_help_or_prefs_link(verify_link):
                continue

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
import re
from typing import List
from playwright.async_api import Page, Locator
from .models import CertificateItem


def _is_help_or_prefs_link(url: str) -> bool:
    if not url:
        return False
    lowered = url.lower()
    return (
        "linkedin.com/help" in lowered
        or "linkedin.com/mypreferences" in lowered
        or "linkedin.com/legal" in lowered
        or "/help/" in lowered
        or "/mypreferences/" in lowered
    )


async def extract_new_layout_items(page: Page, source: str) -> List[CertificateItem]:
    """Extract certificates from LinkedIn's new SDUI layout.
    
    DOM structure (per cert entry):
      <div>                                          ← lockup's immediate parent
        <a data-view-name="license-certifications-lockup-view" href="/company/...">
        <div>                                        ← sibling with cert text
          <p>Cert Name</p>
          <p>Issuer</p>
          <p>Issued Aug 2023</p>
          <p>Credential ID XXX</p>
          <div data-view-name="license-certifications-see-skills-button">...</div>
        </div>
      </div>
    """
    results: List[CertificateItem] = []
    
    lockups = page.locator('[data-view-name="license-certifications-lockup-view"]')
    count = await lockups.count()
    print(f"[extraction.py] Found {count} certification lockup views (source: {source})")
    
    if count == 0:
        return results
    
    for i in range(count):
        try:
            lockup = lockups.nth(i)
            
            # Get the lockup's immediate parent — this is the cert block
            parent = lockup.locator("xpath=..")
            if await parent.count() == 0:
                continue
            
            text_content = ""
            try:
                text_content = await parent.inner_text()
            except Exception:
                continue
            
            if not text_content or len(text_content.strip()) < 5:
                continue
            
            # Get company link from lockup href
            company_link = ""
            try:
                href = await lockup.get_attribute("href")
                if href:
                    company_link = href if href.startswith("http") else f"https://www.linkedin.com{href}"
            except Exception:
                pass
            
            result = _parse_cert_text(text_content, company_link, source + "_newLayout")
            if result:
                results.append(result)
        except Exception as e:
            print(f"[extraction.py] Error processing lockup {i}: {e}")
            continue
    
    return results


def _parse_cert_text(text: str, company_link: str, source: str) -> "CertificateItem | None":
    """Parse cert text block into a CertificateItem.
    
    Expected text format:
      Cert Name
      Issuer Name
      Issued Aug 2023
      Credential ID XXX
      Skills: ...  (skip)
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    
    # Stop at "Skills:" line — everything after is not cert info
    clean_lines = []
    for l in lines:
        if l.lower().startswith("skills:") or l.lower().startswith("attached media"):
            break
        clean_lines.append(l)
    
    if not clean_lines:
        return None
    
    cert_name = ""
    issuer = ""
    issue_date = ""
    expiry_date = ""
    cred_id = ""
    verify_link = ""
    
    # First line = certificate name
    cert_name = clean_lines[0]
    
    # Process remaining lines
    for j in range(1, len(clean_lines)):
        line = clean_lines[j]
        
        # Check for "Issued XXX" pattern
        m_issued = re.search(r"^Issued\s+(.+)", line, re.I)
        if m_issued:
            issue_date = m_issued.group(1).strip()
            # Check for "Issued Aug 2023 · Expires Dec 2025" pattern
            if "·" in issue_date:
                parts = issue_date.split("·")
                issue_date = parts[0].strip()
                if len(parts) > 1:
                    exp_part = parts[1].strip()
                    m_exp = re.search(r"Expire[sd]?\s+(.+)", exp_part, re.I)
                    if m_exp:
                        expiry_date = m_exp.group(1).strip()
                    elif "no expiration" in exp_part.lower():
                        expiry_date = "No Expiration Date"
            continue
        
        # Check for "Expires XXX" pattern
        m_exp = re.search(r"^Expire[sd]?\s+(.+)", line, re.I)
        if m_exp:
            expiry_date = m_exp.group(1).strip()
            continue
        
        if "no expiration" in line.lower():
            expiry_date = "No Expiration Date"
            continue
        
        # Check for "Credential ID XXX" pattern
        m_cred = re.search(r"^Credential ID\s*:?\s*(.+)", line, re.I)
        if m_cred:
            cred_id = m_cred.group(1).strip()
            continue
        
        # If nothing matched and we haven't set issuer, this is the issuer
        if not issuer:
            issuer = line
    
    # Validate cert name
    if not cert_name or len(cert_name) < 2:
        return None
    
    # Skip if cert_name looks like garbage
    if cert_name.lower() in ["show all", "show credential", "see credential"]:
        return None
    
    # Use company link as verify_link if available
    if company_link and not _is_help_or_prefs_link(company_link):
        verify_link = company_link
    
    return CertificateItem(
        certificate_name=cert_name,
        credential_id=cred_id,
        issuer=issuer,
        issue_date=issue_date,
        expiry_date=expiry_date,
        verify_link=verify_link,
        source=source,
    )


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

            # Skip LinkedIn help/account/privacy links
            if _is_help_or_prefs_link(verify_link):
                continue

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
