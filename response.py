from typing import List, Optional, Dict, Any
from .models import LinkedInRequest, CertificateItem, ScrapeResult


def build_response(
    req: LinkedInRequest,
    items: List[CertificateItem],
    cookies_loaded: bool,
    is_guest: bool,
    debug_msgs: List[str],
    debug_files: Optional[dict] = None,
) -> Dict[str, Any]:
    """Compose the public API response while preserving the legacy shape.

    - `certificates_list` is a list when items exist, otherwise the string
      "not found" to match current clients.
    - `found` and `total_certificates` reflect extraction results.
    """
    resp = {
        "url": req.url,
        "keyword": req.keyword,
        "found": len(items) > 0,
        "total_certificates": len(items),
        "certificates_list": [i.dict() for i in items] if items else "not found",
        "cookies_loaded": cookies_loaded,
        "guest_mode": is_guest,
        "debug": " | ".join(debug_msgs),
    }
    if debug_files:
        resp["debug_files"] = debug_files
    return resp


def build_error(req: LinkedInRequest, error: str, debug_msgs: List[str]) -> Dict[str, Any]:
    """Build a consistent error response without changing the contract.

    `certificates_list` is set to "error" to match current behavior.
    """
    return {
        "url": req.url,
        "found": False,
        "error": error,
        "certificates_list": "error",
        "debug": " | ".join(debug_msgs),
    }
