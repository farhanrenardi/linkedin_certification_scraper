from typing import List, Optional


def add_debug(debug_list: List[str], tag: str) -> None:
    """Append a debug tag to the in-flight list.

    Using small, structured tags helps trace the executed strategies and
    decisions without exposing sensitive data.
    """
    debug_list.append(tag)


async def save_debug_files(page, prefix: str = "debug") -> Optional[dict]:
    """Save a full-page screenshot and HTML content to /tmp for diagnostics.

    Returns a map with file paths or None if saving fails. This is gated by
    a request `debug` flag and should not be enabled in production by default.
    """
    try:
        ts = int(page.context._impl_obj._loop.time())  # approximate timestamp
        screenshot_path = f"/tmp/{prefix}_{ts}.png"
        html_path = f"/tmp/{prefix}_{ts}.html"
        await page.screenshot(path=screenshot_path, full_page=True)
        content = await page.content()
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"screenshot": screenshot_path, "html": html_path}
    except Exception:
        return None
