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
        sec = page.locator("#licenses_and_certifications").locator("xpath=ancestor::section[1]").first
        if await sec.count() > 0: return sec, "Classic_ID"
    except: pass

    # 2. Strategy: Header Text (Regex)
    # Mencari H2/Span dengan teks "Licenses & certifications" (Tambah variasi bahasa)
    header_regex = re.compile(r"Licenses\s*(&|and)\s*certifications|Sertifikasi|Lisensi|Licenses|Certifications|Lisensi & Sertifikasi", re.I)
    try:
        headings = page.locator("h2, h3, span.pvs-header__title, span[class*='title']").filter(has_text=header_regex)
        count = await headings.count()
        for i in range(count):
            # Cek apakah parentnya adalah Section
            candidate = headings.nth(i).locator("xpath=ancestor::section[1]")
            if await candidate.count() > 0:
                # Validasi: Pastikan bukan Experience
                text = await candidate.text_content()
                if "experience" not in text.lower()[:50]: 
                    return candidate, "Header_Text"
            
            # Fallback: Jika layout div-soup, cari container div terdekat
            candidate_div = headings.nth(i).locator("xpath=ancestor::div[contains(@class, 'pvs-header')]/..")
            if await candidate_div.count() > 0:
                return candidate_div, "Header_Div"
    except: pass

    # 3. Strategy: Anchor Keyword Trace (SAVAGE MODE)
    # Cari elemen apapun (kecil) yang punya teks khas sertifikat, lalu cari wadah besarnya.
    try:
        anchor_text = re.compile(r"Credential ID|ID Kredensial|Issued|Diterbitkan", re.I)
        anchors = page.locator("div, span, a").filter(has_text=anchor_text)
        
        if await anchors.count() > 0:
            print("   ⚓ Anchor text found! Tracing back to container...")
            # Ambil elemen pertama yang valid
            anchor = anchors.first
            
            # Coba cari Section ancestor
            section = anchor.locator("xpath=ancestor::section[1]")
            if await section.count() > 0:
                return section, "Anchor_Trace_Section"
            
            # Coba cari Card ancestor (Tambah: artdeco-card lebih luas)
            card = anchor.locator("xpath=ancestor::div[contains(@class, 'artdeco-card') or contains(@class, 'pvs-list') or contains(@class, 'pvs-entity')][1]")
            if await card.count() > 0:
                return card, "Anchor_Trace_Card"
    except: pass

    # 4. Strategy: Contextual (Halaman Details)
    if "details/certifications" in page.url or "details/licenses" in page.url:
        main = page.locator("main")
        if await main.count() > 0:
            return main, "Full_Page_Main"

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