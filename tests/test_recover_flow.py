# Fix (recover flow, Gene's Linux laptop): an install that never connected left a note that, after a reload, showed
#  "Incomplete Install Detected" with a greyed Recover button before any board was connected. Now the note is saved
#  only once erasing/writing starts; Incomplete Install shows only for a connected board whose MAC matches the note
#  (or a boot loop); other firmware (an Arduino sketch) gets plain Install GSP32; the real case reads Recover/Install
#  GSP32; Get Started always opens the picker and survives a port that won't open; greyed main buttons say why
import os, http.server, threading, functools, json
from playwright.sync_api import sync_playwright
here = os.path.dirname(os.path.abspath(__file__)); site = os.path.dirname(here)
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8797), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)
MAC = "f8:b3:b7:22:05:e8"
def note_js(n): return "if (!sessionStorage.getItem('seeded')) { sessionStorage.setItem('seeded', 1); localStorage.setItem('gsp32.flash', JSON.stringify(%s)); }" % json.dumps(n)
def page(b, init="", fake=True):
    pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.add_init_script(path=here + "/mock.js")
    pg.add_init_script("window.__ver = '47';" + init)
    if fake: pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.route("**/gsp32-telemetry.genereese.workers.dev/**", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true}'))
    errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:8797/index.html"); pg.wait_for_timeout(300)
    return pg, errors
def label(pg): return pg.inner_text("#install-btn")
def vis(pg, sel): return pg.is_visible(sel)
def note(pg): return pg.evaluate("JSON.parse(localStorage.getItem('gsp32.flash'))")
def page_text(pg): return pg.evaluate("document.body.innerText")
def start_ok(pg): return pg.evaluate("(() => { const b = document.getElementById('connect'); return !b.hidden && !b.disabled && b.offsetParent !== null; })()")
with sync_playwright() as p:
    b = p.chromium.launch()
    # 1. An install whose connect fails writes nothing and leaves no note
    pg, errors = page(b, "window.__other = true;")
    pg.click("#connect"); pg.wait_for_timeout(1500)
    pg.evaluate("window.__failFlash = true")
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install")
    pg.wait_for_function("document.body.innerText.includes('did not answer')", timeout=30000)
    check("connect failed: no note saved", note(pg) is None, str(note(pg)))
    check("connect failed: no files written", not [l for l in pg.evaluate("window.__log") if l.startswith("files")])
    check("no page errors (1)", not errors, str(errors)); pg.close()
    # 2. The note is saved once erasing starts, with the MAC and writing: true; a finished install clears it
    pg, errors = page(b, "window.__eraseDelay = 1500;")
    pg.click("#connect"); pg.wait_for_timeout(1500)
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install")
    pg.wait_for_function("document.body.innerText.includes('Erasing')", timeout=15000); pg.wait_for_timeout(200)
    n = note(pg)
    check("note saved when erasing starts", bool(n) and n.get("writing") is True and n.get("mac") == MAC, str(n))
    pg.wait_for_function("document.getElementById('wizard').hidden", timeout=20000); pg.wait_for_timeout(300)
    check("finished install clears the note", note(pg) is None); pg.close()
    # 3. Gene's case: an old note (saved at Installing, never connected) on a reload. Nothing about Incomplete before a
    #  board is connected; Get Started opens the picker; an Arduino sketch board gets plain Install GSP32, enabled
    pg, errors = page(b, "window.__other = true; window.__picks = 0; const rp = navigator.serial.requestPort; navigator.serial.requestPort = async (o) => { window.__picks++; return rp(o); };" + note_js({"mac": "", "version": "92", "startedAt": 1}))
    check("stale note: nothing about Incomplete before connecting", "Incomplete" not in page_text(pg) and "Recover" not in page_text(pg))
    pg.click("#connect"); pg.wait_for_timeout(200)
    check("Get Started opens the picker", pg.evaluate("window.__picks") == 1)
    pg.wait_for_timeout(2000)
    check("stale note, Arduino sketch: plain Install GSP32", label(pg) == "Install GSP32", label(pg))
    check("Install enabled once the device is read", pg.is_enabled("#install-btn"))
    check("stale note: no Incomplete Install text", "Incomplete" not in page_text(pg), pg.inner_text("#board-state"))
    check("stale note dropped", note(pg) is None)
    check("no page errors (3)", not errors, str(errors)); pg.close()
    # 4. A real cut-off install (note with writing for this MAC) on a boot-looping board: Recover/Install GSP32, enabled
    pg, errors = page(b, "window.__bootLoop = true;" + note_js({"mac": MAC, "version": "92", "startedAt": 1, "writing": True}))
    check("real note: nothing shown before connecting", "Incomplete" not in page_text(pg))
    pg.click("#connect"); pg.wait_for_timeout(2500)
    check("real note, MAC matches: Recover/Install GSP32", label(pg) == "Recover/Install GSP32", label(pg))
    check("Recover/Install enabled and primary", pg.is_enabled("#install-btn") and "primary" in pg.get_attribute("#install-btn", "class"))
    st = pg.inner_text("#board-status") if vis(pg, "#board-status") else ""
    check("status names the button", "Click Recover/Install GSP32" in st, st)
    pg.click("#install-btn"); pg.wait_for_timeout(400)
    check("Recover/Install opens Erase and Install", vis(pg, "#start-install"))
    check("no page errors (4)", not errors, str(errors)); pg.close()
    # 5. A note for another board's MAC: plain Install GSP32 on this one (Arduino sketch)
    pg, errors = page(b, "window.__other = true;" + note_js({"mac": "aa:bb:cc:dd:ee:ff", "version": "92", "startedAt": 1, "writing": True}))
    pg.click("#connect"); pg.wait_for_timeout(2500)
    check("note for another MAC: plain Install GSP32", label(pg) == "Install GSP32" and "Incomplete" not in page_text(pg), label(pg))
    pg.close()
    # 6. Boot loop with no note at all: still Recover/Install GSP32
    pg, errors = page(b, "window.__bootLoop = true;")
    pg.click("#connect"); pg.wait_for_timeout(800); pg.click("#reset"); pg.wait_for_timeout(3800)
    check("boot loop: Recover/Install GSP32", label(pg) == "Recover/Install GSP32", label(pg)); pg.close()
    # 7. Arduino sketch with a matching note: Install GSP32 once the sketch is seen running (no GSP32 within 20 s)
    pg, errors = page(b, "window.__other = true;" + note_js({"mac": MAC, "version": "92", "startedAt": 1, "writing": True}))
    pg.click("#connect"); pg.wait_for_timeout(23000)
    check("matching note but other firmware runs: Install GSP32", label(pg) == "Install GSP32" and "Incomplete" not in page_text(pg), label(pg) + " / " + pg.inner_text("#board-state"))
    check("note dropped once other firmware runs", note(pg) is None); pg.close()
    # 8. The port won't open (stale Chromium state, another program): one clear line, Get Started stays usable,
    #  and clicking it again opens the picker again
    pg, errors = page(b, "window.__picks = 0; navigator.serial.requestPort = async () => { window.__picks++; return { open: async () => { throw new DOMException('Failed to open serial port.', 'NetworkError'); }, close: async () => {}, getInfo: () => ({}), readable: null, writable: null, setSignals: async () => {} }; };")
    pg.click("#connect"); pg.wait_for_timeout(900)
    err = pg.inner_text("#start-error") if vis(pg, "#start-error") else ""
    check("open fails: one clear line by Get Started", err.startswith("Could not open the port.") and "\n" not in err, err)
    check("open fails: Get Started usable", start_ok(pg))
    pg.click("#connect"); pg.wait_for_timeout(900)
    check("Get Started again opens the picker again", pg.evaluate("window.__picks") == 2)
    check("no page errors (8)", not errors, str(errors)); pg.close()
    # 9. A port Chromium still holds (first open fails): closed and opened again, it connects
    pg, errors = page(b, "window.__openFailsOnce = true;")
    pg.evaluate("() => { const p = window.__port, o = p.open.bind(p); p.open = async (x) => { if (window.__openFailsOnce) { window.__openFailsOnce = false; throw new DOMException('The port is already open.', 'InvalidStateError'); } return o(x); }; }")
    pg.click("#connect"); pg.wait_for_timeout(2500)
    check("stale port: opens on the second try and connects", not pg.is_disabled("#disconnect") and "keeps running" in pg.inner_text("#console-out"), pg.inner_text("#console-out")[-150:])
    check("stale port: no error line", not vis(pg, "#start-error")); pg.close()
    # 10. The port does not come back after the probe: the message, the port closed, Get Started back
    #  Flasher Version 115.10: a classic board is probed on connect only with an unfinished install on record (seeded)
    pg, errors = page(b, "window.__failFlash = true;" + note_js({"mac": "00:00:00:00:00:01", "version": "92", "startedAt": 1, "writing": True}))
    pg.evaluate("() => { const p = window.__port, o = p.open.bind(p); let n = 0; p.open = async (x) => { if (++n > 1) throw new DOMException('Failed to open serial port.', 'NetworkError'); return o(x); }; }")
    pg.click("#connect"); pg.wait_for_timeout(4000)
    check("port lost after the probe: message", "The port closed while reading the device" in pg.inner_text("#console-out"), pg.inner_text("#console-out")[-200:])
    check("port lost after the probe: Get Started usable", start_ok(pg))
    check("not connected: the greyed Install says why", vis(pg, "#actions-note") and "Click Get Started" in pg.inner_text("#actions-note"), pg.inner_text("#actions-note") if vis(pg, "#actions-note") else "")
    check("no page errors (10)", not errors, str(errors)); pg.close()
    # 11. While the probe reads the board (real esptool-js: the mock never syncs), greyed Install says why
    pg, errors = page(b, note_js({"mac": "00:00:00:00:00:01", "version": "92", "startedAt": 1, "writing": True}), fake=False)
    pg.click("#connect"); pg.wait_for_timeout(1500)
    check("probe running: Install greyed with a reason", pg.is_disabled("#install-btn") and vis(pg, "#actions-note") and "Reading the device" in pg.inner_text("#actions-note"), pg.inner_text("#actions-note") if vis(pg, "#actions-note") else "")
    pg.wait_for_function("document.getElementById('console-out').innerText.includes('Could not read the device yet')", timeout=40000); pg.wait_for_timeout(1500)
    check("probe over: Install enabled, no note", pg.is_enabled("#install-btn") and not vis(pg, "#actions-note"))
    pg.close()
    # 12. Erase and Install greyed until the box is ticked, and it says so
    pg, errors = page(b)
    pg.click("#connect"); pg.wait_for_timeout(1500); pg.click("#install-btn"); pg.wait_for_timeout(300)
    check("Erase and Install greyed: 'Tick the box above'", pg.is_disabled("#start-install") and vis(pg, "#start-note") and "Tick the box" in pg.inner_text("#start-note"))
    pg.check("#erase-ok")
    check("ticked: enabled, reason gone", pg.is_enabled("#start-install") and not vis(pg, "#start-note"))
    check("no page errors (12)", not errors, str(errors)); pg.close()
    b.close()
print("FAILURES:", fails)
raise SystemExit(1 if fails else 0)
