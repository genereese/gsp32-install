# Flasher Version 114.2 (Gene's ESP32-C3 on COM13, GSP32 114.1 in safe mode): after a native-USB install the page sent
#  esptool's SYNC frame to a device that had already started; GSP32's REPL took the port and ate the first Set Up Wi-Fi.
#  1. look first: a C3 whose boot output is already there gets no SYNC frame; the first Set Up Wi-Fi lists networks
#  2. a board with no output yet when the check runs is still asked (SYNC sent), as before
#  3. "GSP32 Improv Listening" after the REPL prompt is not believed: Set Up Wi-Fi restarts the board first
#  4. a GSP32 that says it listens but never answers is restarted once and asked again (no Try Again)
#  5. appBooted() reads boot output, not download mode
import sys, http.server, threading, functools, os
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); here = os.path.dirname(os.path.abspath(__file__))
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8862), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
U = "http://127.0.0.1:8862/index.html"
fails = 0
C3 = ("window.__downloadMode = true; window.__usb = { usbVendorId: 0x303a, usbProductId: 0x1001 };"
      " window.__chip = 'ESP32-C3 (QFN32) (revision v0.4)';"
      " window.__features = ['Wi-Fi', 'BT 5 (LE)', 'Single Core', '160MHz', 'Embedded Flash 4MB (XMC)'];")
# The C3 restarts by RTS after the install (the mock's boot(): GSP32's lines 0.3 s later, before the 1.5 s check). A
#  SYNC frame then does what 114.1 in safe mode did: the REPL takes the port (packets eaten), the web UI still says Listening
STARTED = (" window.__onSync = () => { if (!window.__listen) return; window.__listen = false; window.__say('$ UUUUUUUU\\r\\nMicroPython v1.25.0 on 2025-04-15; ESP32C3 module with ESP32C3\\r\\n"
           "Type \"help()\" for more information.\\r\\n>>> '); setTimeout(() => window.__say('GSP32 Improv Listening\\r\\n'), 200); };")
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra); sys.stdout.flush()
def wait_js(pg, js, ms=15000):
    try: pg.wait_for_function(js, timeout=ms); return True
    except Exception: return False
def page(b, init=""):
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.add_init_script(path=here + "/mock.js"); pg.add_init_script(path=here + "/classic.js")
    if init: pg.add_init_script(init)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.route("**/gsp32-telemetry.genereese.workers.dev/**", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true}'))
    errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(U); pg.wait_for_timeout(300)
    return pg, errors
def installed(pg):
    return wait_js(pg, "() => /Installed/.test(document.getElementById('board-status').innerText)", 25000)
def connected(pg):
    return wait_js(pg, "() => !document.getElementById('install-btn').disabled", 20000)
def resets(pg):
    return pg.evaluate("window.__log.filter((x) => x === 'RESET').length")
def networks(pg, ms=40000):
    return wait_js(pg, "() => document.getElementById('wifi-list').innerText.includes('HomeNet')", ms)
def boot(pg, extra_ms=600):
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(extra_ms)
with sync_playwright() as p:
    b = p.chromium.launch()

    # 1. The C3 already started: no SYNC frame, the board's lines are read, the first Set Up Wi-Fi works
    pg, errors = page(b, C3 + STARTED)
    pg.click("#connect")
    check("c3: native port connected", connected(pg), pg.inner_text("#board-state"))
    before = pg.evaluate("window.__syncs || 0")
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install")
    check("c3: install finishes", installed(pg), pg.inner_text("#board-status"))
    check("c3: GSP32 found (its boot lines were kept)", wait_js(pg, "() => /GSP32/.test(document.getElementById('board-state').innerText) && !/No GSP32/.test(document.getElementById('board-state').innerText)", 12000), pg.inner_text("#board-state"))
    pg.wait_for_timeout(2500)
    check("c3: no SYNC frame sent to the started device", pg.evaluate("window.__syncs || 0") == before, pg.evaluate("[window.__syncs, window.__log.slice(-12)]"))
    check("c3: no Tap RST guide", pg.evaluate("document.getElementById('usb-guide').hidden"))
    pg.wait_for_selector("#wifi-setup:not([hidden])", timeout=8000)
    r0 = resets(pg)
    pg.click("#wifi-setup")
    check("c3: the first Set Up Wi-Fi lists networks", networks(pg, 20000), pg.inner_text("#wifi-status"))
    check("c3: no packet eaten", pg.evaluate("window.__badPk") == 0, pg.evaluate("window.__badBytes"))
    check("c3: no page errors", not errors, errors)
    pg.close()

    # 2. Nothing printed yet when the check runs (GSP32's lines come later): the ROM is still asked, as before
    pg, errors = page(b, C3)
    pg.click("#connect"); connected(pg)
    pg.evaluate("window.__bootGap = 3500")
    before = pg.evaluate("window.__syncs || 0")
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install")
    check("late: install finishes", installed(pg), pg.inner_text("#board-status"))
    pg.wait_for_timeout(2500)
    check("late: a device with no output yet is still asked (SYNC sent)", pg.evaluate("window.__syncs || 0") > before, pg.evaluate("[window.__syncs, window.__log.slice(-6)]"))
    check("late: GSP32 found afterwards", wait_js(pg, "() => /GSP32 Version/.test(document.getElementById('board-state').innerText)", 20000), pg.inner_text("#board-state"))
    check("late: no page errors", not errors, errors)
    pg.close()

    # 3. The REPL has the port, then the web UI says Listening (114.1 in safe mode): Set Up Wi-Fi restarts first
    pg, errors = page(b)
    pg.click("#connect"); pg.wait_for_timeout(100); boot(pg, 1500)
    pg.evaluate("window.__listen = false; window.__say('MicroPython v1.25.0 on 2025-04-15; ESP32C3 module with ESP32C3\\r\\nType \"help()\" for more information.\\r\\n>>> ')")
    pg.wait_for_timeout(300)
    pg.evaluate("window.__say('GSP32 Improv Listening\\r\\n')")
    pg.wait_for_timeout(300)
    check("repl: the Listening line after the prompt is not believed", pg.evaluate("window.__badPk") == 0)
    pg.wait_for_selector("#wifi-setup:not([hidden])", timeout=8000)
    r0 = resets(pg)
    pg.click("#wifi-setup")
    check("repl: the first Set Up Wi-Fi lists networks", networks(pg, 30000), pg.inner_text("#wifi-status"))
    check("repl: the device was restarted first", resets(pg) > r0, resets(pg) - r0)
    check("repl: no packet went to the REPL", pg.evaluate("window.__badPk") == 0, pg.evaluate("window.__badBytes"))
    check("repl: no page errors", not errors, errors)
    pg.close()

    # 4. Says Listening, never answers: one restart and the networks, not "did not answer" / Try Again
    pg, errors = page(b)
    pg.click("#connect"); pg.wait_for_timeout(100); boot(pg, 1500)
    pg.evaluate("window.__listen = false")
    pg.wait_for_selector("#wifi-setup:not([hidden])", timeout=8000)
    r0 = resets(pg)
    pg.click("#wifi-setup")
    check("silent: networks after one restart", networks(pg, 45000), pg.inner_text("#wifi-status"))
    check("silent: restarted once", resets(pg) - r0 == 1, resets(pg) - r0)
    check("silent: no Try Again", pg.evaluate("document.getElementById('wifi-rescan').textContent") != "Try Again" or pg.evaluate("document.getElementById('wifi-rescan').hidden"))
    check("silent: no page errors", not errors, errors)
    pg.close()

    # 5. appBooted
    pg, errors = page(b)
    res = pg.evaluate("""async () => { const m = await import('./app.js?probe=' + Date.now()).catch((e) => null); if (!m || !m.appBooted) return null;
        return [m.appBooted('rst:0x15 (USB_UART_CHIP_RESET),boot:0xc (SPI_FAST_FLASH_BOOT)\\r\\n'), m.appBooted('entry 0x403cc710\\r\\n'),
                m.appBooted('GSP32 Improv Listening\\r\\n'), m.appBooted('rst:0x15 (USB_UART_CHIP_RESET),boot:0x0 (DOWNLOAD(USB/UART0))\\r\\nwaiting for download\\r\\n'),
                m.appBooted('')]; }""")
    check("appBooted: flash boot, loader, GSP32 yes; download mode and nothing no", res == [True, True, True, False, False], res)
    pg.close()
    b.close()
print("FAILURES:", fails)
sys.exit(1 if fails else 0)
