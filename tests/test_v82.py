# Version 82 (Gene): Show Password under the Wi-Fi password field (the browser's eye icon goes away after blur);
#  each Wi-Fi window starts hidden. Shots /workspace/review/v82/
import sys, http.server, threading, functools, os, time
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); here = os.path.dirname(os.path.abspath(__file__))
SHOTS = "/workspace/review/v82"; os.makedirs(SHOTS, exist_ok=True)
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8782), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
U = "http://127.0.0.1:8782/index.html"
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra); sys.stdout.flush()
with sync_playwright() as p:
    b = p.chromium.launch()
    for w, h in ((1280, 900), (393, 852)):
        pg = b.new_page(viewport={"width": w, "height": h}); pg.add_init_script(path=here + "/mock.js")
        pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
        errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(U); pg.wait_for_timeout(300)
        pg.click("#connect"); pg.wait_for_selector("#wifi-setup:not([hidden])", timeout=20000); pg.click("#wifi-setup")
        pg.wait_for_selector("#wifi-list li", timeout=30000)
        pg.click("#wifi-list li:first-child label"); pg.click("#wifi-connect"); pg.wait_for_selector("#wifi-modal[open]")
        check("%d: Show Password under the field, unchecked, field hidden" % w,
              pg.inner_text("label[for=wifi-show]").strip() == "Show Password" and not pg.is_checked("#wifi-show") and pg.get_attribute("#wifi-password", "type") == "password"
              and pg.locator("#wifi-show").bounding_box()["y"] > pg.locator("#wifi-password").bounding_box()["y"])
        pg.fill("#wifi-password", "hunter22"); pg.click("#wifi-modal-title")  # blur
        pg.check("#wifi-show"); time.sleep(0.2)
        check("%d: checked shows the password, focus back in the field" % w, pg.get_attribute("#wifi-password", "type") == "text" and pg.evaluate("document.activeElement.id") == "wifi-password" and pg.input_value("#wifi-password") == "hunter22")
        pg.screenshot(path=SHOTS + "/flasher-show-password-%d.png" % w)
        pg.uncheck("#wifi-show"); check("%d: unchecked hides it again" % w, pg.get_attribute("#wifi-password", "type") == "password")
        pg.check("#wifi-show"); pg.click("#wifi-modal-cancel"); pg.wait_for_timeout(300)
        pg.click("#wifi-connect"); pg.wait_for_selector("#wifi-modal[open]")
        check("%d: a new Wi-Fi window starts hidden" % w, not pg.is_checked("#wifi-show") and pg.get_attribute("#wifi-password", "type") == "password")
        pg.screenshot(path=SHOTS + "/flasher-wifi-modal-%d.png" % w)
        check("%d: no page errors" % w, not errors, str(errors)); pg.close()
    b.close()
srv.shutdown()
print("FAILURES:", fails); sys.exit(1 if fails else 0)
