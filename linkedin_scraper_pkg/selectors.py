import re
from typing import Tuple
from playwright.async_api import Page, Locator


async def find_cert_section(page: Page) -> Tuple[Locator | None, str]:
    """Locate the 'Licenses & Certifications' section using robust strategies.

    We avoid brittle generated class names and prefer:
    - ID selectors when present
    - Section headers with localized text via :has()
    - Data attributes as fallbacks
    - Full section scan with keyword heuristics
    Returns (section_locator, strategy_tag).
    """
    # Strategy 1: Known ID
    try:
        sec_by_id = page.locator("#licenses_and_certifications")
        if await sec_by_id.count() > 0:
            parent_section = sec_by_id.locator("..").locator("section").first
            if await parent_section.count() > 0:
                return parent_section, "ID"
    except Exception:
        pass

    # Strategy 2: Localized header via :has() and heading role
    try:
        text_re = re.compile(
            r"Licenses\s*&\s*certifications|Licenses\s*and\s*certifications|Lisensi\s*&\s*sertifikasi|Sertifikasi|Lisensi|Sertifikat",
            re.I,
        )
        # Heading role (visible text)
        heading = page.get_by_role("heading", name=text_re).first
        if await heading.count() > 0:
            sec_h = heading.locator("xpath=ancestor::section[1]").first
            if await sec_h.count() > 0:
                return sec_h, "HeadingRole"
        # Try different selectors for header
        sec = page.locator("section:has(.pvs-header__title)").filter(has_text=text_re).first
        if await sec.count() > 0:
            return sec, "HeaderHas"
        # Try generic section filter
        sec2 = page.locator("section").filter(has_text=text_re).first
        if await sec2.count() > 0:
            return sec2, "SectionText"
    except Exception:
        pass

    # Strategy 2b: Look for h2, h3 with cert text, then get parent section
    try:
        text_re = re.compile(
            r"Licenses\s*&\s*certifications|Licenses\s*and\s*certifications|Lisensi\s*&\s*sertifikasi|Sertifikasi|Lisensi",
            re.I,
        )
        for tag in ["h2", "h3", "h4"]:
            headers = page.locator(f"{tag}").filter(has_text=text_re)
            if await headers.count() > 0:
                parent = headers.first.locator("xpath=ancestor::section[1]")
                if await parent.count() > 0:
                    return parent, f"HeaderTag:{tag}"
    except Exception:
        pass

    # Strategy 3: Data attributes and id contains
    try:
        for sel in [
            "section[data-section='certifications']",
            "section[id*='certif']",
            "section[data-view-name*='certif']",
            "div[data-section='certifications']",
        ]:
            candidate = page.locator(sel).first
            if await candidate.count() > 0:
                return candidate, f"Attr:{sel}"
    except Exception:
        pass

    # Strategy 4: Full sections scan with better keyword matching
    try:
        all_sections = page.locator("section")
        count = await all_sections.count()
        for i in range(count):
            sec = all_sections.nth(i)
            text = (await sec.inner_text()).lower()
            # More flexible matching
            if any(k in text for k in ["licens", "certif", "sertif", "credential"]):
                return sec, f"Scan#{i}"
    except Exception:
        pass

    # Strategy 5: Look for specific pvs (profile visual service) sections
    try:
        all_divs = page.locator("[class*='pvs-section']")
        count = await all_divs.count()
        for i in range(count):
            div = all_divs.nth(i)
            text = (await div.inner_text()).lower()
            if any(k in text for k in ["licens", "certif", "sertif"]):
                return div, f"PVSSection#{i}"
    except Exception:
        pass

    return None, "NotFound"


async def find_show_all_button(section: Locator) -> Locator | None:
    """Find a visible 'Show all certifications' button or link in the section.

    Prefer text-based matching and href hints, returning a locator ready to click.
    Ensures the element is visible to avoid clicking honeypots.
    """
    # Strategy 1: Text-based (EN + ID variants) - exact phrases
    try:
        patterns = [
            re.compile(r"Show all\s*(certifications|licenses)", re.I),
            re.compile(r"Tampilkan semua\s*(sertifikasi|lisensi)", re.I),
            re.compile(r"Show all", re.I),
            re.compile(r"Tampilkan semua", re.I),
        ]
        for pattern in patterns:
            btn = section.get_by_text(pattern).first
            if await btn.count() > 0:
                try:
                    if await btn.is_visible():
                        return btn
                except Exception:
                    pass
    except Exception:
        pass

    # Strategy 1b: Button/Link containing show/tampilkan text
    try:
        btn = section.locator("a, button").filter(
            has_text=re.compile(r"show|tampilkan", re.I)
        ).first
        if await btn.count() > 0:
            try:
                if await btn.is_visible():
                    return btn
            except Exception:
                pass
    except Exception:
        pass

    # Strategy 2: Href-based
    try:
        btn2 = section.locator("a[href*='/details/certifications/']").first
        if await btn2.count() > 0:
            try:
                if await btn2.is_visible():
                    return btn2
            except Exception:
                pass
    except Exception:
        pass

    # Strategy 2b: Details/licenses href
    try:
        btn2b = section.locator("a[href*='/details/licenses/']").first
        if await btn2b.count() > 0:
            try:
                if await btn2b.is_visible():
                    return btn2b
            except Exception:
                pass
    except Exception:
        pass

    # Strategy 3: Footer link
    try:
        btn3 = section.locator("div[class*='footer'] a, div[class*='Footer'] a").first
        if await btn3.count() > 0:
            try:
                if await btn3.is_visible():
                    return btn3
            except Exception:
                pass
    except Exception:
        pass

    # Strategy 4: Last anchor in section (often "Show all" is positioned at end)
    try:
        last_link = section.locator("a").last
        if await last_link.count() > 0:
            text = await last_link.inner_text()
            if any(k in text.lower() for k in ["show", "tampilkan", "detail"]):
                try:
                    if await last_link.is_visible():
                        return last_link
                except Exception:
                    pass
    except Exception:
        pass

    return None
