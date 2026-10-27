# Fix (Linux reset): each connect attempt takes the next reset sequence. On Linux tight first (one setSignals per
#  step, like esptool's UnixTightReset), elsewhere classic first (esptool-js's own, as before), USB-JTAG first for a
#  native USB chip; then classic, tight, USB-JTAG in turn, 50 ms the first round and 550 ms after. What worked is
#  remembered per USB bridge and tried first next time
import os, http.server, threading, functools
from playwright.sync_api import sync_playwright
# Flasher Version 115.10: a classic board is not probed on a plain connect any more (Gene: it restarted the board); these
#  tests of the probe itself (still run for native USB and for Recover) turn it on
PROBE_ON = "window.__gsp32ProbeOnConnect = true;"
here = os.path.dirname(os.path.abspath(__file__)); site = os.path.dirname(here)
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8794), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)
def plat(name):
    return ("Object.defineProperty(navigator, 'platform', { get: () => '%s' });"
            "Object.defineProperty(navigator, 'userAgentData', { get: () => ({ platform: '%s' }) });") % (name, name.split(' ')[0])
def page(b, init=""):
    pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script(PROBE_ON)
    pg.add_init_script("window.__ver = '47'; window.__ets = true;" + init)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.route("**/gsp32-telemetry.genereese.workers.dev/**", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true}'))
    errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:8794/index.html"); pg.wait_for_timeout(300)
    return pg, errors
def out(pg): return pg.inner_text("#console-out")
def resets(pg): return [l[6:] for l in pg.evaluate("window.__log") if l.startswith("reset ")]
def connect(pg, wait_for="Device:", ms=15000):
    pg.click("#connect")
    try: pg.wait_for_function("t => document.getElementById('console-out').innerText.includes(t)", arg=wait_for, timeout=ms)
    except Exception: pass
    pg.wait_for_timeout(300)
def start_visible(pg):
    return pg.evaluate("(() => { const b = document.getElementById('connect'); return !b.hidden && !b.disabled && b.offsetParent !== null; })()")
with sync_playwright() as p:
    b = p.chromium.launch()
    # 1. Linux, CP2102, the board takes classic: tight first, then classic
    pg, errors = page(b, plat("Linux x86_64") + "window.__resetWorks = 'classic';")
    connect(pg)
    check("Linux: tight first, then classic", resets(pg) == ["tight", "classic"], str(resets(pg)))
    check("Linux: connected", "Device:" in out(pg), out(pg)[-160:])
    log = pg.evaluate("window.__log")
    sig = [l for l in log if l.startswith("signals")]
    # tight: reset (DTR off, RTS on) straight to download (DTR on, RTS off) in one setSignals, no state in between
    i = next((k for k in range(len(sig) - 1) if sig[k] == "signals dtr=false rts=true" and sig[k + 1] == "signals dtr=true rts=false"), -1)
    check("tight: reset -> download in one setSignals", i >= 0, str(sig[:12]))
    tight = ["signals dtr=false rts=false", "signals dtr=true rts=true", "signals dtr=false rts=true", "signals dtr=true rts=false", "signals dtr=false rts=false"]
    check("tight: UnixTightReset's 5 states, one setSignals each", any(sig[k:k + 5] == tight for k in range(len(sig))), str(sig[:8]))
    stored = pg.evaluate("localStorage.getItem('gsp32ResetSeq')")
    check("what worked is remembered per USB bridge", stored == '{"10c4:ea60":"classic"}', str(stored))
    check("no page errors", not errors, str(errors))
    # 2. Same browser next time: classic (remembered) first, then tight, USB-JTAG
    pg.evaluate("window.__resetWorks = 'usbJtag'")
    pg.evaluate("localStorage.setItem('gsp32ResetSeq', JSON.stringify({'10c4:ea60': 'classic'}))")
    pg.reload(); pg.wait_for_timeout(300); pg.evaluate("window.__resetWorks = 'usbJtag'")
    connect(pg)
    check("remembered classic first, then tight, USB-JTAG", resets(pg) == ["classic", "tight", "usbJtag"], str(resets(pg)))
    check("remembered now USB-JTAG", pg.evaluate("localStorage.getItem('gsp32ResetSeq')") == '{"10c4:ea60":"usbJtag"}')
    pg.close()
    # 3. Windows (keeps what worked there): classic first, then tight, USB-JTAG
    pg, errors = page(b, plat("Win32") + "window.__resetWorks = 'tight';")
    connect(pg)
    check("Windows: classic first, then tight", resets(pg) == ["classic", "tight"], str(resets(pg)))
    sig = [l for l in pg.evaluate("window.__log") if l.startswith("signals")]
    classic = ["signals dtr=false rts=false", "signals dtr=false rts=true", "signals dtr=false rts=true", "signals dtr=true rts=true", "signals dtr=true rts=false", "signals dtr=true rts=false", "signals dtr=false rts=false"]
    check("classic: esptool-js's own calls (setRTS re-sends DTR)", any(sig[k:k + 7] == classic for k in range(2)), str(sig[:9]))  # 115.10: no setRunState call on a plain open
    check("no page errors (Windows)", not errors, str(errors)); pg.close()
    # 4. Native USB (USB-JTAG PID 0x1001) on Linux: USB-JTAG first
    pg, errors = page(b, plat("Linux x86_64") + "window.__usb = { usbVendorId: 0x303a, usbProductId: 0x1001 }; window.__chip = 'ESP32-S3 (QFN56) (revision v0.2)'; window.__resetWorks = 'usbJtag';")
    connect(pg)
    check("USB-JTAG chip: USB-JTAG first", resets(pg) == ["usbJtag"], str(resets(pg)))
    pg.close()
    # 5. Nothing works: every attempt rotates tight, classic, USB-JTAG; 50 ms the first round, 550 ms after
    pg, errors = page(b, plat("Linux x86_64") + "window.__resetWorks = 'none';")
    connect(pg, "Resets tried", 30000); pg.wait_for_timeout(8000)
    r = resets(pg)
    check("7 attempts in rotation", r[:7] == ["tight", "classic", "usbJtag", "tight", "classic", "usbJtag", "tight"], str(r))
    check("console names them with esptool's delays", "[Resets tried: tight 50, classic 50, usbJtag 50, tight 550, classic 550, usbJtag 550, tight 550]" in out(pg), out(pg)[-400:])
    check("failure: still connected, Install can try again", pg.evaluate("!document.getElementById('disconnect').disabled && !document.getElementById('install-btn').disabled"))
    check("no page errors (failure)", not errors, str(errors)); pg.close()
    # 6. The real esptool-js 0.5.7 (the mock board never answers its sync): it runs our rotation, one per attempt
    pg = b.new_page(); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script(PROBE_ON); pg.add_init_script("window.__ver = '47';" + plat("Linux x86_64"))
    pg.route("**/gsp32-telemetry.genereese.workers.dev/**", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true}'))
    errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:8794/index.html"); pg.wait_for_timeout(300)
    connect(pg, "Resets tried", 40000)
    check("real esptool-js: rotation tight, classic, USB-JTAG", "[Resets tried: tight 50, classic 50, usbJtag 50" in out(pg), [l for l in out(pg).splitlines() if "Resets" in l])
    check("no page errors (real esptool-js)", not errors, str(errors)); pg.close()
    b.close()
print("FAILURES:", fails)
raise SystemExit(1 if fails else 0)
