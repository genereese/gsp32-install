# Version 64: every install at 115200, no speed tests; status "Installing Version N (45%)"; one retry after a write error
import sys, os, http.server, threading, functools
from playwright.sync_api import sync_playwright
here = os.path.dirname(os.path.abspath(__file__)); site = os.path.dirname(here)
SHOTS = os.environ.get("SHOTS", "/tmp")
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8783), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)
def run(b, init="", shots=False):
    pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script("window.__ver = '47';" + init)
    pg.add_init_script("""window.__status = []; addEventListener('DOMContentLoaded', () => { const el = document.getElementById('board-status');
      new MutationObserver(() => window.__status.push([el.textContent, el.classList.contains('erasing')])).observe(el, {childList: true, characterData: true, subtree: true}); });""")
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.goto("http://127.0.0.1:8783/index.html"); pg.wait_for_timeout(300); pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(4500)
    if shots: pg.screenshot(path=SHOTS + "/v64-install-idle.png")
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install")
    if shots:
        pg.wait_for_timeout(250); pg.screenshot(path=SHOTS + "/v64-install-busy.png")
    pg.wait_for_timeout(5000)
    log = [l for l in pg.evaluate("window.__log") if isinstance(l, str)]
    return pg, log, pg.evaluate("window.__status")
with sync_playwright() as p:
    b = p.chromium.launch()
    pg, log, st = run(b, shots=True)
    texts = [t for t, _ in st]
    check("written once at 115200, no speed change", [l for l in log if l.startswith(("write", "change"))] == ["write at 115200"], str(log[-8:]))
    check("full image, erase all", any("eraseAll true" in l for l in log))
    check("status reads Installing Version N (45%)", any(t.startswith("Installing ") and t.endswith("%)") and "Baud" not in t for t in texts), str(texts[-5:]))
    check("no speed wording anywhere", not any("Calibrat" in t or "Baud" in t or "Didn't Work" in t for t in texts) and "baud" not in pg.inner_text("#console-out").lower().replace("baud:", ""), str(texts))
    check("percent only grows", (lambda ps: ps == sorted(ps))([int(t.rsplit("(", 1)[1].rstrip("%)")) for t in texts if t.startswith("Installing ") and t.endswith("%)")]))
    check("installed", "Installed" in pg.inner_text("body"))
    check("footer says Flasher Version 115", "Flasher Version 115" in pg.text_content(".flasher-version"))
    pg.close()
    pg, log, st = run(b, "window.__failWriteAt = [115200];")
    w = [l for l in log if l.startswith("write")]
    check("a write error gets one fresh retry", w == ["write at 115200", "write at 115200"] and "Installed" in pg.inner_text("body"), str(w))
    check("retry explained in the console", "Connecting again and writing it again (2 of 3)" in pg.inner_text("#console-out"))
    pg.close(); b.close()
print("FAILS", fails); sys.exit(1 if fails else 0)
