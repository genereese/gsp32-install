# Version 39: "GSP32 Found" always names the version, also when the board's Improv Ready line was missed
import sys, http.server, threading, functools, os
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); here = os.path.dirname(os.path.abspath(__file__))
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8770), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, init in (("Ready line seen", "window.__ver = '38'"), ("Ready line missed", "window.__ver = '38'; window.__noReady = true")):
        pg = b.new_page(); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script(init)
        pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
        pg.goto("http://127.0.0.1:8770/index.html"); pg.wait_for_timeout(300); pg.click("#connect"); pg.wait_for_timeout(100)
        pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
        pg.wait_for_timeout(4500)
        check(name + ": GSP32 Version 38 Found", "GSP32 Version 38 Found" in pg.inner_text("#board-state"), repr(pg.inner_text("#board-state")))
        pg.close()
print("fails", fails); sys.exit(1 if fails else 0)
