from typing import List, Optional
from pydantic import BaseModel


class LinkedInRequest(BaseModel):
    """Incoming request payload for the LinkedIn certificates scraper.

    This mirrors the current public API contract so that callers (e.g., n8n)
    do not need to change their payload structure.
    """
    url: str
    keyword: Optional[str] = None
    debug: bool = False
    headless: Optional[bool] = None
    max_wait: int = 25000
    detail_only: bool = False
    click_show_all: bool = True
    proxy: Optional[str] = None
    use_cdp: bool = False
    cdp_url: Optional[str] = None


class CertificateItem(BaseModel):
    """Normalized certificate item extracted from LinkedIn profile views.

    Using a typed model helps ensure consistent fields and simplifies
    validation before serializing back to the legacy response format.
    """
    certificate_name: str
    credential_id: str = ""
    issuer: str = ""
    issue_date: str = ""
    expiry_date: str = ""
    verify_link: str = ""
    source: str = ""


class ScrapeResult(BaseModel):
    """Internal result shape used for composing the public response.

    The public API response will be built from this model to preserve
    the existing keys expected by clients.
    """
    url: str
    keyword: Optional[str] = None
    certificates: List[CertificateItem]
    cookies_loaded: bool
    guest_mode: bool
    debug_msgs: List[str]
    debug_files: Optional[dict] = None
