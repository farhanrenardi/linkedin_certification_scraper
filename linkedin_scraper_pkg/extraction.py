import re
from typing import List, Optional
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


def _looks_like_cert(text: str, verify_link: str) -> bool:
    """Check if a text block looks like a certificate entry."""
    text_lower = text.lower()
    
    # Must have at least one cert indicator
    has_issued = bool(re.search(r'\bissued\b|\bditerbitkan\b', text_lower))
    has_credential = bool(re.search(r'\bcredential\b|\bkredensial\b', text_lower))
    has_show_cred = "show credential" in text_lower or "lihat kredensial" in text_lower
    has_cert_link = bool(verify_link and (
        "learning/certificates" in verify_link.lower()
        or "credential" in verify_link.lower()
        or "credly.com" in verify_link.lower()
        or "redir/redirect" in verify_link.lower()
    ))
    has_expiry = bool(re.search(r'\bexpir\b|\bkedaluwarsa\b|\bno expiration\b', text_lower))
    
    return has_issued or has_credential or has_show_cred or has_cert_link or has_expiry


def _is_noise_text(text: str) -> bool:
    """Check if text block is likely noise (not a cert)."""
    text_lower = text.lower().strip()
    
    # Skip items that look like footer/navigation/social
    noise_phrases = [
        "show all", "load more", "more profiles",
        "questions?", "visit our help",
        "manage your account", "recommendation transparency",
        "select language", "explore premium", "people also viewed",
        "see all ", "message", "connect", "follow",
        "about", "accessibility", "talent solutions",
        "community guidelines", "careers", "marketing solutions",
        "privacy & terms", "ad choices", "advertising",
        "sales solutions", "mobile", "small business",
        "safety center", "linkedin corporation",
    ]
    for phrase in noise_phrases:
        if phrase in text_lower:
            print(f"[debug] _is_noise_text matched phrase: {phrase} in '{text_lower[:50]}'")
            return True
    
    # Skip items where the FIRST line is a follower count or just company names with followers
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if lines:
        first_line_lower = lines[0].lower()
        if re.search(r'^\d+[,.]?\d*\s+followers?$', first_line_lower):
            print(f"[debug] _is_noise_text matched first line follower: {first_line_lower}")
            return True
        
        # If it's a very short block (<= 2 lines) and one of them is followers, it's just a company card
        if len(lines) <= 2 and any(re.search(r'followers?$', l, re.I) for l in lines):
            print(f"[debug] _is_noise_text matched short company card")
            return True
    
    # Skip connection suggestions ("· 3rd+" or "· 2nd")
    if re.search(r'·\s*\d+(st|nd|rd|th)\+?\s*$', text_lower, re.MULTILINE):
        # But only if there's NO "Issued" data
        if not re.search(r'\bissued\b|\bditerbitkan\b', text_lower):
            print(f"[debug] _is_noise_text matched connection suggestion context")
            return True
    
    # Skip social interaction items ("1 reaction", "Like", "Comment", etc.)
    interaction_only = re.match(
        r'^(\d+\s+reactions?\s*|\d+\s+comments?\s*|like|comment|send|share|'
        r'repost|save|interested|celebrate|support|love|insightful|funny|'
        r'report|hide|copy link|embed this post|not interested)$',
        text_lower.split('\n')[0].strip()
    )
    if interaction_only:
        print(f"[debug] _is_noise_text matched interaction: {interaction_only.group(1)}")
        return True
    

    
    # Skip items that are just company names with follower counts 
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if len(lines) <= 2 and any(re.search(r'followers?$', l, re.I) for l in lines):
        return True
    
    return False


async def extract_new_layout_items(
    page: Page,
    source: str,
    scope: Optional[Locator] = None,
    strict_filter: bool = True,
) -> List[CertificateItem]:
    """Extract certificates from LinkedIn's current layout (2025+).

    Args:
        page: Playwright page.
        source: Label for debugging output.
        scope: Optional Locator to restrict search to (e.g., the cert section).
               If None, defaults to ``page.locator("main section")`` on detail
               pages or ``page.locator("main")`` elsewhere.
        strict_filter: Whether to enforce strict cert-like filtering. Use True
                       on the main profile page to avoid noise. Use False on
                       dedicated detail pages (`/details/certifications/`).

    Strategies (in priority order):
      E. HR-separated siblings – find <hr> elements in the cert container,
         then iterate the <div> siblings between them.
      F. Figure-card extraction – find divs with a direct <figure> child,
         parse their text.  Requires cert-like indicators (\"Issued\",
         credential link, etc.) to filter false positives.
      A–D. Legacy selectors kept as final fallbacks.
    """
    results: List[CertificateItem] = []
    seen_names: set = set()

    # Determine the search scope
    if scope is None:
        # Default to main to avoid accidental sidebar targeting
        search_root = page.locator("main")
    else:
        search_root = scope

    # ------------------------------------------------------------------
    # Strategy E – HR-separated siblings (primary for 2025+ layout)
    # ------------------------------------------------------------------
    try:
        hrs = search_root.locator("hr[role='presentation'], hr")
        hr_count = await hrs.count()
        print(
            f"[extraction.py] Strategy E: {hr_count} <hr> separators "
            f"(source: {source}, strict={strict_filter})"
        )

        if hr_count >= 1:
            list_container = hrs.first.locator("xpath=..")
            cert_divs = list_container.locator("xpath=child::div")
            div_count = await cert_divs.count()
            print(
                f"[extraction.py] Strategy E: {div_count} direct div children "
                f"in list container"
            )

            for j in range(div_count):
                try:
                    item = cert_divs.nth(j)
                    text_content = await item.inner_text()
                    if not text_content or len(text_content.strip()) < 10:
                        continue

                    if _is_noise_text(text_content):
                        continue

                    verify_link = ""
                    try:
                        cred_links = item.locator(
                            "a[href*='learning/certificates'], "
                            "a[href*='credential'], "
                            "a[href*='redir/redirect'], "
                            "a[href*='credly.com']"
                        )
                        if await cred_links.count() > 0:
                            href = await cred_links.first.get_attribute("href")
                            if href:
                                verify_link = (
                                    href
                                    if href.startswith("http")
                                    else f"https://www.linkedin.com{href}"
                                )
                    except Exception:
                        pass

                    # Must look like an actual certificate if strict
                    if strict_filter and not _looks_like_cert(text_content, verify_link):
                        continue

                    result = _parse_cert_text(
                        text_content, verify_link, source + "_hrList"
                    )
                    if result and result.certificate_name not in seen_names:
                        seen_names.add(result.certificate_name)
                        results.append(result)
                except Exception:
                    continue
    except Exception as e:
        print(f"[extraction.py] Strategy E error: {e}")

    # ------------------------------------------------------------------
    # Strategy F – Figure-card extraction (supplement)
    # ------------------------------------------------------------------
    try:
        figure_parents = search_root.locator("div:has(> figure)")
        fp_count = await figure_parents.count()

        if fp_count > 0:
            print(
                f"[extraction.py] Strategy F: {fp_count} figure-parent divs "
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

                if not text_content or len(text_content.strip()) < 10:
                    continue

                if _is_noise_text(text_content):
                    continue

                verify_link = ""
                try:
                    a_link = card.locator(
                        "a[href*='learning/certificates'], "
                        "a[href*='credential'], "
                        "a[href*='redir/redirect'], "
                        "a[href*='credly.com']"
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

                # Must look like an actual certificate if strict
                if strict_filter and not _looks_like_cert(text_content, verify_link):
                    continue

                result = _parse_cert_text(
                    text_content, verify_link, source + "_figureCard"
                )
                if result and result.certificate_name not in seen_names:
                    seen_names.add(result.certificate_name)
                    results.append(result)
            except Exception:
                continue
    except Exception as e:
        print(f"[extraction.py] Strategy F error: {e}")

    # ------------------------------------------------------------------
    # Strategy G – UL/LI elements fallback
    # ------------------------------------------------------------------
    if not results:
        try:
            lis = search_root.locator("li")
            li_count = await lis.count()
            if li_count > 0:
                print(
                    f"[extraction.py] Strategy G: {li_count} <li> elements "
                    f"(source: {source})"
                )
                for m in range(li_count):
                    try:
                        li = lis.nth(m)
                        text_content = ""
                        try:
                            text_content = await li.inner_text()
                        except Exception:
                            continue

                        if not text_content or len(text_content.strip()) < 10:
                            continue

                        if _is_noise_text(text_content):
                            continue

                        verify_link = ""
                        try:
                            a_link = li.locator(
                                "a[href*='learning/certificates'], "
                                "a[href*='credential'], "
                                "a[href*='redir/redirect'], "
                                "a[href*='credly.com']"
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

                        # Must look like an actual certificate if strict
                        if strict_filter and not _looks_like_cert(text_content, verify_link):
                            continue

                        result = _parse_cert_text(
                            text_content, verify_link, source + "_LI"
                        )
                        if result and result.certificate_name not in seen_names:
                            seen_names.add(result.certificate_name)
                            results.append(result)
                    except Exception:
                        continue
        except Exception as e:
            print(f"[extraction.py] Strategy G error: {e}")

    # ------------------------------------------------------------------
    # Strategy H - Single Root Fallback (for 1 cert without lists/figures)
    # ------------------------------------------------------------------
    if not results:
        try:
            text_content = await search_root.inner_text()
            if text_content and len(text_content.strip()) > 10:
                verify_link = ""
                try:
                    a_link = search_root.locator(
                        "a[href*='learning/certificates'], a[href*='credential'], "
                        "a[href*='redir/redirect'], a[href*='credly.com']"
                    )
                    if await a_link.count() > 0:
                        href = await a_link.first.get_attribute("href")
                        if href:
                            verify_link = href if href.startswith("http") else f"https://www.linkedin.com{href}"
                except Exception:
                    pass

                # Strip common header
                lines = [l.strip() for l in text_content.split('\n') if l.strip()]
                if lines and re.search(r'Licenses|Sertif', lines[0], re.I):
                    lines = lines[1:]
                
                if lines:
                    cleaned_text = '\n'.join(lines)
                    
                    if (not strict_filter) or _looks_like_cert(cleaned_text, verify_link):
                        if not _is_noise_text(cleaned_text):
                            result = _parse_cert_text(cleaned_text, verify_link, source + "_RootSingle")
                            if result and result.certificate_name not in seen_names:
                                print(f"[extraction.py] Strategy H matched single root document")
                                seen_names.add(result.certificate_name)
                                results.append(result)
        except Exception as e:
            print(f"[extraction.py] Strategy H error: {e}")

    # ------------------------------------------------------------------
    # Strategy A – see-license-button anchors (legacy, kept for compat)
    # ------------------------------------------------------------------
    if not results:
        buttons = page.locator(
            '[data-view-name="license-certifications-see-license-button"]'
        )
        btn_count = await buttons.count()
        if btn_count > 0:
            print(
                f"[extraction.py] Strategy A: {btn_count} see-license-button "
                f"elements (source: {source})"
            )

            for i in range(btn_count):
                try:
                    btn = buttons.nth(i)
                    cert_row = btn.locator("xpath=ancestor::div[child::figure]")
                    row_count = await cert_row.count()
                    if row_count == 0:
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
                except Exception:
                    continue

    # ------------------------------------------------------------------
    # Strategy B – HR-separated list container (legacy detail view)
    # ------------------------------------------------------------------
    if not results:
        try:
            detail_view = page.locator(
                '[data-view-name="profile-certifications-details-view"]'
            )
            if await detail_view.count() > 0:
                hrs = detail_view.locator("hr")
                hr_count = await hrs.count()
                if hr_count >= 1:
                    list_container = hrs.first.locator("xpath=..")
                    cert_divs = list_container.locator("xpath=child::div")
                    div_count = await cert_divs.count()

                    for j in range(div_count):
                        try:
                            item = cert_divs.nth(j)
                            text_content = await item.inner_text()
                            if not text_content or len(text_content.strip()) < 10:
                                continue

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
            print(f"[extraction.py] Strategy B error: {e}")

    # ------------------------------------------------------------------
    # Strategy C – lockup-view selector (legacy compat)
    # ------------------------------------------------------------------
    if not results:
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
                except Exception:
                    continue

    return results


def _parse_cert_text(text: str, company_link: str, source: str) -> "CertificateItem | None":
    """Parse cert text block into a CertificateItem.

    Expected text format (2025+ layout):
      Cert Name
      Issuer Name
      Issued Aug 2023
      Show credential
      Skills: ...  (skip)
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Stop at "Skills:" line or other non-cert content
    clean_lines = []
    for l in lines:
        lower = l.lower()
        if lower.startswith("skills:") or lower.startswith("attached media"):
            break
        # Also stop at skill icon text or skill association content
        if "skill" in lower and ("+" in l) and len(l) < 80:
            break
        clean_lines.append(l)

    if not clean_lines:
        print(f"[debug] _parse_cert_text returning None: no clean_lines for {text[:50]}")
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

        # Skip "Show credential" text
        if line.lower() in [
            "show credential", "lihat kredensial", "tampilkan kredensial",
        ]:
            continue

        # Check for "Issued XXX" pattern
        m_issued = re.search(r"^Issued\s+(.+)", line, re.I)
        if not m_issued:
            m_issued = re.search(r"^Diterbitkan\s+(.+)", line, re.I)
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
        if not m_cred:
            m_cred = re.search(r"^ID Kredensial\s*:?\s*(.+)", line, re.I)
        if m_cred:
            cred_id = m_cred.group(1).strip()
            continue

        # If nothing matched and we haven't set issuer, this is the issuer
        if not issuer:
            issuer = line

    # Validate cert name
    if not cert_name or len(cert_name) < 2:
        print(f"[debug] _parse_cert_text returning None: invalid cert_name '{cert_name}'")
        return None

    # Skip if cert_name looks like garbage
    skip_names = [
        "show all", "show credential", "see credential",
        "load more", "show more", "more profiles for you",
        "tampilkan semua", "lihat kredensial",
    ]
    if cert_name.lower().strip() in skip_names:
        print(f"[debug] _parse_cert_text returning None: cert_name in skip_names '{cert_name}'")
        return None

    # Skip if cert_name ends with "logo"
    if cert_name.lower().endswith("logo"):
        print(f"[debug] _parse_cert_text returning None: cert_name ends with logo '{cert_name}'")
        return None

    # Skip if cert_name is a URL or LinkedIn internal link
    if (
        re.match(r'^https?://', cert_name, re.I)
        or re.match(r'^www\.', cert_name, re.I)
        or 'linkedin.com/profile/add' in cert_name.lower()
    ):
        if issuer:
            cert_name = issuer
            issuer = ""
        else:
            print(f"[debug] _parse_cert_text returning None: cert_name is URL without issuer fallback '{cert_name}'")
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
    """Extract certificate entries from legacy layout selectors."""
    results: List[CertificateItem] = []
    base = root or page

    items = None
    item_selectors = [
        "li.pvs-list__paged-list-item",
        "li.artdeco-list__item",
        "li",
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

            try:
                if require_visible and not await item.is_visible():
                    continue
            except Exception:
                pass

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

            garbage_patterns = [
                r"^(Show credential|See credential|Show all|Like|Share|View|Comment)$",
                r"^(Home|My Network|Jobs|Messaging|Notifications)$",
                r"^skills?:",
                r"licenses.*certifications",
                r"\.pdf$|\.png$|\.jpg$",
                r"^(Message|Comment|Like|Share|Follow|Unfollow)$",
                r"^(For Business|Log in|Sign up|Help)$",
                r"^\d+\s+(new\s+)?notifications?$",
                r"^new\s+feed\s+updates",
            ]

            clean_lines = [
                l for l in lines
                if not any(re.search(p, l, re.I) for p in garbage_patterns)
                and len(l) > 1
            ]
            if not clean_lines:
                continue

            try:
                aria_spans = await item.locator(
                    "span[aria-hidden='true']"
                ).all_inner_texts()
            except Exception:
                aria_spans = []

            candidate_names = []
            if aria_spans and aria_spans[0].strip():
                candidate_names.append(aria_spans[0].strip())
            candidate_names.extend(clean_lines)

            cert_name = candidate_names[0]
            if cert_name.lower().endswith("logo") and len(candidate_names) > 1:
                cert_name = candidate_names[1]

            if "logo" in cert_name.lower():
                continue
            if len(cert_name) < 5 or len(cert_name) > 500:
                continue

            bad_keywords = [
                "home", "network", "jobs", "messaging", "skills", "see all",
                "message", "notifications", "new feed", "for business",
                "log in", "sign up", "help", "comment", "follow", "unfollow",
                "commented", "reacted",
            ]
            if any(k in cert_name.lower() for k in bad_keywords):
                continue

            issuer = ""
            if len(aria_spans) >= 2 and aria_spans[1]:
                candidate = aria_spans[1].strip()
                if candidate and candidate != cert_name:
                    issuer = candidate

            if not issuer:
                try:
                    company_link = item.locator("a[href*='/company/']").first
                    if await company_link.count():
                        issuer = (await company_link.inner_text()).strip()
                except Exception:
                    pass

            issue_date = ""
            expiry_date = ""

            try:
                captions = await item.locator(
                    ".pvs-entity__caption-wrapper span[aria-hidden='true']"
                ).all_inner_texts()
                for caption in captions:
                    caption = caption.strip()
                    if re.search(
                        r"issued|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec",
                        caption,
                        re.I,
                    ):
                        issue_date = caption
                    if re.search(r"expire|kedaluwarsa|berlaku sampai", caption, re.I):
                        expiry_date = caption
            except Exception:
                pass

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

            cred_id = ""
            for line in lines:
                m = re.search(
                    r"Credential ID\s*:?\s*([A-Za-z0-9\-\./:]+)", line, re.I
                )
                if m:
                    cred_id = m.group(1)
                    break

            verify_link = ""
            try:
                links = item.locator("a[href]")
                link_count = await links.count()
                for j in range(link_count):
                    link = links.nth(j)
                    link_text = await link.inner_text()
                    if "credential" in link_text.lower() or "verify" in link_text.lower():
                        href = await link.get_attribute("href")
                        if href:
                            verify_link = (
                                href
                                if href.startswith("http")
                                else f"https://www.linkedin.com{href}"
                            )
                            break

                if not verify_link and link_count > 0:
                    href = await links.first.get_attribute("href")
                    if href and href.startswith("http"):
                        verify_link = href
            except Exception:
                pass

            if _is_help_or_prefs_link(verify_link):
                continue
            if verify_link and "multiple-media-viewer" in verify_link:
                continue
            if verify_link and "/in/" in verify_link and "miniProfileUrn" in verify_link:
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
            continue

    return results
