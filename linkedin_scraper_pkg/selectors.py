# FILE: linkedin_scraper_pkg/selectors.py
import re
from typing import Tuple
from playwright.async_api import Page, Locator

async def find_cert_section(page: Page) -> Tuple[Locator | None, str]:
    """
    Strategi Multi-Layer untuk menemukan Section Sertifikat:
    1. Classic ID (Cepat)
    2. Header Text (Lokalisasi)
    3. Anchor Keyword Trace (Paling Kuat/Savage)
    4. Full Page Fallback (Jika di halaman details)
    """
    
    # 1. Strategy: The Classic ID
    try:
        # Mencari ID standar dan naik ke parent section (Adjust xpath agar lebih akurat)
        sec = page.locator("#licenses_and_certifications")
        if await sec.count() > 0:
            # Try to get parent section
            parent_sec = sec.locator("xpath=ancestor::section[1]")
            if await parent_sec.count() > 0:
                return parent_sec.first, "Classic_ID_Section"
            # Fallback to ID element itself if no parent section
            return sec.first, "Classic_ID"
    except Exception as e:
        print(f"   ⚠️ Classic ID strategy failed: {str(e)[:50]}")

    # 2. Strategy: Header Text (Regex) - Expanded patterns
    # Mencari H2/Span dengan teks "Licenses & certifications" (Tambah variasi bahasa)
    header_patterns = [
        r"Licenses?\s*(&|and)?\s*certifications?",
        r"Certifications?",
        r"Lisensi(\s*(&|dan)?\s*Sertifikat)?",
        r"Sertifikat",
        r"Professional\s*Certifications?",
    ]
    
    for pattern in header_patterns:
        try:
            header_regex = re.compile(pattern, re.I)
            headings = page.locator("h2, h3, span.pvs-header__title, span[class*='title'], div.pvs-header__title-container").filter(has_text=header_regex)
            count = await headings.count()
            
            for i in range(count):
                # Cek apakah parentnya adalah Section
                candidate = headings.nth(i).locator("xpath=ancestor::section[1]")
                if await candidate.count() > 0:
                    # Validasi: Pastikan bukan Experience atau Education
                    text = await candidate.text_content()
                    if text and "experience" not in text.lower()[:80] and "education" not in text.lower()[:80]: 
                        return candidate.first, f"Header_Text_{pattern[:20]}"
                
                # Fallback: Jika layout div-soup, cari container div terdekat
                candidate_div = headings.nth(i).locator("xpath=ancestor::div[contains(@class, 'pvs-header')]/..")
                if await candidate_div.count() > 0:
                    return candidate_div.first, "Header_Div"
        except Exception as e:
            print(f"   ⚠️ Header pattern {pattern[:20]} failed: {str(e)[:50]}")
            continue

    # 3. Strategy: Anchor Keyword Trace (SAVAGE MODE)
    # Cari elemen apapun (kecil) yang punya teks khas sertifikat, lalu cari wadah besarnya.
    try:
        anchor_patterns = [
            r"Credential\s*ID",
            r"ID\s*Kredensial",
            r"Issued\s*by",
            r"Diterbitkan\s*oleh",
            r"Issue\s*Date",
            r"Expiration\s*Date",
        ]
        
        for pattern in anchor_patterns:
            try:
                anchor_text = re.compile(pattern, re.I)
                anchors = page.locator("div, span, a, li").filter(has_text=anchor_text)
                
                if await anchors.count() > 0:
                    print(f"   ⚓ Anchor text '{pattern[:20]}' found! Tracing back to container...")
                    # Ambil elemen pertama yang valid
                    anchor = anchors.first
                    
                    # Coba cari Section ancestor
                    section = anchor.locator("xpath=ancestor::section[1]")
                    if await section.count() > 0:
                        return section.first, f"Anchor_Trace_Section_{pattern[:15]}"
                    
                    # Coba cari Card ancestor (Tambah: artdeco-card lebih luas)
                    card = anchor.locator("xpath=ancestor::div[contains(@class, 'artdeco-card') or contains(@class, 'pvs-list') or contains(@class, 'pvs-entity')][1]")
                    if await card.count() > 0:
                        return card.first, f"Anchor_Trace_Card_{pattern[:15]}"
            except:
                continue
    except Exception as e:
        print(f"   ⚠️ Anchor trace strategy failed: {str(e)[:50]}")

    # 4. Strategy: Contextual (Halaman Details)
    if "details/certifications" in page.url or "details/licenses" in page.url:
        main = page.locator("main")
        if await main.count() > 0:
            return main.first, "Full_Page_Main"

    print("   ❌ All section detection strategies failed")
    return None, "NotFound"

async def find_show_all_button(section: Locator) -> Locator | None:
    # Cari tombol "Show all" agar bisa load semua data
    try:
        # Regex luas untuk berbagai bahasa
        btn_regex = re.compile(r"Show all|Tampilkan semua|See all|Lihat semua", re.I)
        
        # Cari tag 'a' atau 'button'
        btn = section.locator("a, button").filter(has_text=btn_regex).first
        if await btn.count() > 0: return btn
        
        # Cari berdasarkan ID navigasi
        btn = section.locator("[id*='navigation-index']").first
        if await btn.count() > 0: return btn

        # Cari di footer section
        footer = section.locator(".pvs-footer__text, .artdeco-card__action").first
        if await footer.count() > 0: return footer

    except: pass
    return None