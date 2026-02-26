import asyncio
import random
from typing import Tuple
from playwright.async_api import Page


async def random_delay(min_sec: float = 0.5, max_sec: float = 1.5) -> None:
    """Sleep for a random duration to emulate human pacing.

    This helps avoid predictable timing and can reduce detection risk
    when used judiciously outside of core waits.
    """
    await asyncio.sleep(random.uniform(min_sec, max_sec))


async def goto_with_retry(page: Page, url: str, timeout_ms: int, tries: int = 2) -> Tuple[bool, str]:
    """Navigate to a URL with bounded retries and network idle waits.

    Returns (success, error_message). It uses Playwright's `networkidle`
    and a small post-load delay to stabilize dynamic content.
    """
    last_err = ""
    for attempt in range(tries):
        try:
            await page.goto(url, timeout=timeout_ms, wait_until="networkidle")
            await random_delay(1.0, 2.0)
            return True, ""
        except Exception as e:
            last_err = str(e)
            if attempt < tries - 1:
                await random_delay(1.0, 2.0)
            else:
                return False, last_err
    return False, last_err


async def navigate_via_js(page: Page, url: str, timeout_ms: int = 20000) -> Tuple[bool, str]:
    """Navigate via window.location.href to bypass SDUI client-side interception.

    LinkedIn's new SDUI routing layer intercepts Playwright's page.goto()
    and redirects automated browsers away from profile pages. Using raw
    JavaScript navigation bypasses this detection layer.

    Returns (success, error_message).
    """
    try:
        await page.evaluate(f"window.location.href = '{url}'")
        await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        await page.wait_for_timeout(3000)
        await random_delay(0.5, 1.5)
        return True, ""
    except Exception as e:
        return False, str(e)


async def human_behavior(page: Page) -> None:
    """Perform gentle mouse moves and incremental scrolls to emulate humans.

    Avoids abrupt jumps that could trigger heuristics and helps lazy-loading
    content appear without excessive scrolling.
    """
    try:
        for _ in range(random.randint(2, 4)):
            x = random.randint(100, 800)
            y = random.randint(100, 600)
            await page.mouse.move(x, y, steps=random.randint(5, 15))
            await random_delay(0.2, 0.6)

        scroll_distance = random.randint(300, 800)
        steps = random.randint(3, 6)
        for _ in range(steps):
            await page.mouse.wheel(0, scroll_distance // steps)
            await random_delay(0.2, 0.5)

        await random_delay(0.8, 1.5)
        await page.mouse.wheel(0, -random.randint(100, 300))
        await random_delay(0.4, 0.9)
    except Exception:
        # Non-critical; skip on errors
        pass


async def warm_up_scroll(page: Page) -> None:
    """Perform a gentle top-to-bottom scroll to trigger lazy-loading.

    This helps LinkedIn render sections (including certificates) that may not
    be present in the initial DOM. Scroll is incremental to avoid detection
    and to let network idle between steps.
    """
    try:
        # Start near top to ensure deterministic scroll path
        await page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
        steps = [0.25, 0.5, 0.75, 1.0]
        for frac in steps:
            await page.evaluate(
                "window.scrollTo({top: document.body.scrollHeight * %s, behavior: 'smooth'})" % frac
            )
            await random_delay(0.6, 1.1)
    except Exception:
        pass


async def deep_scroll(page: Page, steps: int = 6) -> None:
    """Perform a deeper incremental scroll to force-load lazy content.

    Useful when important sections (e.g., certificates) are not yet in the DOM
    after the warm-up scroll. Keeps pauses between steps to allow network idle.
    """
    try:
        for i in range(1, steps + 1):
            frac = i / steps
            await page.evaluate(
                "window.scrollTo({top: document.body.scrollHeight * %s, behavior: 'smooth'})" % frac
            )
            await random_delay(0.7, 1.2)
    except Exception:
        pass


async def smooth_scroll_to(page: Page, element) -> bool:
    """Smoothly scroll to the bounding box of a locator if possible.

    Returns True when the scroll targets a known rectangle; False otherwise.
    """
    try:
        if await element.count() > 0:
            box = await element.bounding_box()
            if box:
                await page.evaluate(
                    f"window.scrollTo({{ top: {box['y'] - 150}, behavior: 'smooth' }})"
                )
                await random_delay(0.8, 1.5)
                return True
    except Exception:
        pass
    return False


async def stabilize_detail_view(page: Page, max_wait: int = 25000) -> None:
    """Trigger lazy-loading in details view using incremental scroll.

    We scroll in thirds and finally to the bottom to prompt AJAX loads,
    while bounding total wait to avoid indefinite scrolling.
    """
    try:
        lst = page.locator(
            "main ul.pvs-list li, main li.pvs-list__paged-list-item, main li[role='listitem']"
        )
        if await lst.count() == 0:
            try:
                await lst.first.wait_for(state="visible", timeout=max_wait)
            except Exception:
                pass
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, document.body.scrollHeight/3)")
            await random_delay(0.6, 1.2)
        await page.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")
        await random_delay(1.0, 1.8)
    except Exception:
        pass
