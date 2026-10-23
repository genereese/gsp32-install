# Version 48 (flasher polish): Check It Out, X close, slideshow, busy console, Send button, version shown
import sys, http.server, threading, functools, os
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); here = os.path.dirname(os.path.abspath(__file__))
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8813), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
shots = sys.argv[1] if len(sys.argv) > 1 else None
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.goto("http://127.0.0.1:8813/index.html"); pg.wait_for_timeout(1200)
    check("heading Check It Out", pg.inner_text("#tour-title") == "Check It Out")
    check("flasher shows its version", "Flasher Version 110" in pg.inner_text("body"))
    check("strip visible without scrolling at 1440x900", pg.locator(".tour-thumb >> nth=0").bounding_box()["y"] < 900, str(pg.locator(".tour-thumb >> nth=0").bounding_box()))
    art = pg.locator(".step-art >> nth=0").bounding_box(); txt = pg.locator(".steps-row li span >> nth=0").bounding_box()
    check("V50: slim steps, icon left of its text, 40px", art["x"] + art["width"] <= txt["x"] + 1 and round(art["width"]) == 40)
    n = pg.locator(".tour-thumb").count()
    pg.click(".tour-thumb >> nth=0"); pg.wait_for_timeout(400)
    check("X close, no Close text button", pg.inner_text("#tour-close").strip() == "" and pg.locator("#tour-close svg").count() == 1 and pg.get_attribute("#tour-close", "aria-label") == "Close")
    t0 = pg.inner_text("#tour-modal-title")
    check("counter 1 of N", pg.inner_text("#tour-count") == f"1 of {n}")
    pg.click("#tour-next"); pg.wait_for_timeout(300)
    check("next changes slide", pg.inner_text("#tour-count") == f"2 of {n}" and pg.inner_text("#tour-modal-title") != t0)
    if shots: pg.screenshot(path=shots + "/flasher-after-slideshow-1440.png")
    pg.keyboard.press("ArrowLeft"); pg.wait_for_timeout(200)
    check("left arrow back", pg.inner_text("#tour-count") == f"1 of {n}")
    pg.keyboard.press("ArrowLeft"); pg.wait_for_timeout(200)
    check("wraps to last", pg.inner_text("#tour-count") == f"{n} of {n}")
    pg.click("#tour-close"); pg.wait_for_timeout(300)
    check("X closes", not pg.is_visible("#tour-modal"))
    pg.close()
    pg = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True)
    pg.goto("http://127.0.0.1:8813/index.html"); pg.wait_for_timeout(1000)
    xs = [pg.locator(".steps-row li:not(.arrow) >> nth=%d" % i).bounding_box() for i in range(3)]
    check("V50: steps stack, one per line, inside 390", max(x["x"] + x["width"] for x in xs) <= 390 and len({round(x["y"]) for x in xs}) == 3, str(xs))
    pg.click(".tour-thumb >> nth=0"); pg.wait_for_timeout(300)
    pg.evaluate("""() => { const m = document.getElementById('tour-modal');
      const t = (type, x) => { const e = new Event(type, {bubbles: true}); e.touches = e.changedTouches = [{clientX: x}]; m.dispatchEvent(e); };
      t('touchstart', 300); t('touchend', 100); }""")
    check("swipe left goes next", pg.inner_text("#tour-count").startswith("2 of"))
    if shots: pg.screenshot(path=shots + "/flasher-after-slideshow-390.png")
    pg.close()
    # busy console: Wi-Fi step open disables typing, Cancel restores it
    pg = b.new_page(viewport={"width": 1440, "height": 900}); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script("window.__ver = '47'")
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.goto("http://127.0.0.1:8813/index.html"); pg.wait_for_timeout(300); pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(4500)
    check("idle: input and Send enabled", pg.is_enabled("#console-in") and not pg.is_visible("#console-note"))
    pg.fill("#console-in", "x"); pg.wait_for_timeout(50)
    check("Send button enabled when idle", pg.is_enabled("#console-send"))
    pg.click("#wifi-setup"); pg.wait_for_timeout(800)
    check("Wi-Fi step: input and Send disabled, V61 Busy ... with no tip", not pg.is_enabled("#console-in") and not pg.is_enabled("#console-send") and pg.get_attribute("#console-in", "placeholder") == "Busy ..." and pg.locator("#console-note").count() == 0)
    if shots: pg.screenshot(path=shots + "/flasher-after-busy-console-1440.png", full_page=True)
    pg.click("#wifi-cancel"); pg.wait_for_timeout(900)
    check("Cancel restores typing", pg.is_enabled("#console-in") and not pg.is_visible("#console-note"))
    pg.close()
print("fails", fails); sys.exit(1 if fails else 0)
