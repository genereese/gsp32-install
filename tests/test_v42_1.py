# Version 42.1: the design system (tokens, two weights, restored sizes), the boot loop with Install still clickable,
#  the leave-page warning while installing, the saved install note leading to Recover, and the GSP32 check countdown
import sys, http.server, threading, functools, os
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); here = os.path.dirname(os.path.abspath(__file__))
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8772), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
U = "http://127.0.0.1:8772/index.html"
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra); sys.stdout.flush()
def page(b, init=""):
    pg = b.new_page(viewport={"width": 1280, "height": 900}); pg.add_init_script(path=here + "/mock.js")
    if init: pg.add_init_script(init)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.goto(U); pg.wait_for_timeout(300); return pg
def style(pg, sel, prop):
    return pg.evaluate("getComputedStyle(document.querySelector(%r))[%r]" % (sel, prop))
with sync_playwright() as p:
    b = p.chromium.launch()

    # Design system: no root scale, 15 px body, line height 1.45, two weights, restored sizes
    pg = page(b)
    check("root font 16 px (no % scale)", pg.evaluate("getComputedStyle(document.documentElement).fontSize") == "16px")
    check("body 15 px, line height about 1.45", style(pg, "body", "fontSize") == "15px" and abs(float(style(pg, "body", "lineHeight")[:-2]) - 21.75) < 0.1)
    check("steps row back to 14.72 px, regular weight", style(pg, ".steps-row", "fontSize") == "14.72px" and style(pg, ".steps-row", "fontWeight") == "400")
    check("Get Started 46 px tall", pg.evaluate("document.getElementById('connect').offsetHeight") >= 46)
    pg.click("#connect"); pg.wait_for_timeout(800)
    check("Console heading back to 16.8 px", style(pg, ".console-bar h3", "fontSize") == "16.8px")
    check("console text stays 13.6 px", style(pg, "#console-out", "fontSize") == "13.6px")
    check("card title clearly larger (18 px, 600)", style(pg, "#board-chip", "fontSize") == "18px" and style(pg, "#board-chip", "fontWeight") == "600")
    check("console buttons regular weight", style(pg, "#copy-log", "fontWeight") == "400")
    check("cards 16 px apart", abs(pg.evaluate("document.getElementById('console-card').getBoundingClientRect().top - document.getElementById('console').getBoundingClientRect().bottom") - 16) < 0.5)
    weights = set(pg.evaluate("[...document.querySelectorAll('body *')].filter(e => e.offsetParent).map(e => getComputedStyle(e).fontWeight)"))
    check("only weights 400 and 600 on screen", weights <= {"400", "600"}, weights)
    pg.close()

    # Boot loop: Install stays clickable, then Incomplete Install Detected with Recover GSP32
    pg = page(b, "window.__bootLoop = true")
    pg.click("#connect"); pg.wait_for_timeout(800); pg.click("#reset"); pg.wait_for_timeout(1200)
    check("booting: button row still there and clickable", pg.is_visible("#install-btn") and pg.is_enabled("#install-btn"))
    pg.wait_for_timeout(2500)
    check("boot loop: Incomplete Install Detected", "Incomplete Install Detected" in pg.inner_text("#board-status") and "Incomplete Install Detected" in pg.inner_text("#board-state"))
    check("boot loop: primary Recover GSP32", pg.inner_text("#install-btn") == "Recover/Install GSP32" and "primary" in pg.get_attribute("#install-btn", "class") and pg.is_enabled("#install-btn"))
    check("boot loop: no countdown left", not pg.is_visible("#check-wait"))
    pg.click("#install-btn"); pg.wait_for_timeout(500)
    check("Recover opens the erase and install step", pg.is_visible("#start-install"))
    pg.close()

    # Invalid header alone (one boot) is enough
    pg = page(b, "window.__other = true")
    pg.click("#connect"); pg.wait_for_timeout(600)
    pg.evaluate("window.gsp32.appendConsole('ota data partition invalid, falling back to factory\\r\\n')"); pg.wait_for_timeout(300)
    check("ROM error line: Recover GSP32", pg.inner_text("#install-btn") == "Recover/Install GSP32")
    pg.close()

    # Saved note of an unfinished install: Recover right away; cleared after a good install
    # Version 81: the connect probe (Version 80) resets the board, and the mock then boots GSP32, which rightly clears
    #  the note (nothing to recover). A board that does not come back as GSP32 (__other) keeps it: Recover
    pg = page(b, "window.__other = true; if (!sessionStorage.getItem('seeded')) { sessionStorage.setItem('seeded', 1); localStorage.setItem('gsp32.flash', JSON.stringify({mac: 'f8:b3:b7:22:05:e8', version: '42', startedAt: 1, writing: true})); }")
    pg.click("#connect"); pg.wait_for_timeout(800)
    check("saved note: Recover GSP32 offered", pg.inner_text("#install-btn") == "Recover/Install GSP32" and "Incomplete Install" in pg.inner_text("#board-state"), pg.inner_text("#board-state"))
    pg.close()
    pg = page(b, "window.__eraseDelay = 1500")
    pg.click("#connect"); pg.wait_for_timeout(500)
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(700)
    note = pg.evaluate("JSON.parse(localStorage.getItem('gsp32.flash'))")
    check("install saves {mac, version, startedAt, writing} once erasing starts", note and set(note) == {"mac", "version", "startedAt", "writing"} and note["startedAt"] > 0 and note["mac"], note)
    leave = pg.evaluate("(() => { const e = new Event('beforeunload', {cancelable: true}); window.dispatchEvent(e); return e.defaultPrevented; })()")
    check("beforeunload asks while installing", leave)
    pg.wait_for_function("document.getElementById('wizard').hidden", timeout=20000); pg.wait_for_timeout(500)
    check("note cleared after the install", pg.evaluate("localStorage.getItem('gsp32.flash')") is None)
    leave = pg.evaluate("(() => { const e = new Event('beforeunload', {cancelable: true}); window.dispatchEvent(e); return e.defaultPrevented; })()")
    check("beforeunload quiet after the install", not leave)
    pg.close()

    # Countdown while checking for GSP32 (other firmware)
    pg = page(b, "window.__other = true")
    pg.click("#connect"); pg.wait_for_timeout(600); pg.click("#reset"); pg.wait_for_timeout(1500)
    t1 = pg.inner_text("#check-wait-text"); w1 = pg.evaluate("parseFloat(document.getElementById('check-wait-bar').style.width)")
    pg.wait_for_timeout(2000)
    t2 = pg.inner_text("#check-wait-text"); w2 = pg.evaluate("parseFloat(document.getElementById('check-wait-bar').style.width)")
    check("countdown shows 'Checking for GSP32… N s' and counts down", t1.startswith("Checking for GSP32\u2026") and t1.endswith(" s") and int(t2.split()[-2]) < int(t1.split()[-2]), (t1, t2))
    check("slim bar fills", w2 > w1 and pg.locator("#check-wait .progress").bounding_box()["height"] <= 5, (w1, w2))
    check("Install clickable during the countdown", pg.is_visible("#install-btn") and pg.is_enabled("#install-btn"))
    pg.wait_for_timeout(18500)
    check("countdown gone at No GSP32 Found", not pg.is_visible("#check-wait") and "No GSP32 Found" in pg.inner_text("#board-state"))
    pg.close()
print("fails", fails); sys.exit(1 if fails else 0)
