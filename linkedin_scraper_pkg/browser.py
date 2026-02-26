from playwright.async_api import Browser, BrowserContext
from playwright.async_api import async_playwright
from .config import random_user_agent, SLOW_MO_MS

# Keep a module-level reference to prevent garbage collection
_playwright_instance = None


async def launch_browser(headless: bool = True, proxy: str | None = None) -> Browser:
    """Launch a Chromium browser with defensive flags for scraping.

    Headless and proxy are configurable per request. We avoid GPU and
    extension features and disable automation signals where possible.
    """
    global _playwright_instance
    _playwright_instance = await async_playwright().start()
    browser = await _playwright_instance.chromium.launch(
      headless=headless,
      proxy={"server": proxy} if proxy else None,
      slow_mo=SLOW_MO_MS if SLOW_MO_MS > 0 else None,
      args=[
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-infobars",
        "--window-size=1920,1080",
        "--disable-dev-shm-usage",
        "--disable-web-security",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-accelerated-2d-canvas",
        "--disable-gpu",
        "--hide-scrollbars",
        "--mute-audio",
        "--no-first-run",
        "--no-zygote",
        "--disable-extensions",
      ],
    )
    return browser


async def launch_persistent_context(
    user_data_dir: str,
    headless: bool = True,
    proxy: str | None = None,
) -> BrowserContext:
    """Launch a Chromium browser with a persistent user data directory.

    Cookies and localStorage are preserved between runs automatically.
    Returns a BrowserContext (not a Browser) since persistent contexts
    combine both.
    """
    global _playwright_instance
    _playwright_instance = await async_playwright().start()
    context = await _playwright_instance.chromium.launch_persistent_context(
        user_data_dir,
        headless=headless,
        proxy={"server": proxy} if proxy else None,
        slow_mo=SLOW_MO_MS if SLOW_MO_MS > 0 else None,
        user_agent=random_user_agent(),
        viewport={"width": 1920, "height": 1080},
        locale="en-US",
        timezone_id="Asia/Jakarta",
        permissions=["geolocation"],
        has_touch=False,
        is_mobile=False,
        device_scale_factor=1,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            "--window-size=1920,1080",
            "--disable-dev-shm-usage",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-accelerated-2d-canvas",
            "--disable-gpu",
            "--hide-scrollbars",
            "--mute-audio",
            "--no-first-run",
            "--disable-extensions",
        ],
    )
    return context


async def new_context(
    browser: Browser,
    locale: str = "en-US",
    timezone_id: str = "Asia/Jakarta",
    user_agent: str | None = None,
) -> BrowserContext:
    """Create a browser context with realistic headers and locale settings.

    We set a desktop viewport and language headers to reduce anomaly signals,
    then rely on `apply_stealth()` to patch common automation fingerprints.
    """
    ua = user_agent or random_user_agent()
    context = await browser.new_context(
        user_agent=ua,
        viewport={"width": 1920, "height": 1080},
        locale=locale,
        timezone_id=timezone_id,
        permissions=["geolocation"],
        has_touch=False,
        is_mobile=False,
        device_scale_factor=1,
        extra_http_headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        },
    )
    return context


async def apply_stealth(context: BrowserContext) -> None:
    """Inject lightweight anti-detection scripts to patch common fingerprints.

    We avoid over-mocking and focus on the essentials: webdriver, plugins,
    languages, minimal `window.chrome`, and permission overrides. This strikes
    a balance between stealth and maintainability.
    """
    await context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        window.chrome = { runtime: {} };

        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
          parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters)
        );

        const overrideToString = (obj, method) => {
          const original = obj[method];
          obj[method] = function() {
            return original.apply(this, arguments);
          };
          obj[method].toString = () => 'function ' + method + '() { [native code] }';
        };
        overrideToString(navigator, 'getBattery');
        Object.defineProperty(navigator, 'getBattery', {
          value: () => Promise.resolve({
            charging: true,
            chargingTime: 0,
            dischargingTime: Infinity,
            level: 1.0,
          })
        });
        """
    )


async def connect_over_cdp(cdp_url: str) -> Browser:
    """Connect to an existing Chrome instance via CDP.

    This allows reusing a real user's logged-in session (e.g., Chrome started
    with `--remote-debugging-port=9222`), which is harder for LinkedIn to
    block than a fresh automated Chromium profile.
    
    If cdp_url contains hostname that Chrome rejects, we fetch the WebSocket URL
    first using a direct request, then connect via WebSocket.
    """
    import httpx
    
    p = await async_playwright().start()
    
    # Try to get WebSocket URL first if using hostname (not localhost/IP)
    if 'host.docker.internal' in cdp_url or any(host in cdp_url for host in ['hostname', 'docker']):
        try:
            # Fetch version endpoint to get WebSocket URL
            async with httpx.AsyncClient() as client:
                # Use IP instead of hostname for HTTP request
                version_url = cdp_url.replace('host.docker.internal', '0.250.250.254') + '/json/version/'
                response = await client.get(version_url, timeout=10.0)
                if response.status_code == 200:
                    data = response.json()
                    ws_url = data.get('webSocketDebuggerUrl', '')
                    if ws_url:
                        # Replace IP back to hostname for WebSocket
                        ws_url = ws_url.replace('0.250.250.254', 'host.docker.internal')
                        browser = await p.chromium.connect_over_cdp(ws_url)
                        return browser
        except Exception as e:
            print(f"Failed to fetch WebSocket URL: {e}, trying direct connect...")
    
    # Fallback: try direct connect
    browser = await p.chromium.connect_over_cdp(cdp_url)
    return browser
