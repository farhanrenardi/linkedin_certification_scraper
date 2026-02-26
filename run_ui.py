from __future__ import annotations

import os
import sys
import time
import shutil
import tempfile
import subprocess
import webbrowser
import urllib.request
import urllib.error
from threading import Thread

import uvicorn


def _detect_chrome_path() -> str | None:
    if sys.platform == "darwin":
        default = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if os.path.exists(default):
            return default
        return shutil.which("google-chrome") or shutil.which("chrome")
    if sys.platform.startswith("win"):
        candidates = [
            os.environ.get("CHROME_PATH"),
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        ]
        for path in candidates:
            if path and os.path.exists(path):
                return path
        return shutil.which("chrome") or shutil.which("google-chrome")
    return (
        shutil.which("google-chrome")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )


def _cdp_is_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/version", timeout=2
        ) as response:
            return response.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


def start_cdp(port: int = 9222) -> None:
    if _cdp_is_running(port):
        print(f"✅ Chrome CDP already running on port {port}")
        return
    chrome_path = _detect_chrome_path()
    if not chrome_path:
        print("⚠️ Chrome executable not found. Please install Chrome or set CHROME_PATH.")
        return

    user_data_dir = os.path.join(tempfile.gettempdir(), "linkedin_cdp_profile")
    cmd = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]

    # Windows needs different process creation flags
    kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform.startswith("win"):
        # CREATE_NEW_PROCESS_GROUP for Windows
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **kwargs)
    try:
        with open(".cdp.pid", "w", encoding="utf-8") as handle:
            handle.write(str(proc.pid))
        with open(".cdp.profile", "w", encoding="utf-8") as handle:
            handle.write(user_data_dir)
    except Exception:
        pass
    print(f"✅ Chrome CDP started on port {port}")


def start_server(host: str, port: int) -> None:
    from ui_app import app
    uvicorn.run(app, host=host, port=port, log_level="info")


def main() -> None:
    host = os.environ.get("UI_HOST", "127.0.0.1")
    port = int(os.environ.get("UI_PORT", "8787"))
    cdp_port = int(os.environ.get("SCRAPER_CDP_PORT", "9222"))

    os.environ.setdefault("SCRAPER_USE_CDP", "true")
    os.environ.setdefault("SCRAPER_CDP_URL", f"http://127.0.0.1:{cdp_port}")

    start_cdp(cdp_port)

    server_thread = Thread(target=start_server, args=(host, port), daemon=True)
    server_thread.start()

    time.sleep(1)
    ui_url = f"http://{host}:{port}"
    webbrowser.open(ui_url)

    print("\nLinkedIn Certificate Scraper UI is running:")
    print(ui_url)
    print("Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    main()
