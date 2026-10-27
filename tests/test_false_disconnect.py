# Fix (false disconnect): line noise on the serial port (FramingError, BreakError, ...) is not an unplug. Reading goes
#  on with a fresh reader and no "disconnected" message; esptool-js's own reads (connect, flash) survive one such error;
#  a real unplug says so, closes the port and brings Get Started back
import os, http.server, threading, functools
from playwright.sync_api import sync_playwright
here = os.path.dirname(os.path.abspath(__file__)); site = os.path.dirname(here)
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8793), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)
DISC = "The device disconnected"
def page(b, init=""):
    pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.add_init_script(path=here + "/mock.js")
    pg.add_init_script("window.__ver = '47'; window.__ets = true;" + init)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.route("**/gsp32-telemetry.genereese.workers.dev/**", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true}'))
    errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:8793/index.html"); pg.wait_for_timeout(300)
    return pg, errors
def out(pg): return pg.inner_text("#console-out")
def start_visible(pg):
    return pg.evaluate("(() => { const b = document.getElementById('connect'); const i = document.getElementById('installer'); return !b.hidden && !b.disabled && !i.hidden && b.offsetParent !== null; })()")
with sync_playwright() as p:
    b = p.chromium.launch()
    # 1. Noise while the console reads (an Arduino sketch, a reset): reading goes on
    pg, errors = page(b)
    pg.click("#connect"); pg.wait_for_timeout(4500)
    check("connected (115.10: no probe, the device left running)", pg.evaluate("!document.getElementById('disconnect').disabled") and "keeps running" in out(pg), out(pg)[-200:])
    for name in ("FramingError", "BreakError", "ParityError", "BufferOverrunError"):
        pg.evaluate("n => window.__serialError(n)", name); pg.wait_for_timeout(150)
        pg.evaluate("n => window.__say('after ' + n + '\\r\\n')", name); pg.wait_for_timeout(250)
        check(name + ": reading goes on", ("after " + name) in out(pg), out(pg)[-120:])
    check("noise: no disconnect message", DISC not in out(pg))
    check("noise: port still open (Disconnect enabled, never closed)", pg.evaluate("!document.getElementById('disconnect').disabled") and not [l for l in pg.evaluate("window.__log") if l.startswith("close")] , str([l for l in pg.evaluate("window.__log") if l.startswith("close")]))
    # Many errors in a row (a sketch at another baud rate) still don't count as an unplug
    for _ in range(12): pg.evaluate("window.__serialError('FramingError')"); pg.wait_for_timeout(20)
    pg.wait_for_timeout(600); pg.evaluate("window.__say('still here\\r\\n')"); pg.wait_for_timeout(700)
    check("12 errors in a row: still reading, no disconnect", "still here" in out(pg) and DISC not in out(pg), out(pg)[-120:])
    # 2. A real unplug: the message once, the port closed, Get Started back and usable
    pg.evaluate("window.__unplug()"); pg.wait_for_timeout(900)
    log = pg.evaluate("window.__log")
    check("unplug: disconnect message once", out(pg).count(DISC) == 1, out(pg)[-200:])
    check("unplug: port closed (Chromium lets go)", any(l.startswith("close") for l in log[log.index("UNPLUG"):]), str(log[-6:]))
    check("unplug: Get Started visible and enabled", start_visible(pg))
    check("unplug: console log kept", "still here" in out(pg))
    # Get Started again reconnects the same port (it was closed, so open() works)
    pg.click("#connect"); pg.wait_for_timeout(4500)
    check("Get Started after unplug: connected again", pg.evaluate("!document.getElementById('disconnect').disabled") and "keeps running" in out(pg).split(DISC)[-1], out(pg)[-200:])
    check("no page errors", not errors, str(errors)); pg.close()
    # 3. esptool-js reads during connect and flash survive one FramingError each; the install finishes
    pg, errors = page(b, "window.__esptoolNoise = true; window.__flashNoise = true;")
    pg.click("#connect"); pg.wait_for_timeout(4500)
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(8000)
    log = pg.evaluate("window.__log")
    check("connect read survives a FramingError", "connect read ok 2" in log, str([l for l in log if "read" in l]))
    check("flash read survives a FramingError", "flash read ok 2" in log, str([l for l in log if "read" in l]))
    check("install finished (image written)", any(l.startswith("files 1") for l in log) and "Installed" in pg.inner_text("body"))
    check("install with noise: no disconnect message", DISC not in out(pg))
    check("no page errors (install)", not errors, str(errors)); pg.close()
    # 4. Any failure (the port can't be opened) leaves Get Started usable
    pg, errors = page(b)
    pg.evaluate("() => { window.__port.open = async () => { throw new DOMException('Failed to open serial port.', 'NetworkError'); }; }")
    pg.click("#connect"); pg.wait_for_timeout(800)
    check("open failure: message shown", "Could not open the port" in out(pg) or "Could not open the port" in pg.inner_text("body"))
    check("open failure: Get Started visible and enabled", start_visible(pg))
    pg.close()
    b.close()
print("FAILURES:", fails)
raise SystemExit(1 if fails else 0)
