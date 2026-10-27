# Flasher Version 115.17 (Gene's classic ESP32, CP2102, 27 Oct 2026): a device whose auto-reset never reaches download
#  mode installs with BOOT held. The flasher still tries the automatic reset first; when that fails the error says
#  "Hold the BOOT button, click Try Again ..., and let go when progress starts", and the device is remembered in this
#  browser (localStorage gsp32HoldBoot, keyed by USB VID:PID plus the MACs read once an install got through), so the
#  next Install shows the hold-BOOT tip before it starts. "It installs without BOOT now: forget this" clears it. A
#  device that connects normally never sees it, nor does a native USB chip, nor a remembered bridge whose known MAC is
#  not on the list. SHOTS=<dir> saves the hint and the tip as PNGs
import sys, http.server, threading, functools, os, json
from playwright.sync_api import sync_playwright
here = os.path.dirname(os.path.abspath(__file__))
site = os.environ.get("SITE") or os.path.dirname(here)
shots = os.environ.get("SHOTS")
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8896), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
U = "http://127.0.0.1:8896/index.html"
fails = 0
def check(name, ok, extra=""):
    extra = str(extra).replace("Traceback (most recent call last)", "Traceback (device output)")
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra); sys.stdout.flush()
BOOT = [
    [150, "ets Jul 29 2019 12:21:46\r\n\r\nrst:0x1 (POWERON_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)\r\n"],
    [2500, "\r\n\r\nGSP32-C Beta V125 on ESP32 (GSP32-C ESP32), boot 1, reset: power-on\r\n\r\ngsp.help() lists the GSP32-C commands.\r\n\r\n", True],
    [3200, "main.py running\r\n"],
]
def page(b, init="", usb="{usbVendorId: 0x10c4, usbProductId: 0xea60}", stored=None):
    pg = b.new_page(viewport={"width": 1280, "height": 1000}); pg.add_init_script(path=here + "/mock.js")
    pg.add_init_script("window.__usb = %s; window.__boot = %s; window.__gspc = '120';" % (usb, json.dumps(BOOT)))
    if stored is not None:
        pg.add_init_script("if (!sessionStorage.getItem('seeded')) { localStorage.setItem('gsp32HoldBoot', %s); sessionStorage.setItem('seeded', '1'); }" % json.dumps(json.dumps(stored)))
    if init: pg.add_init_script(init)
    errors = []; pg.on("pageerror", lambda e: errors.append(str(e))); pg.__errors = errors
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.route("**/gsp32-telemetry.genereese.workers.dev/**", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true}'))
    pg.goto(U); pg.wait_for_timeout(300); return pg
def connect(pg):
    pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(3000)
def open_install(pg):
    pg.click("#install-btn"); pg.wait_for_timeout(400)
    pg.select_option("#release-channel", "gspc-125"); pg.wait_for_timeout(300)
def start(pg):
    pg.evaluate("window.__bootScript = window.__boot"); pg.check("#erase-ok"); pg.click("#start-install")
def installed(pg, ms=60000):
    pg.wait_for_function("/main\\.py running/.test(document.getElementById('console-out').innerText)", timeout=ms); pg.wait_for_timeout(800)
    return "Installed" in pg.inner_text("body")
def stored(pg):
    return pg.evaluate("JSON.parse(localStorage.getItem('gsp32HoldBoot') || 'null')")
def tip(pg):
    return pg.is_visible("#boot-remembered")
def shot(pg, sel, name):
    if not shots: return
    os.makedirs(shots, exist_ok=True)
    pg.locator(sel).scroll_into_view_if_needed(); pg.wait_for_timeout(400)
    pg.locator("#wizard").screenshot(path=os.path.join(shots, name))
    print("shot", os.path.join(shots, name))

with sync_playwright() as p:
    b = p.chromium.launch()
    # 1. A normal device: no tip before the install, no hint, nothing remembered
    pg = page(b)
    connect(pg); open_install(pg)
    check("normal device: no hold-BOOT tip in the Install step", not tip(pg))
    start(pg)
    check("normal device: installed", installed(pg))
    check("normal device: no hold-BOOT notes", not pg.is_visible("#boot-hint") and not pg.is_visible("#boot-now"))
    check("normal device: nothing remembered", stored(pg) is None, stored(pg))
    open_install(pg)
    check("normal device: still no tip on the next Install", not tip(pg))
    check("flow 1: no page errors", not pg.__errors, pg.__errors)
    pg.close()

    # 2. Gene's device: no reset reaches download mode. Auto first, then the hold-BOOT step; remembered; tip next time
    pg = page(b, "window.__resetWorks = 'none';")
    connect(pg); open_install(pg)
    check("before any failure: no tip", not tip(pg))
    start(pg)
    pg.wait_for_function("!document.getElementById('boot-now').hidden", timeout=90000)
    check("auto reset tried first (Resets tried before the hold-BOOT step)", "[Resets tried:" in pg.inner_text("#console-out"))
    pg.wait_for_function("!document.getElementById('boot-hint').hidden", timeout=90000); pg.wait_for_timeout(700)
    hint = pg.inner_text("#boot-hint")
    check("failure: hint says hold BOOT, click Try Again, let go when progress starts",
          "Hold the BOOT button" in hint and "Try Again" in hint and "let go when progress starts" in hint, hint)
    check("failure: hint says it will remind next time", "reminds you next time" in hint, hint)
    s = stored(pg)
    check("failure: device remembered by its USB bridge", bool(s) and "10c4:ea60" in s and s["10c4:ea60"]["macs"] == [], s)
    check("failure: console says it will remind", "remind you next time" in pg.inner_text("#console-out"))
    shot(pg, "#boot-hint", "flasher-11517-hold-boot-hint.png")
    # Try Again: the tip is there before the install starts (shown at once, not folding)
    pg.click("#error-retry"); pg.wait_for_timeout(50)
    check("remembered: tip shown up front in the Install step", tip(pg) and "Hold BOOT for this device" in pg.inner_text("#boot-remembered"), pg.inner_text("#boot-remembered") if tip(pg) else "")
    check("remembered: tip says let go when progress starts", "let go when progress starts" in pg.inner_text("#boot-remembered"))
    pg.wait_for_timeout(400)
    shot(pg, "#boot-remembered", "flasher-11517-hold-boot-tip.png")
    # With BOOT held (the reset now works) the install goes through, and the MAC read joins the entry
    pg.evaluate("window.__resetWorks = undefined")
    start(pg)
    check("remembered + BOOT held: installed", installed(pg))
    check("remembered + BOOT held: no hold-BOOT step this time", not pg.is_visible("#boot-hint") and not pg.is_visible("#boot-now"))
    s = stored(pg)
    check("remembered: the MAC read joins the entry", bool(s) and s["10c4:ea60"]["macs"] == ["f8:b3:b7:22:05:e8"], s)
    # Remembered across a reload (a new visit), the tip is there before the install
    pg.reload(); pg.wait_for_timeout(300); connect(pg); open_install(pg)
    check("new visit: tip shown before the install", tip(pg))
    # Clear it
    pg.click("#boot-forget"); pg.wait_for_timeout(700)
    check("forget: tip folds away", not tip(pg))
    check("forget: nothing remembered", stored(pg) is None, stored(pg))
    check("forget: console says so", "reminder for this device was cleared" in pg.inner_text("#console-out"))
    pg.click("[data-step=prep] [data-action=close]"); pg.wait_for_timeout(400); open_install(pg)
    check("forget: no tip on the next Install", not tip(pg))
    check("flow 2: no page errors", not pg.__errors, pg.__errors)
    pg.close()

    # 3. The first try fails, BOOT is pressed during the pause and the second try gets through: remembered with its MAC
    pg = page(b, "window.__resetWorks = 'none';")
    connect(pg); open_install(pg); start(pg)
    pg.wait_for_function("!document.getElementById('boot-now').hidden", timeout=90000)
    pg.evaluate("window.__resetWorks = undefined")
    check("second try with BOOT: installed", installed(pg))
    s = stored(pg)
    check("second try with BOOT: remembered with the MAC", bool(s) and s["10c4:ea60"]["macs"] == ["f8:b3:b7:22:05:e8"], s)
    check("flow 3: no page errors", not pg.__errors, pg.__errors)
    pg.close()

    # 4. Same kind of USB bridge, but a remembered list with another MAC: the tip shows while the MAC is unknown, and
    #  not once this device's MAC is known (another board)
    pg = page(b, stored={"10c4:ea60": {"macs": ["aa:bb:cc:dd:ee:ff"], "at": 1}})
    connect(pg); open_install(pg)
    check("other MAC, unknown yet: tip shown (bridge matches)", tip(pg))
    start(pg)
    check("other MAC: installed", installed(pg))
    open_install(pg)
    check("other MAC, now known: no tip", not tip(pg))
    check("other MAC: the stored list is unchanged", stored(pg)["10c4:ea60"]["macs"] == ["aa:bb:cc:dd:ee:ff"], stored(pg))
    check("flow 4: no page errors", not pg.__errors, pg.__errors)
    pg.close()

    # 5. Another bridge (CH340) with a CP210x entry stored: no tip
    pg = page(b, usb="{usbVendorId: 0x1a86, usbProductId: 0x7523}", stored={"10c4:ea60": {"macs": [], "at": 1}})
    connect(pg); open_install(pg)
    check("other USB bridge: no tip", not tip(pg))
    pg.close()

    # 6. Native USB (0x303A) never gets the classic tip (it has its own BOOT and RST guide)
    pg = page(b, "window.__ver = '116';", usb="{usbVendorId: 0x303a, usbProductId: 0x1001}", stored={"303a:1001": {"macs": [], "at": 1}})
    pg.click("#connect"); pg.wait_for_timeout(3000)
    if pg.is_visible("#install-btn") and pg.is_enabled("#install-btn"):
        pg.click("#install-btn"); pg.wait_for_timeout(400)
    check("native USB: no classic tip", not tip(pg))
    pg.close()
    b.close()
print("FAILURES:", fails)
raise SystemExit(1 if fails else 0)
