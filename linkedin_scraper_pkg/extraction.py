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
        "li.profile-section-card"  # Tambah fallback jika ada card layout
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
            items = root.locator("li, div[class*='entity']")
        else:
            items = page.locator("li, div[class*='entity']")
        if await items.count() == 0:
            print("   ❌ No items found even in fallback.")
            return results

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
            name_locator = item.locator("h3, span.mr1.t-bold, span.t-bold, div.display-flex > span:first-child")
            if await name_locator.count() > 0:
                cert_name = (await name_locator.text_content()).strip()
            if not cert_name and full_text:
                # Fallback regex
                name_match = re.search(r"^(.*?)(?:Issued by|Diterbitkan oleh|Oleh|Issuer|Organization|–|—|\s{2,})", full_text, re.I)
                if name_match:
                    cert_name = name_match.group(1).strip()

            if not cert_name:
                print(f"   ⚠️ Skipping item {i}: No certificate name found.")
                continue  # Skip jika nama kosong

            # B. Issuer (Cari span normal setelah name)
            issuer = ""
            issuer_locator = item.locator("span.t-14.t-normal, span.t-black--light, div.pvs-entity__caption-wrapper")
            if await issuer_locator.count() > 0:
                issuer_text = (await issuer_locator.text_content()).strip()
                issuer_match = re.search(r"(?:Issued by|Diterbitkan oleh|Oleh|Issuer|Organization)?\s*(.+)", issuer_text, re.I)
                if issuer_match:
                    issuer = issuer_match.group(1).strip()

            # C. Issue Date (Cari span dengan date pattern)
            issue_date = ""
            date_locator = item.locator("span.t-14.t-normal.t-black--light, span.visually-hidden")
            date_texts = await date_locator.all_text_contents()
            for dt in date_texts:
                has_date = re.search(r"(?:Issued|Diterbitkan)\s*(on)?\s*(\w+\s*\d{4})", dt, re.I)
                if has_date:
                    issue_date = has_date.group(2)
                    break
                # Fallback: Ambil tanggal pertama
                has_any_date = re.search(r"\w+\s*\d{4}", dt)
                if has_any_date:
                    issue_date = has_any_date.group(0)
                    break

            # D. Expiry Date
            expiry_date = ""
            for dt in date_texts:
                expiry_match = re.search(r"(?:Expires|Kadaluarsa)\s*(on)?\s*(\w+\s*\d{4})", dt, re.I)
                if expiry_match:
                    expiry_date = expiry_match.group(2)
                    break

            # E. Credential ID (Sering di visually-hidden)
            cred_id = ""
            id_locator = item.locator("span.visually-hidden, div.pvs-entity__caption-wrapper")
            id_texts = await id_locator.all_text_contents()
            for idt in id_texts:
                id_match = re.search(r"(?:Credential ID|ID Kredensial)[:\s]+([\w\-\.]+)", idt, re.I)
                if id_match:
                    cred_id = id_match.group(1)
                    break

            # F. Verify Link (Cari link eksternal atau credential)
            verify_link = ""
            link_locator = item.locator("a.optional-action-target-wrapper, a[href*='credential'], a[href*='redir']")
            if await link_locator.count() > 0:
                verify_link = await link_locator.get_attribute("href")
                if verify_link and verify_link.startswith("/"):
                    verify_link = "https://www.linkedin.com" + verify_link

            # Clean up
            if "Issued" in issuer or "Diterbitkan" in issuer:
                issuer = ""

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
            print(f"   ✅ Extracted item {i}: {cert_name}")

        except Exception as e:
            print(f"   ❌ Error parsing item {i}: {str(e)[:100]}")
            continue

    if not results:
        print("   ⚠️ No certificates extracted. Check if section is truly present or login required.")

    return results