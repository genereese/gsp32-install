# Version 75 (Gene): console pinned to the bottom when Install folds the buttons away; time left while writing
#  ("Installing Version N (45%, About 1 Minute Left)", only once settled); a Next step note after the install; Get
#  Started fetches versions.json again; new Check It Out slides, no Peer Manager note. Screenshots at 1440 and 393 px
import sys, os, http.server, threading, functools, re
from playwright.sync_api import sync_playwright
here = os.path.dirname(os.path.abspath(__file__)); site = os.path.dirname(here)
import oldsite; site = oldsite.overlay(site)  # Flasher 115.24: several releases come from the 115.23 list (tests/oldsite.py)
SHOTS = os.environ.get("SHOTS", "/tmp"); os.makedirs(SHOTS, exist_ok=True)
hits = []
class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.startswith("/versions.json"): hits.append(self.path)
        return super().do_GET()
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8784), functools.partial(H, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)
def atBottom(pg):
    return pg.evaluate("(() => { const c = document.getElementById('console-out'); return c.scrollHeight - c.scrollTop - c.clientHeight < 4; })()")
def open_(b, width, init=""):
    pg = b.new_page(viewport={"width": width, "height": 900 if width > 500 else 852})
    pg.add_init_script(path=here + "/mock.js"); pg.add_init_script(path=here + "/classic.js"); pg.add_init_script("window.__ver = '47';" + init)
    pg.add_init_script("""window.__status = []; addEventListener('DOMContentLoaded', () => { const el = document.getElementById('board-status');
      new MutationObserver(() => window.__status.push(el.textContent)).observe(el, {childList: true, characterData: true, subtree: true}); });""")
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.goto("http://127.0.0.1:8784/index.html"); pg.wait_for_timeout(300)
    return pg
def connect(pg):
    pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(4500)
with sync_playwright() as p:
    b = p.chromium.launch()
    for width in (1440, 393):
        tag = str(width)
        pg = open_(b, width, "window.__flashDelay = 2500; window.__eraseDelay = 1500;")
        check(tag + ": no Peer Manager note", "Peer Manager" not in pg.inner_text("body") and pg.locator(".release-note").count() == 0)
        pg.locator("#tour").scroll_into_view_if_needed(); pg.wait_for_timeout(800)
        titles = pg.locator(".tour-thumb span").all_inner_texts()
        # Version 106 (Gene): ten slides of the current web UI (the Experiment menu's Sandbox and Examples added)
        check(tag + ": Check It Out slides", "Code Editor" in titles and "Sandbox" in titles and "Examples" in titles and "Insert Wizards" not in titles and len(titles) == 10, str(titles))
        # Flasher Version 104 (Gene): the AI Helper is the first slide, the Settings slide is gone (still ten)
        check(tag + ": AI Helper first, Settings slide (Flasher 115.29: V135 tour)", titles[:1] == ["AI Helper"] and "Settings" in titles, str(titles))
        pg.screenshot(path=SHOTS + "/tour8-check-it-out-" + tag + ".png")
        pg.click(".tour-thumb >> nth=0"); pg.wait_for_timeout(600)
        check(tag + ": the AI slide's tour text", "Sandbox Files" in pg.inner_text("#tour-modal").title() and "Apply" in pg.inner_text("#tour-modal"))  # Flasher 115.29: V135 text
        pg.screenshot(path=SHOTS + "/tour8-ai-" + tag + ".png"); pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
        pg.click(".tour-thumb >> nth=3"); pg.wait_for_timeout(600)
        pg.screenshot(path=SHOTS + "/tour8-editor-" + tag + ".png"); pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
        pg.evaluate("window.scrollTo(0, 0)")
        before = len(hits); connect(pg)
        check(tag + ": Get Started fetches versions.json again", len(hits) == before + 1, str(hits))
        pg.evaluate("for (let i = 0; i < 120; i++) window.gsp32.appendConsole('boot line ' + i + '\\n')")
        pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install")
        pg.wait_for_timeout(900)
        check(tag + ": console pinned while the buttons fold away (erase line visible)", atBottom(pg) and "Erasing" in pg.inner_text("#board-status"))
        pg.screenshot(path=SHOTS + "/erasing-" + tag + ".png")
        pg.wait_for_function("/Left\\)$/.test(document.getElementById('board-status').textContent)", timeout=30000)
        st = pg.inner_text("#board-status")
        check(tag + ": time left in the status bar", re.fullmatch(r"Installing Version \d+(\.\d+)? \(\d+%, About (\d+ (Minutes|Seconds)|1 Minute) Left\)", st) is not None, st)
        pg.screenshot(path=SHOTS + "/time-left-" + tag + ".png")
        texts = pg.evaluate("window.__status")
        first = next(i for i, t in enumerate(texts) if "Left)" in t)
        check(tag + ": no time left before the estimate settles", any(re.fullmatch(r"Installing Version [\d.]+ \(\d+%\)", t) for t in texts[:first]), str(texts[:first])[-200:])
        pg.wait_for_function("/Installed/.test(document.getElementById('board-status').textContent)", timeout=40000); pg.wait_for_timeout(5500)
        st = pg.inner_text("#board-status")
        check(tag + ": Next step points to Set Up Wi-Fi", "Next: click Set Up Wi-Fi" in st and "GSP32 Web UI" in st, st)
        check(tag + ": console still at the bottom after the install", atBottom(pg))
        pg.screenshot(path=SHOTS + "/installed-next-step-" + tag + ".png")
        pg.close()
    pg = open_(b, 1100); connect(pg)
    pg.evaluate("for (let i = 0; i < 120; i++) window.gsp32.appendConsole('boot line ' + i + '\\n')")
    pg.evaluate("document.getElementById('console-out').scrollTop = 0"); pg.wait_for_timeout(100)
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(900)
    check("scrolled up by the user: the console stays where they put it", pg.evaluate("document.getElementById('console-out').scrollTop") < 5)
    texts = []
    pg.wait_for_function("/Installed/.test(document.getElementById('board-status').textContent)", timeout=20000)
    check("a fast write shows no time left", not any("Left" in t for t in pg.evaluate("window.__status")))
    pg.close(); b.close()
print("FAILS", fails); sys.exit(1 if fails else 0)
