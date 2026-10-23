# Flasher Version 110: after a verified native-USB install (VID 0x303A), Checking for GSP32 cannot sit there.
#  A ROM line with no GSP32, or the port leaving, forces Tap RST / pick the new port, then Next / Set Up Wi-Fi.
#  During that check the console stays usable (wifi() can be typed) and Cancel ends it. The post-install guide
#  offers Set Up Wi-Fi Instead, the same button as the pre-install BOOT guide. A classic port still locks the console.
import sys, http.server, threading, functools, os
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); here = os.path.dirname(os.path.abspath(__file__))
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8842), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
U = "http://127.0.0.1:8842/index.html"
fails = 0
S3 = ("window.__downloadMode = true; window.__usb = { usbVendorId: 0x303a, usbProductId: 0x1001 };"
      " window.__chip = 'ESP32-S3 (QFN56) (revision v0.2)';"
      " window.__features = ['Wi-Fi', 'BT 5', 'Dual Core', '240MHz', 'Embedded PSRAM 8MB (AP_3v3)'];")
# Boot banner only: the runtime port's GSP32 lines never arrive on this download COM
STALL = ("window.__onWdt = () => { window.__downloadMode = false;"
         " setTimeout(() => window.__say('rst:0x15 (USB_UART_CHIP_RESET),boot:0x0 (DOWNLOAD(USB/UART0))\\r\\n'), 3500); };")
# Same port prints GSP32 before the handoff deadline
FOUND = ("window.__onWdt = () => { window.__downloadMode = false; setTimeout(() => window.__say("
         "'rst:0x1 (POWERON_RESET)\\r\\nGSP32 Improv Ready\\r\\nServer listening on port 80\\r\\n"
         "Web UI running in the background\\r\\nGSP32 Improv Listening\\r\\n'), 3500); };")
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra); sys.stdout.flush()
def wait_js(pg, js, ms=15000):
    try: pg.wait_for_function(js, timeout=ms); return True
    except Exception: return False
def shown(pg, sel):
    return pg.evaluate("(s) => { const e = document.querySelector(s); return !!e && !e.hidden && !e.shutting && !(e.sliding && !e.sliding.on) && e.getBoundingClientRect().width > 0; }", sel)
def page(b, init=""):
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.add_init_script(path=here + "/mock.js")
    if init: pg.add_init_script(init)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.route("**/gsp32-telemetry.genereese.workers.dev/**", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true}'))
    errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(U); pg.wait_for_timeout(300)
    return pg, errors
def install(pg):
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install")
CHECKING = "() => { const e = document.getElementById('check-wait'); return !e.hidden && e.offsetHeight > 20; }"
def installed(pg):
    return wait_js(pg, "() => /Installed/.test(document.getElementById('board-status').innerText)", 25000)
def connected(pg):
    # The port is open and the probe has finished (Install is clickable). Download mode is covered in test_s3_boardinfo.
    return wait_js(pg, "() => !document.getElementById('install-btn').disabled", 20000)
with sync_playwright() as p:
    b = p.chromium.launch()

    # 1. ROM banner and no GSP32: Checking shows, then Tap RST (not an endless countdown, not No GSP32 Found).
    #    Set Up Wi-Fi Instead reaches the network list.
    pg, errors = page(b, S3 + STALL)
    pg.click("#connect")
    check("native port connected", connected(pg), pg.inner_text("#board-state"))
    install(pg)
    check("stall: install finishes", installed(pg), pg.inner_text("#board-status"))
    check("stall: Checking shows", wait_js(pg, CHECKING, 12000))
    check("stall: console stays usable for wifi()", pg.is_enabled("#console-in") and pg.is_enabled("#console-send") and pg.get_attribute("#console-in", "placeholder") != "Busy ...")
    check("stall: Cancel is offered", not pg.evaluate("document.getElementById('check-wait-cancel').hidden"))
    pg.fill("#console-in", "wifi()"); pg.press("#console-in", "Enter")
    check("stall: wifi() left the box (it was sent)", pg.input_value("#console-in") == "")
    check("stall: Tap RST guide, not an endless check", wait_js(pg, "() => !document.getElementById('usb-guide').hidden && document.getElementById('usb-guide-title').innerText.includes('Tap RST')", 12000), pg.inner_text("#usb-guide-title"))
    pg.wait_for_timeout(500)
    check("stall: Checking is gone", pg.evaluate("document.getElementById('check-wait').hidden"))
    check("stall: still Installed, no Next yet, not No GSP32 Found", "Installed" in pg.inner_text("#board-status") and "Next:" not in pg.inner_text("#board-status") and "No GSP32 Found" not in pg.inner_text("#board-state"), pg.inner_text("#board-status") + " | " + pg.inner_text("#board-state"))
    check("stall: Set Up Wi-Fi Instead", shown(pg, "#usb-guide-wifi") and pg.inner_text("#usb-guide-wifi").strip() == "Set Up Wi-Fi Instead")
    pg.click("#usb-guide-wifi")
    check("stall: Set Up Wi-Fi Instead lists networks", wait_js(pg, "() => document.getElementById('wifi-list').innerText.includes('HomeNet')", 20000), pg.inner_text("#wifi-status"))
    check("stall: no page errors", not errors, errors)
    pg.close()

    # 2. Cancel during Checking forces the same guide at once
    pg, errors = page(b, S3 + STALL)
    pg.click("#connect"); connected(pg)
    install(pg); installed(pg)
    check("cancel: Checking shows", wait_js(pg, CHECKING, 12000))
    pg.click("#check-wait-cancel")
    check("cancel: Tap RST guide at once", wait_js(pg, "() => !document.getElementById('usb-guide').hidden && document.getElementById('usb-guide-title').innerText.includes('Tap RST')", 4000), pg.inner_text("#usb-guide-title"))
    pg.wait_for_timeout(400)
    check("cancel: Checking is gone", pg.evaluate("document.getElementById('check-wait').hidden"))
    check("cancel: console usable afterwards", pg.is_enabled("#console-in"))
    check("cancel: no page errors", not errors, errors)
    pg.close()

    # 3. GSP32 lines on this port before the deadline: Next and Set Up Wi-Fi, no guide, no leftover Checking
    pg, errors = page(b, S3 + FOUND)
    pg.click("#connect"); connected(pg)
    install(pg)
    check("found: install finishes", installed(pg), pg.inner_text("#board-status"))
    check("found: Set Up Wi-Fi in the row", wait_js(pg, "() => { const e = document.getElementById('wifi-setup'); return !e.hidden && !e.disabled; }", 12000))
    pg.wait_for_timeout(400)
    check("found: Next step", "Next: click Set Up Wi-Fi" in pg.inner_text("#board-status"), pg.inner_text("#board-status"))
    check("found: guide stayed folded", pg.evaluate("document.getElementById('usb-guide').hidden"))
    check("found: Checking is gone", pg.evaluate("document.getElementById('check-wait').hidden"))
    check("found: GSP32 named", "GSP32" in pg.inner_text("#board-state"), pg.inner_text("#board-state"))
    check("found: no page errors", not errors, errors)
    pg.close()

    # 4. The download port leaves during Checking: pick the new port, Checking does not stay
    pg, errors = page(b, S3 + STALL)
    pg.click("#connect"); connected(pg)
    install(pg); installed(pg)
    check("unplug: Checking shows", wait_js(pg, CHECKING, 12000))
    pg.evaluate("window.__unplug()")
    check("unplug: pick the new port", wait_js(pg, "() => !document.getElementById('usb-guide').hidden && document.getElementById('usb-guide-title').innerText.trim() === 'Pick the Port Again'", 8000), pg.inner_text("#usb-guide-title"))
    pg.wait_for_timeout(500)
    check("unplug: Checking is gone", pg.evaluate("document.getElementById('check-wait').hidden"))
    check("unplug: Set Up Wi-Fi Instead", shown(pg, "#usb-guide-wifi") and pg.inner_text("#usb-guide-wifi").strip() == "Set Up Wi-Fi Instead")
    check("unplug: not the plain disconnect line", "USB port changed" in pg.inner_text("#console-out") and "The board disconnected" not in pg.inner_text("#console-out"))
    check("unplug: no page errors", not errors, errors)
    pg.close()

    # 5. Classic port: the countdown still locks the console, and Cancel is not offered
    pg, errors = page(b, "window.__other = true")
    pg.click("#connect")
    check("classic: connected", wait_js(pg, "() => !document.getElementById('install-btn').disabled", 20000))
    pg.click("#reset")
    check("classic: Checking shows", wait_js(pg, CHECKING, 10000))
    check("classic: console stays locked", not pg.is_enabled("#console-in") and not pg.is_enabled("#console-send") and pg.get_attribute("#console-in", "placeholder") == "Busy ...")
    check("classic: no Cancel", pg.evaluate("document.getElementById('check-wait-cancel').hidden"))
    check("classic: no page errors", not errors, errors)
    pg.close()

print("fails", fails); sys.exit(1 if fails else 0)
