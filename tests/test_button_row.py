import sys, http.server, threading, functools, os
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=site); handler.log_message = lambda *a: None
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8768), handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
here = os.path.dirname(os.path.abspath(__file__)); fails = 0
FROZEN = "(() => { const _a = Element.prototype.animate; Element.prototype.animate = function(k, o) { const a = _a.call(this, k, o); a.pause(); return a; }; })()"
def run(b, name, gap=0, fail=False, frozen=False, reboot=False):
    global fails
    pg = b.new_page(viewport={"width": 1280, "height": 900}); pg.add_init_script(path=here + "/mock.js")
    pg.add_init_script("window.__ets = true; window.__bootGap = %d; window.__failFlash = %s" % (gap, "true" if fail else "false"))
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.goto("http://127.0.0.1:8768/index.html"); pg.wait_for_timeout(300); pg.click("#connect"); pg.wait_for_timeout(800)
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install")
    if frozen: pg.evaluate(FROZEN)  # from here finish events are held back, like a background tab
    pg.wait_for_timeout(gap + 2500)
    if fail: pg.click("#wizard-close") if pg.is_visible("#wizard-close") else None
    if reboot:  # the board restarts again later (reset button / reconnect)
        pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))"); pg.wait_for_timeout(gap + 2500)
    hidden = pg.evaluate("document.getElementById('board-actions').hidden || !!document.getElementById('board-actions').shutting")
    disabled = pg.evaluate("document.getElementById('install-btn').disabled")
    ok = not hidden and not disabled
    print(("PASS " if ok else "FAIL ") + name, "status=" + pg.inner_text("#board-status")[:40], "state=" + pg.inner_text("#board-state")[:40])
    fails += not ok; pg.close()
with sync_playwright() as p:
    b = p.chromium.launch()
    run(b, "R1 success, quick boot"); run(b, "R2 success, slow boot", gap=4000)
    run(b, "R3 success, held-back fold events", frozen=True)
    run(b, "R4 failure path", fail=True); run(b, "R5 failure, held-back fold events", fail=True, frozen=True)
    run(b, "R6 reboot after install", reboot=True); run(b, "R7 reboot after install, slow boot, held-back", gap=3000, reboot=True, frozen=True)
print("fails", fails); sys.exit(1 if fails else 0)
