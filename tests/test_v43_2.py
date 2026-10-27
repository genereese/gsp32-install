# Version 43.2: Wi-Fi wizard under the status line, the status pulses during every wait with nothing moving, older
#  firmware is named at once on Change Wi-Fi, softer tab warning, and "Wi-Fi Connected! " keeps its link (item 7)
import sys, http.server, threading, functools, os, time
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); here = os.path.dirname(os.path.abspath(__file__))
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8774), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
U = "http://127.0.0.1:8774/index.html"
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra); sys.stdout.flush()
def page(b, init=""):
    pg = b.new_page(viewport={"width": 1280, "height": 900}); pg.add_init_script(path=here + "/mock.js")
    if init: pg.add_init_script(init)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.goto(U); pg.wait_for_timeout(300); return pg
def boot(pg):
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
SEEN = """(() => { window.__pulsed = false; const s = document.getElementById('board-status');
  new MutationObserver(() => { if (s.classList.contains('waiting') && getComputedStyle(s, '::before').animationName === 'erase-pulse') window.__pulsed = true; })
    .observe(s, {attributes: true, attributeFilter: ['class']}); })()"""
PULSE = "(() => { const s = document.getElementById('board-status'); return s.classList.contains('waiting') && getComputedStyle(s, '::before').animationName; })()"
with sync_playwright() as p:
    b = p.chromium.launch()

    # 1, 2, 7: wizard under the status line, pulse while scanning and connecting, Wi-Fi Connected! with its link
    pg = page(b, "window.__bootGap = 3000")
    check("warning: could, not will", pg.inner_text("#flash-warn") == "Changing Tabs Could Cause the Install to Fail", pg.inner_text("#flash-warn"))
    check("wizard after the status line, countdown and warning", pg.evaluate("""(() => { const w = document.getElementById('wizard');
      return ['board-status', 'check-wait', 'flash-warn'].every(id => document.getElementById(id).compareDocumentPosition(w) & Node.DOCUMENT_POSITION_FOLLOWING); })()"""))
    pg.click("#connect"); pg.wait_for_timeout(100); boot(pg); pg.wait_for_timeout(1500)
    check("device check (Checking for GSP32... N s): status pulses", pg.evaluate(PULSE) == "erase-pulse", pg.evaluate(PULSE))
    pg.wait_for_timeout(2500)
    pg.wait_for_selector("#wifi-setup:not([hidden])", timeout=8000)
    pg.evaluate(SEEN); pg.click("#wifi-setup")
    pg.wait_for_selector("#wifi-list li", timeout=30000); pg.wait_for_timeout(400)
    check("Wi-Fi scan: status pulsed", pg.evaluate("window.__pulsed"))
    check("networks listed: no pulse", not pg.evaluate(PULSE))
    gap = pg.evaluate("document.getElementById('wifi-list').getBoundingClientRect().top - document.getElementById('board-status').getBoundingClientRect().bottom")
    check("Wi-Fi list below 'Pick your network...'", gap > 0 and "Pick your network" in pg.inner_text("#board-status"), gap)
    pg.click("#wifi-list li:first-child label"); pg.click("#wifi-connect"); pg.fill("#wifi-password", "x-test-pass"); pg.click("#wifi-modal-connect"); pg.wait_for_timeout(100)
    check("connecting: status pulses", pg.evaluate(PULSE) == "erase-pulse", pg.evaluate(PULSE))
    pg.wait_for_function("document.getElementById('wizard').hidden", timeout=30000); pg.wait_for_timeout(300)
    text = pg.evaluate("document.getElementById('board-status').textContent")
    check("connected: space after 'Wi-Fi Connected!'", text.startswith("Wi-Fi Connected! Your device"), text[:40])
    link = pg.evaluate("(() => { const a = document.querySelector('#board-status a'); return a && [a.href, a.target, a.rel, a.textContent]; })()")
    check("connected: address is a link, new tab", link == ["http://192.168.2.77/", "_blank", "noopener", "http://192.168.2.77/"], link)
    check("connected: no pulse", not pg.evaluate(PULSE))
    boot(pg); pg.wait_for_timeout(5000)
    link2 = pg.evaluate("(() => { const a = document.querySelector('#board-status a'); return a && a.href; })()")
    check("after a device restart: link and space kept", link2 == "http://192.168.2.77/" and "Connected! Your" in pg.evaluate("document.getElementById('board-status').textContent"), link2)
    pg.close()

    # 3. Older firmware (no Listening line) on a board with Wi-Fi: named promptly, not 'did not answer'
    pg = page(b, "window.__oldFw = true; window.__noReady = true; window.__savedWifi = true")
    pg.click("#connect"); pg.wait_for_timeout(100); boot(pg); pg.wait_for_timeout(4500)
    pg.wait_for_selector("#wifi-setup:not([hidden])", timeout=5000)
    started = time.time(); pg.click("#wifi-setup")
    pg.wait_for_function("document.getElementById('board-status').textContent.includes('older GSP32')", timeout=25000)
    took = time.time() - started
    status = pg.inner_text("#board-status")
    check("old firmware: says so within 20 s", took < 20 and status == "This device runs an older GSP32. Install Version 43.1 or newer to change Wi-Fi here.", "%.1f s %s" % (took, status))
    check("old firmware: nothing sent to it", pg.evaluate("window.__pk") == 0, pg.evaluate("window.__pk"))
    pg.close()

    # 3b. Current firmware: Change Wi-Fi still works after a restart (not mistaken for an old one)
    pg = page(b, "window.__savedWifi = true")
    pg.click("#connect"); pg.wait_for_timeout(100); boot(pg); pg.wait_for_timeout(4500)
    pg.evaluate("window.__stopListening()"); pg.wait_for_timeout(300)
    pg.wait_for_selector("#wifi-setup:not([hidden])", timeout=5000); pg.click("#wifi-setup")
    pg.wait_for_selector("#wifi-list li", timeout=30000)
    check("43.1+ firmware: networks listed", "older" not in pg.inner_text("#board-status"))
    pg.close()
    b.close()
print("fails", fails); sys.exit(1 if fails else 0)
