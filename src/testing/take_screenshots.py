"""Take screenshots of the Streamlit UI (real data) into the `screenshots/` folder.

It starts the app, opens it in headless Chrome (dark theme), clicks the tab and its button like a
user would, waits for the result and saves two screenshots per part (top of page + result card).

Needs: the Gmail MCP server running (python src/mcp_server/start_server.py) and Google Chrome.
Run from the project root:
    python src/testing/take_screenshots.py part3 part4
"""

import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket  # pip package: websocket-client

ROOT = Path(__file__).resolve().parents[2]
SCREENSHOTS = ROOT / "screenshots"
APP = ROOT / "src" / "frontend" / "app.py"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
APP_PORT, CHROME_PORT = 8502, 9333
WIDTH, HEIGHT, ZOOM = 1520, 760, 1.25  # page size in CSS pixels at 125% zoom -> 1900x950 image

# part -> (tab text, button text, screenshot name prefix)
PARTS = {
    "part1": ("Part 1", "Generate reply", "writer_agent_part1"),
    "part2": ("Part 2", "Fetch first email & reply", "writer_agent_part2"),
    "part3": ("Part 3", "Read today's emails", "reader_agent_part3"),
    "part4": ("Part 4", "Read emails & write replies", "reader_writer_workflow_part4"),
}


class Browser:
    """Tiny Chrome DevTools Protocol client: run JavaScript and take screenshots."""

    def __init__(self, port: int):
        pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
        page = next(p for p in pages if p["type"] == "page")
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=900)
        self.msg_id = 0

    def send(self, method: str, **params):
        self.msg_id += 1
        self.ws.send(json.dumps({"id": self.msg_id, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.msg_id:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def js(self, expression: str):
        result = self.send("Runtime.evaluate", expression=expression, returnByValue=True)
        return result.get("result", {}).get("value")

    def wait_for(self, expression: str, timeout: int = 900) -> None:
        end = time.time() + timeout
        while time.time() < end:
            if self.js(expression):
                return
            time.sleep(1)
        raise TimeoutError(f"Timed out waiting for: {expression}")

    def screenshot(self, path: Path) -> None:
        import base64
        data = self.send("Page.captureScreenshot", format="png")["data"]
        path.write_bytes(base64.b64decode(data))
        print(f"  saved {path.relative_to(ROOT)}")


VISIBLE_IFRAME = "[...document.querySelectorAll('iframe')].find(f => f.offsetParent !== null)"
VISIBLE_ERROR = ("[...document.querySelectorAll('[data-testid=\"stAlert\"]')]"
                 ".find(a => a.offsetParent !== null)?.innerText")


def capture(browser: Browser, part: str) -> None:
    tab_text, button_text, prefix = PARTS[part]
    print(f"{part}: clicking '{tab_text}' -> '{button_text}' ...")
    browser.js(f"[...document.querySelectorAll('button[role=\"tab\"]')].find(b => b.innerText.includes('{tab_text}')).click()")
    time.sleep(1.5)
    browser.js(f"[...document.querySelectorAll('button')].find(b => b.innerText.trim() === \"{button_text}\" && b.offsetParent !== null).click()")

    browser.wait_for(f"!!({VISIBLE_IFRAME}) || !!({VISIBLE_ERROR})")
    error = browser.js(VISIBLE_ERROR)
    if error:
        raise RuntimeError(f"{part} failed in the app: {error}")
    time.sleep(3)  # let the result card finish rendering

    browser.js("window.scrollTo(0, 0); document.querySelector('[data-testid=\"stMain\"]')?.scrollTo(0, 0)")
    time.sleep(1)
    browser.screenshot(SCREENSHOTS / f"{prefix}_1.png")
    browser.js(f"({VISIBLE_IFRAME}).scrollIntoView({{block: 'start'}})")
    time.sleep(1.5)
    browser.screenshot(SCREENSHOTS / f"{prefix}_2.png")


def main(parts: list[str]) -> None:
    SCREENSHOTS.mkdir(exist_ok=True)
    app = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(APP), "--server.headless", "true",
         "--server.port", str(APP_PORT)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    chrome = subprocess.Popen([
        CHROME, "--headless=new", f"--remote-debugging-port={CHROME_PORT}",
        f"--user-data-dir={tempfile.mkdtemp()}", "--no-first-run", "--hide-scrollbars",
        f"--window-size={WIDTH},{HEIGHT}", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(4)
        browser = Browser(CHROME_PORT)
        browser.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
        browser.send("Emulation.setDeviceMetricsOverride", width=WIDTH, height=HEIGHT, deviceScaleFactor=ZOOM, mobile=False)
        for part in parts:
            browser.send("Page.navigate", url=f"http://localhost:{APP_PORT}")
            browser.wait_for("document.querySelectorAll('button[role=\"tab\"]').length === 4", timeout=60)
            time.sleep(2)
            capture(browser, part)
    finally:
        chrome.terminate()
        app.terminate()


if __name__ == "__main__":
    main(sys.argv[1:] or ["part3", "part4"])
