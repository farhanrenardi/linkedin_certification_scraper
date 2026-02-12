# FILE: linkedin_scraper_pkg/extraction.py
import re
import asyncio
from typing import List
from playwright.async_api import Page, Locator
from .models import CertificateItem

async def extract_items(
    page: Page,
    scope_selector: str,
    source: str,
    require_visible: bool = False,  # Default False untuk lebih agresif
    root: Page | Locator | None = None,
) -> List[CertificateItem]:
    
    results: List[CertificateItem] = []
    base = root or page

    # --- 1. DEFINISI SELECTOR YANG LEBIH ROBUST ---
    # Tambah selector spesifik untuk layout LinkedIn terbaru (2024-2026)
    candidates_selectors = [
        "li.pvs-list__paged-list-item",          # Layout Modern Standard
        "div.pvs-list__paged-list-item",         # Layout Modern Div
        "li.artdeco-list__item",                 # Layout Klasik
        "div.artdeco-list__item",                # Layout Klasik Div
        "ul.pvs-list > li",                      # Fallback Struktur UL
        "div.pvs-list > div",                    # Fallback Struktur Div
        "[data-view-name='profile-component-entity']",  # Layout SPA terbaru
        "div.pvs-entity, div.pvs-entity--padded",  # LinkedIn entity items
        "li.profile-section-card",               # Card layout
        "div[class*='pvs-list__item']",          # Flexible class match
        "li[class*='artdeco-list']",             # Flexible class match
        "div[class*='profile-component']",       # Profile component divs
    ]

    items = None
    
    # Coba satu per satu sampai ketemu elemen
    for sel in candidates_selectors:
        try:
            potential_items = base.locator(sel)
            count = await potential_items.count()
            if count > 0:
                # Validasi: Pastikan ada teks minimal (gunakan text_content() untuk include hidden)
                first_text = await potential_items.first.text_content()
                if first_text and len(first_text.strip()) > 10:  # Naikkan threshold untuk validasi
                    items = potential_items
                    print(f"   🔥 [Extraction] Locked on selector: {sel} ({count} items)")
                    break
        except: continue

    if not items:
        print("   ⚠️ No candidate selectors matched. Falling back to all li/div in section.")
        if root:
            # Try broader selectors
            items = root.locator("li, div[class*='entity'], div[class*='item'], div[class*='card']")
        else:
            items = page.locator("li, div[class*='entity'], div[class*='item'], div[class*='card']")
        
        item_count = await items.count()
        if item_count == 0:
            print("   ❌ No items found even in fallback.")
            # Last resort: print page structure for debugging
            print("   🔍 Attempting to debug page structure...")
            try:
                # Get all text content to see what's actually on the page
                page_text = await (root if root else page).text_content()
                if page_text:
                    # Look for certification keywords
                    keywords = ["credential", "issued", "certification", "license", "certificate"]
                    found_keywords = [kw for kw in keywords if kw.lower() in page_text.lower()]
                    if found_keywords:
                        print(f"   🔍 Found keywords in page: {found_keywords}")
                        print(f"   🔍 Page text preview: {page_text[:300]}...")
                    else:
                        print("   ⚠️ No certification-related keywords found in page text")
            except:
                pass
            return results
        else:
            print(f"   ⚠️ Fallback found {item_count} items, will attempt extraction")

    count = await items.count()
    print(f"   ⚔️ Processing {count} potential items...")

    # --- 2. EXTRACT PER FIELD MENGGUNAKAN LOCATOR (Lebih Reliable daripada Regex Full Text) ---
    for i in range(count):
        try:
            item = items.nth(i)
            # Ambil full text untuk debug dan fallback
            full_text = await item.text_content() or ""
            full_text = re.sub(r"\s+", " ", full_text).strip()
            print(f"   🔍 Item {i} raw text: {full_text[:150]}...")  # Debug: Print raw text untuk lihat isi

            # A. Certificate Name (Cari elemen bold atau header)
            cert_name = ""
            # Try multiple locator strategies for certificate name
            name_locators = [
                "h3, span.mr1.t-bold, span.t-bold",
                "div.display-flex > span:first-child",
                "div[class*='entity__title']",
                "span[class*='t-bold']",
                "a[class*='entity__title']",
                "div[class*='title'] span",
            ]
            
            for loc_str in name_locators:
                try:
                    name_locator = item.locator(loc_str)
                    if await name_locator.count() > 0:
                        cert_name = (await name_locator.first.text_content()).strip()
                        if cert_name and len(cert_name) > 2:
                            break
                except:
                    continue
            
            if not cert_name and full_text:
                # Fallback regex - more flexible patterns
                name_patterns = [
                    r"^(.*?)(?:Issued by|Diterbitkan oleh|Oleh|Issuer|Organization|–|—|\s{2,})",
                    r"^([^|]+)",  # Take first part before pipe
                    r"^(.+?)(?:\n|$)",  # Take first line
                ]
                for pattern in name_patterns:
                    name_match = re.search(pattern, full_text, re.I)
                    if name_match:
                        cert_name = name_match.group(1).strip()
                        # Validate it's not too long (likely grabbed too much)
                        if len(cert_name) < 200 and cert_name:
                            break

            if not cert_name:
                print(f"   ⚠️ Skipping item {i}: No certificate name found.")
                continue  # Skip jika nama kosong

            # B. Issuer (Cari span normal setelah name)
            issuer = ""
            issuer_locators = [
                "span.t-14.t-normal, span.t-black--light",
                "div.pvs-entity__caption-wrapper",
                "span[class*='t-normal']",
                "div[class*='caption']",
                "span[class*='secondary']",
            ]
            
            for loc_str in issuer_locators:
                try:
                    issuer_locator = item.locator(loc_str)
                    if await issuer_locator.count() > 0:
                        issuer_text = (await issuer_locator.first.text_content()).strip()
                        # Extract issuer from text that might have prefix
                        issuer_match = re.search(r"(?:Issued by|Diterbitkan oleh|Oleh|Issuer|Organization)?\s*(.+)", issuer_text, re.I)
                        if issuer_match:
                            issuer = issuer_match.group(1).strip()
                            # Clean up if issuer contains date patterns
                            if not re.search(r"\d{4}", issuer[:20]):  # Valid if no year in first 20 chars
                                break
                except:
                    continue

            # C. Issue Date (Cari span dengan date pattern)
            issue_date = ""
            date_locators = [
                "span.t-14.t-normal.t-black--light",
                "span.visually-hidden",
                "span[class*='date']",
                "time",
            ]
            
            date_texts = []
            for loc_str in date_locators:
                try:
                    date_locator = item.locator(loc_str)
                    if await date_locator.count() > 0:
                        texts = await date_locator.all_text_contents()
                        date_texts.extend(texts)
                except:
                    continue
            
            # Also try full text for dates
            if full_text:
                date_texts.append(full_text)
            
            for dt in date_texts:
                # Try to find issued date
                has_date = re.search(r"(?:Issued|Diterbitkan|Issue Date|Tanggal Terbit)[:\s]*(on)?\s*(\w+\s*\d{4})", dt, re.I)
                if has_date:
                    issue_date = has_date.group(2)
                    break
                # Fallback: Find first date pattern
                if not issue_date:
                    has_any_date = re.search(r"(\w+\s*\d{4})", dt)
                    if has_any_date:
                        issue_date = has_any_date.group(1)

            # D. Expiry Date
            expiry_date = ""
            for dt in date_texts:
                expiry_match = re.search(r"(?:Expires|Expiration|Kadaluarsa|Expiry Date)[:\s]*(on)?\s*(\w+\s*\d{4})", dt, re.I)
                if expiry_match:
                    expiry_date = expiry_match.group(2)
                    break
                # Also check for "No Expiration" or similar
                no_expiry = re.search(r"(?:No Expiration|Tidak Ada Kadaluarsa|Does Not Expire)", dt, re.I)
                if no_expiry:
                    expiry_date = "No Expiration"
                    break

            # E. Credential ID (Sering di visually-hidden)
            cred_id = ""
            id_locators = [
                "span.visually-hidden",
                "div.pvs-entity__caption-wrapper",
                "span[class*='credential']",
            ]
            
            id_texts = []
            for loc_str in id_locators:
                try:
                    id_locator = item.locator(loc_str)
                    if await id_locator.count() > 0:
                        texts = await id_locator.all_text_contents()
                        id_texts.extend(texts)
                except:
                    continue
            
            # Also check full text
            if full_text:
                id_texts.append(full_text)
            
            for idt in id_texts:
                id_match = re.search(r"(?:Credential ID|ID Kredensial|License Number|Certificate ID)[:\s]+([\w\-\.]+)", idt, re.I)
                if id_match:
                    cred_id = id_match.group(1)
                    break

            # F. Verify Link (Cari link eksternal atau credential)
            verify_link = ""
            link_locators = [
                "a.optional-action-target-wrapper",
                "a[href*='credential']",
                "a[href*='redir']",
                "a[href*='verify']",
                "a[aria-label*='credential']",
                "a[aria-label*='show']",
            ]
            
            for loc_str in link_locators:
                try:
                    link_locator = item.locator(loc_str)
                    if await link_locator.count() > 0:
                        verify_link = await link_locator.first.get_attribute("href")
                        if verify_link:
                            if verify_link.startswith("/"):
                                verify_link = "https://www.linkedin.com" + verify_link
                            break
                except:
                    continue

            # Clean up
            if "Issued" in issuer or "Diterbitkan" in issuer or "Expires" in issuer:
                issuer = ""
            
            # Additional cleanup: Remove common noise from issuer
            if issuer:
                # Remove credential ID if it leaked into issuer
                issuer = re.sub(r"Credential ID[:\s]+[\w\-\.]+", "", issuer, flags=re.I).strip()
                # Remove date patterns from issuer
                issuer = re.sub(r"\w+\s*\d{4}", "", issuer).strip()

            # Validation: Make sure we have at least a name
            if not cert_name or len(cert_name.strip()) < 2:
                print(f"   ⚠️ Skipping item {i}: Invalid certificate name")
                continue

            # Tambah ke results jika valid
            results.append(CertificateItem(
                certificate_name=cert_name,
                issuer=issuer,
                issue_date=issue_date,
                expiry_date=expiry_date,
                credential_id=cred_id,
                verify_link=verify_link,
                source=f"{source}_Enhanced"
            ))
            print(f"   ✅ Extracted item {i}: {cert_name[:50]}{'...' if len(cert_name) > 50 else ''}")

        except Exception as e:
            print(f"   ❌ Error parsing item {i}: {str(e)[:100]}")
            continue

    if not results:
        print("   ⚠️ No certificates extracted. Check if section is truly present or login required.")

    return results