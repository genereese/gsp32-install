# Version 37: Open GSP32 Web UI waits greyed for Wi-Fi on a board with saved Wi-Fi (no layout shift), fades to blue
import sys, http.server, threading, functools, os
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); here = os.path.dirname(os.path.abspath(__file__))
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=site)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8769), handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)
def page(b, init):
    pg = b.new_page(viewport={"width": 1280, "height": 900}); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script(init)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.goto("http://127.0.0.1:8769/index.html"); pg.wait_for_timeout(300); pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    return pg
W = "document.getElementById('console-webui')"
with sync_playwright() as p:
    b = p.chromium.launch()
    # 1: saved Wi-Fi, connects after 3 s
    pg = page(b, "window.__savedWifi = true; window.__wifiDelay = 3000")
    pg.wait_for_timeout(1500)
    vis = pg.is_visible("#console-webui"); cls = pg.evaluate(W + ".className"); state = pg.inner_text("#board-state")
    box1 = pg.locator("#console-webui").bounding_box(); sbox1 = pg.locator("#board-state").bounding_box()
    check("waiting: button shown greyed", vis and "waiting" in cls and pg.evaluate(W + ".getAttribute('aria-disabled')") == "true", cls)
    check("waiting: note says Waiting for Wi-Fi", "Waiting for Wi-Fi" in state, repr(state))
    n = len(b.contexts[0].pages); pg.click("#console-webui", force=True); pg.wait_for_timeout(300)
    check("waiting: click does nothing", len(b.contexts[0].pages) == n)
    check("waiting: no hover lift", pg.evaluate("getComputedStyle(%s).transform" % W) in ("none", "matrix(1, 0, 0, 1, 0, 0)"))
    pg.mouse.move(0, 0); pg.wait_for_timeout(2800)
    cls = pg.evaluate(W + ".className"); state = pg.inner_text("#board-state")
    box2 = pg.locator("#console-webui").bounding_box(); sbox2 = pg.locator("#board-state").bounding_box()
    check("connected: blue primary, clickable", "primary" in cls and "waiting" not in cls and pg.evaluate(W + ".href").endswith("192.168.2.77/"), cls)
    check("connected: note shows the address", "192.168.2.77" in state, repr(state))
    check("no layout shift (button and note)", abs(box1["y"] - box2["y"]) < 1 and abs(box1["x"] - box2["x"]) < 1 and abs(sbox1["height"] - sbox2["height"]) < 1, (box1, box2, sbox1["height"], sbox2["height"]))
    check("fade uses a transition", "background-color 0.5s" in pg.evaluate("getComputedStyle(%s).transition" % W))
    pg.close()
    # 2: saved Wi-Fi that never connects (timer shortened by the clock)
    pg = b.new_page(); pg.close()
    pg = page(b, "window.__savedWifi = true; window.__wifiNever = true; const _st = window.setTimeout; window.setTimeout = (f, ms, ...a) => _st(f, ms === 20000 ? 2000 : ms, ...a)")
    pg.wait_for_timeout(3500)
    state = pg.inner_text("#board-state"); cls = pg.evaluate(W + ".className")
    check("no Wi-Fi after the wait: Wi-Fi Didn't Connect, still grey", "Wi-Fi Didn't Connect" in state and "waiting" in cls and pg.is_visible("#console-webui"), repr(state))
    pg.close()
    # 3: no saved Wi-Fi: hidden as before
    pg = page(b, ""); pg.wait_for_timeout(2500)
    check("no saved Wi-Fi: button hidden", not pg.is_visible("#console-webui") and "Wi-Fi" not in pg.inner_text("#board-state").replace("Set Up Wi-Fi", ""), repr(pg.inner_text("#board-state")))
    pg.close()
print("fails", fails); sys.exit(1 if fails else 0)
