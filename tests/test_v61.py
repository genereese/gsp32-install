# Version 61: hard time limits on connect and every speed step, clean fallback, Calibrating Transfer Speed..., console box
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
here = os.path.dirname(os.path.abspath(__file__))
import http.server, threading, functools
from playwright.sync_api import sync_playwright
site = os.path.dirname(here)
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8781), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)
def run(b, init="", wait=5000, shot=None):
    pg = b.new_page(); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script("window.__ver = '47';" + init)
    pg.add_init_script("""window.__status = []; addEventListener('DOMContentLoaded', () => { const el = document.getElementById('board-status');
      new MutationObserver(() => window.__status.push([el.textContent, el.classList.contains('erasing')])).observe(el, {childList: true, characterData: true, subtree: true}); });""")
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.goto("http://127.0.0.1:8781/index.html"); pg.wait_for_timeout(300); pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(4500)
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install")
    t0 = time.time()
    if shot: pg.wait_for_timeout(400); shot(pg)
    pg.wait_for_timeout(wait)
    return pg, [l for l in pg.evaluate("window.__log") if isinstance(l, str)], [t for t, _ in pg.evaluate("window.__status")], pg.evaluate("window.__status")
def busy_shot(pg):
    pg.locator("#console-form").screenshot(path=os.environ.get("SHOTS", "/tmp") + "/v61-console-busy.png")
    check("console box says just Busy ...", pg.get_attribute("#console-in", "placeholder") == "Busy ...")
    check("no tip under the box", pg.locator("#console-note").count() == 0)
    i = pg.locator("#console-in").bounding_box(); s = pg.locator("#console-send").bounding_box()
    check("Send flush top/right/bottom", abs(i["y"] - s["y"]) < 1.5 and abs(i["y"] + i["height"] - s["y"] - s["height"]) < 1.5 and abs(i["x"] + i["width"] - s["x"] - s["width"]) < 1.5, str((i, s)))
    r = pg.evaluate("getComputedStyle(document.getElementById('console-send')).borderRadius")
    check("straight left edge, right corners 8 px", r == "0px 8px 8px 0px", r)
with sync_playwright() as p:
    b = p.chromium.launch()
    # 1: the V60 hang: real flushInput semantics, nothing else wrong. V60 never got past it.
    pg, log, texts, st = run(b, shot=busy_shot)
    check("no hang on flushInput: written at 921600", "write at 921600" in log, str([l for l in log if l.startswith(("write", "open", "change"))]))
    check("Calibrating Transfer Speed... shown, pulsing", any("Calibrating Transfer Speed..." in t and e for t, e in st), str(texts[:6]))
    check("installed", "Installed" in pg.inner_text("body"))
    pg.close()
    # 2: 921600 hangs forever -> dropped within ~3 s, 460800 used
    pg, log, texts, st = run(b, "window.__hangBaud = [921600];", wait=9000)
    check("stuck 921600 dropped, written at 460800", "hang at 921600" in log and "write at 460800" in log, str([l for l in log if l.startswith(("write", "hang", "change"))]))
    check("step-down notice visible", any("921,600 Baud Didn't Work" in t or "Retrying at 460,800" in t for t in texts), str(texts))
    check("installed after fallback", "Installed" in pg.inner_text("body"))
    pg.close()
    # 3: every fast rate hangs -> 115200
    pg, log, texts, st = run(b, "window.__hangBaud = [921600, 460800, 230400];", wait=16000)
    check("all fast rates hang: written at 115200", "write at 115200" in log, str([l for l in log if l.startswith(("write", "hang"))]))
    pg.close()
    # 4: connect hangs once -> retried; hangs always -> clear error with Retry
    pg, log, texts, st = run(b, "window.__hangConnect = 1;", wait=16000)
    check("one stuck connect is retried", "write at 921600" in log, str(texts[-3:]))
    pg.close()
    pg, log, texts, st = run(b, "window.__hangConnect = 9;", wait=28000)
    body = pg.inner_text("body")
    check("connect never answers: clear error", "did not answer" in body, texts[-1] if texts else "")
    check("Try Again offered", pg.locator("#error-retry:visible").count() > 0)
    check("nothing saved", pg.evaluate("Object.keys(localStorage).filter(k => k.startsWith('gsp32-baud:')).length") == 0)
    # 6: Version 61 hotfix: an install that hung before erasing leaves the note; the board still runs GSP32. After a
    #  reload the boot banner must not bring back "Click Recover GSP32" beside a Reinstall GSP32 button
    pg = b.new_page(); pg.add_init_script(path=here + "/mock.js")
    pg.add_init_script("window.__ver = '60'; window.__noReady = true; localStorage.setItem('gsp32.flash', JSON.stringify({mac: 'f8:b3:b7:22:05:e8', version: '60', startedAt: 1}))")
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.goto("http://127.0.0.1:8781/index.html"); pg.wait_for_timeout(300); pg.click("#connect"); pg.wait_for_timeout(300)
    check("note found: Recover GSP32 offered with the notice", pg.inner_text("#install-btn") == "Recover GSP32" and pg.is_visible("#install-btn"))
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))"); pg.wait_for_timeout(4000)
    st = pg.inner_text("#board-status") if pg.is_visible("#board-status") else ""
    check("GSP32 seen: note cleared, no stale Recover text", pg.evaluate("localStorage.getItem('gsp32.flash')") is None and "Recover" not in st, st)
    check("button and status agree", ("Recover GSP32" in st) == (pg.inner_text("#install-btn") == "Recover GSP32"), pg.inner_text("#install-btn") + " / " + st)
    pg.close()
    # 7: the note is cleared by a successful install
    pg, log, texts, st = run(b)
    check("successful install clears the note", pg.evaluate("localStorage.getItem('gsp32.flash')") is None)
    pg.close(); b.close()
print("FAILS", fails); sys.exit(1 if fails else 0)
