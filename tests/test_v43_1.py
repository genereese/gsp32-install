# Version 43.1: Improv only while the board listens (no Ctrl-C loop on a running board, version asked once),
#  Change Wi-Fi on a set-up board (restart, scan, connect), Wi-Fi details never sent to a board that is not listening,
#  and the status/progress line under the button row
import sys, http.server, threading, functools, os
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); here = os.path.dirname(os.path.abspath(__file__))
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8773), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
U = "http://127.0.0.1:8773/index.html"
SECRET = "Sekr3t-Test-43.1"
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra); sys.stdout.flush()
def page(b, init=""):
    pg = b.new_page(viewport={"width": 1280, "height": 900}); pg.add_init_script(path=here + "/mock.js")
    if init: pg.add_init_script(init)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.goto(U); pg.wait_for_timeout(300); return pg
def resets(pg):
    return pg.evaluate("window.__log.filter(x => x === 'RESET').length")
RUNNING = "Web UI running in the background\\r\\nConnection successful\\r\\nNetwork config: ('192.168.2.77', '255.255.255.0', '192.168.2.1', '192.168.2.1')\\r\\nmain.py running\\r\\n"
with sync_playwright() as p:
    b = p.chromium.launch()

    # 1. A running board (no boot seen, its listening window long over): connecting sends nothing at all
    pg = page(b)
    pg.click("#connect"); pg.wait_for_timeout(300)
    pg.evaluate("window.__say(%r)" % RUNNING.replace("\\r\\n", "\r\n"))
    pg.wait_for_timeout(8000)
    check("running board: no Improv, no Ctrl-C byte sent in 8 s", pg.evaluate("window.__pk") == 0 and pg.evaluate("window.__ctrlc") == 0, pg.evaluate("[window.__pk, window.__ctrlc]"))
    check("running board: still GSP32 Found", "GSP32" in pg.inner_text("#board-state"), pg.inner_text("#board-state"))
    pg.close()

    # 2. A boot with the listening line: the version is asked exactly once, the board answers, no retries
    pg = page(b, "window.__ver = '43.1'")
    pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(9000)
    check("boot: version asked once", pg.evaluate("window.__info") == 1 and pg.evaluate("window.__pk") == 1, pg.evaluate("[window.__info, window.__pk]"))
    check("boot: GSP32 Version 43.1 Found", "Version 43.1" in pg.inner_text("#board-state"), pg.inner_text("#board-state"))
    pg.close()

    # 3. Old firmware (no listening line) after a boot: never probed
    pg = page(b, "window.__oldFw = true; window.__noReady = true")
    pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(8000)
    check("old firmware: nothing sent", pg.evaluate("window.__pk") == 0, pg.evaluate("window.__pk"))
    pg.close()

    # 4. Change Wi-Fi on a set-up board whose window is over: restart, wait for Listening, scan, connect
    pg = page(b, "window.__savedWifi = true")
    pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(4500)
    pg.evaluate("window.__stopListening()"); pg.wait_for_timeout(300)
    before = resets(pg)
    pg.wait_for_selector("#wifi-setup:not([hidden])", timeout=5000)
    pg.click("#wifi-setup")
    pg.wait_for_selector("#wifi-list li", timeout=30000)
    check("change Wi-Fi: board restarted first", resets(pg) == before + 1, resets(pg) - before)
    check("change Wi-Fi: networks listed", pg.locator("#wifi-list li").count() == 2, pg.inner_text("#wifi-status"))
    pg.click("#wifi-list li:first-child label"); pg.fill("#wifi-password", SECRET); pg.click("#wifi-connect")
    pg.wait_for_function("document.getElementById('wizard').hidden", timeout=30000); pg.wait_for_timeout(300)
    check("change Wi-Fi: Wi-Fi Connected!", pg.inner_text("#board-status").startswith("Wi-Fi Connected!"), pg.inner_text("#board-status"))
    check("change Wi-Fi: no packet reached a quiet board", pg.evaluate("window.__badPk") == 0, pg.evaluate("window.__badPk"))
    check("change Wi-Fi: password not in the console", SECRET not in pg.inner_text("#console-out"))
    pg.close()

    # 5. The session ends before Connect: the name and password are never sent
    pg = page(b)
    pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(1500)
    pg.wait_for_selector("#wifi-setup:not([hidden])", timeout=5000)
    pg.click("#wifi-setup"); pg.wait_for_selector("#wifi-list li", timeout=30000)
    pg.evaluate("window.__stopListening()"); pg.wait_for_timeout(300)
    pk = pg.evaluate("window.__pk")
    pg.click("#wifi-list li:first-child label"); pg.fill("#wifi-password", SECRET); pg.click("#wifi-connect")
    pg.wait_for_timeout(4000)
    check("session gone: nothing sent after Off", pg.evaluate("window.__pk") == pk and SECRET not in (pg.evaluate("window.__badBytes") or ""), pg.evaluate("[window.__pk, %d]" % pk))
    check("session gone: says the board stopped listening", "stopped listening" in pg.inner_text("#wifi-error"), pg.inner_text("#wifi-error"))
    check("session gone: password not in the console", SECRET not in pg.inner_text("#console-out"))
    pg.close()

    # 6. The status/progress line sits under the button row; buttons coming and going never move it vertically
    pg = page(b)
    pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(600)
    order = pg.evaluate("(() => { const a = document.getElementById('board-actions'), s = document.getElementById('board-status'); return !!(a.compareDocumentPosition(s) & Node.DOCUMENT_POSITION_FOLLOWING); })()")
    check("status line after the button row", order)
    pg.wait_for_timeout(3000)
    vis = pg.evaluate("(() => { const a = document.getElementById('board-actions').getBoundingClientRect(), s = document.getElementById('board-status'); return s.hidden ? 'hidden' : s.getBoundingClientRect().top - a.bottom; })()")
    check("status line below the buttons when shown", vis == "hidden" or vis >= 0, vis)
    if SHOTS := os.environ.get("SHOTS"): pg.screenshot(path=SHOTS + "/v43_1-row.png")
    pg.close()
    b.close()
print("fails", fails); sys.exit(1 if fails else 0)
