# Flasher Version 115.9 (GSP32-C Beta V125): Set Up Wi-Fi for GSP32-C. V121 and newer take Improv packets at any time
#  (even at the >>> prompt), so the flasher offers Set Up Wi-Fi, scans, connects and shows the web UI address; V117-V120
#  (no Improv) keep the "set Wi-Fi at its prompt" hint and get nothing sent
import sys, http.server, threading, functools, os
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); here = os.path.dirname(os.path.abspath(__file__))
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8825), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
U = "http://127.0.0.1:8825/index.html"
SECRET = "Sekr3t-Test-125"
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra); sys.stdout.flush()
def page(b, init=""):
    pg = b.new_page(viewport={"width": 1280, "height": 900}); pg.add_init_script(path=here + "/mock.js")
    if init: pg.add_init_script(init)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.goto(U); pg.wait_for_timeout(300); return pg
def boot(pg):
    pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(2500)
with sync_playwright() as p:
    b = p.chromium.launch()
    # 1. GSP32-C V125 at its prompt: found, Set Up Wi-Fi offered (the next step), scan, connect, address shown
    pg = page(b, "window.__gspc = '125'")
    boot(pg)
    st = pg.inner_text("#board-state")
    check("V125: GSP32-C Beta V125 Found, no prompt hint", "GSP32-C Beta V125 Found" in st and "gsp.wifi" not in st, st)
    check("V125: Set Up Wi-Fi shown and the next step", pg.is_visible("#wifi-setup") and "primary" in (pg.get_attribute("#wifi-setup", "class") or ""),
          pg.get_attribute("#wifi-setup", "class"))
    check("V125: no Ctrl-C sent", pg.evaluate("window.__ctrlc") == 0)
    pg.click("#wifi-setup")
    pg.wait_for_selector("#wifi-list li", timeout=30000)
    check("V125: networks listed", pg.locator("#wifi-list li").count() == 2, pg.inner_text("#wifi-status"))
    pg.click("#wifi-list li:first-child label"); pg.click("#wifi-connect"); pg.fill("#wifi-password", SECRET); pg.click("#wifi-modal-connect")
    pg.wait_for_function("document.getElementById('wizard').hidden", timeout=30000); pg.wait_for_timeout(300)
    check("V125: Wi-Fi Connected! with the address", pg.inner_text("#board-status").startswith("Wi-Fi Connected!") and "192.168.2.77" in pg.inner_text("#board-status"),
          pg.inner_text("#board-status"))
    check("V125: Open Web UI goes to the board", pg.get_attribute("#console-webui", "href") == "http://192.168.2.77/" and pg.is_visible("#console-webui"),
          pg.get_attribute("#console-webui", "href"))
    check("V125: still GSP32-C (an Improv answer doesn't make it GSP32)", "GSP32-C Beta V125" in pg.inner_text("#board-state"), pg.inner_text("#board-state"))
    check("V125: every packet reached a listening board", pg.evaluate("window.__badPk") == 0, pg.evaluate("window.__badPk"))
    check("V125: password not in the console", SECRET not in pg.inner_text("#console-out"))
    pg.close()
    # 2. GSP32-C V120 (no Improv): the prompt hint, no Set Up Wi-Fi, nothing sent
    pg = page(b, "window.__gspc = '120'")
    boot(pg); pg.wait_for_timeout(3000)
    st = pg.inner_text("#board-state")
    check("V120: prompt hint kept", "GSP32-C Beta V120 Found" in st and "gsp.wifi" in st, st)
    check("V120: no Set Up Wi-Fi", not pg.is_visible("#wifi-setup"))
    check("V120: nothing sent", pg.evaluate("window.__pk") == 0, pg.evaluate("window.__pk"))
    pg.close()
    # 3. Classic GSP32 unchanged: found, version asked once
    pg = page(b, "window.__ver = '116'")
    boot(pg); pg.wait_for_timeout(6000)
    check("GSP32 V116: still GSP32 Version 116 Found", "Version 116" in pg.inner_text("#board-state"), pg.inner_text("#board-state"))
    pg.close()
print("fails", fails); sys.exit(1 if fails else 0)
