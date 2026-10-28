import re, sys, http.server, threading, functools, os
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import json as _j, re as _r, os as _o
LISTED = _r.match(r"Version \d+(?:\.\d+)?", _j.load(open(_o.path.join(site, "manifest.json")))["version"]).group(0)  # the listed build, e.g. "Version 32"
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=site)
handler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8766), handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
here = os.path.dirname(os.path.abspath(__file__)); ok = 0; bad = 0
shots = os.environ.get("SHOTS") or __import__("tempfile").mkdtemp(prefix="gsp32-install-shots-")
def check(name, cond, extra=""):
    global ok, bad
    print(("PASS " if cond else "FAIL ") + name, extra); ok += bool(cond); bad += (not cond); sys.stdout.flush()
U = "http://127.0.0.1:8766/index.html"
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.add_init_script(path=here + "/mock.js"); pg.add_init_script(path=here + "/classic.js")
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(U); pg.wait_for_timeout(300)
    pg.screenshot(path=shots + "/01-page.png")
    sr = pg.locator(".steps-row").bounding_box(); cb = pg.locator("#connect").bounding_box()
    check("steps and Get Started centered", abs((sr["x"] + sr["width"] / 2) - 640) < 30 and abs((cb["x"] + cb["width"] / 2) - (sr["x"] + sr["width"] / 2)) < 4 and cb["y"] - (sr["y"] + sr["height"]) >= 20, str((sr, cb)))
    check("no dialog, one Get Started button, steps row", pg.locator("dialog[open]").count() == 0 and pg.inner_text("#connect") == "Get Started"
          and "1. Plug In Your Device" in pg.inner_text(".steps-row"))  # V50: the compact hero drops the browser line (the browser card still warns)
    check("device card hidden at first", not pg.is_visible("#console"))
    hb = pg.locator("#installer .hint").bounding_box()
    check("V50: Get Started just below the steps", cb["y"] - (sr["y"] + sr["height"]) >= 16, str(cb["y"] - sr["y"] - sr["height"]))
    check("Don't See Your Device? link under Get Started, checklist folded", pg.is_visible("#no-board") and not pg.is_visible("#board-help")
          and pg.locator("#no-board").bounding_box()["y"] > pg.locator("#connect").bounding_box()["y"])
    pg.click("#no-board"); pg.wait_for_timeout(400)
    t = pg.inner_text("#board-help")
    check("checklist: cable, port/hub, CP210x + CH340 drivers, BOOT, try again", pg.is_visible("#board-help") and all(w in t for w in ["Data Cable", "hub", "CP210x", "CH340", "BOOT", "Try Again"])
          and pg.locator("#board-help a[href*='silabs.com']").count() == 1 and pg.locator("#board-help a[href*='wch']").count() == 1)
    pg.click("#no-board"); pg.wait_for_timeout(400)
    pg.evaluate("(() => { window.__realReq = navigator.serial.requestPort; navigator.serial.requestPort = () => Promise.reject(new DOMException('No port selected', 'NotFoundError')); })()")
    pg.click("#connect"); pg.wait_for_timeout(400)
    check("cancelled picker opens the checklist", pg.is_visible("#board-help") and pg.is_visible("#connect"))
    pg.evaluate("(() => { navigator.serial.requestPort = window.__realReq; })()")
    pg.click("#connect")
    # Flasher Version 115.10 (Gene's ESP32): a classic board is connected without the probe (Install reads it)
    pg.wait_for_function("() => /keeps running/.test(document.getElementById('console-out').innerText)", timeout=15000)
    # the probe's seconds used to cover the fold: now the connect is quick, so wait for the steps to fold away
    pg.wait_for_function("() => document.getElementById('installer').hidden || getComputedStyle(document.getElementById('installer')).display === 'none'", timeout=5000)
    pg.wait_for_timeout(800)
    check("steps fold away, card open with console", not pg.is_visible("#installer") and pg.is_visible("#console") and pg.is_visible("#console-out"))
    check("device card and console are two separate cards", pg.evaluate("(() => { const a = document.getElementById('console'), c = document.getElementById('console-card'); return a.classList.contains('card') && c.classList.contains('card') && !a.contains(c) && c.contains(document.getElementById('console-out')) && !a.contains(document.getElementById('console-out')); })()"))
    def fill():
        return pg.evaluate("[Math.round(innerHeight - document.getElementById('console-card').getBoundingClientRect().bottom - scrollY), document.getElementById('console-out').offsetHeight]")
    # Flasher Version 105: 600 ms to settle after a resize (200 ms was too short with eight suites at once on the box)
    f1 = fill(); pg.set_viewport_size({"width": 1280, "height": 700}); pg.wait_for_timeout(600); f2 = fill(); pg.set_viewport_size({"width": 1280, "height": 380}); pg.wait_for_timeout(600); f3 = fill()
    pg.set_viewport_size({"width": 1280, "height": 900}); pg.wait_for_timeout(200)
    check("console fills the window height, resizes, at least 200px", 8 <= f1[0] <= 24 and 8 <= f2[0] <= 24 and f2[1] < f1[1] and f3[1] == 200, str((f1, f2, f3)))
    check("115.10 connect: no probe (no restart): plain device name, USB bridge known, no RESET",
          pg.inner_text("#board-chip") == "ESP32 Device" and "CP2102" in pg.inner_text("#board-details") and "RESET" not in pg.evaluate("window.__log"),
          pg.inner_text("#board-chip") + " | " + pg.inner_text("#board-details"))
    # After probe the board is reset to run; mock GSP32 firmware boots — Install stays available
    pg.wait_for_timeout(800)
    check("after connect boot: Install button present", pg.is_visible("#install-btn") and "GSP32" in pg.inner_text("#install-btn"), pg.inner_text("#install-btn"))
    y0 = pg.evaluate("document.getElementById('console-out').getBoundingClientRect().top")
    heights = []
    pg.click("#install-btn")
    for i in range(6): heights.append(pg.evaluate("document.getElementById('wizard').offsetHeight")); pg.wait_for_timeout(40)
    check("prep step folds open inline", pg.is_visible("#wizard [data-step=prep]") and heights[0] < heights[-1], str(heights))
    pg.screenshot(path=shots + "/02-prep.png")
    check("gated by checkbox", pg.is_disabled("#start-install"))
    # Version 43.2 (Gene): the steps sit under the buttons and the status line they belong to
    check("V43.2 erase panel folds open under the buttons", pg.evaluate("(() => { const w = document.querySelector('[data-step=prep]').getBoundingClientRect(), a = document.getElementById('board-actions').getBoundingClientRect(); return w.top >= a.bottom - 1; })()"))
    check("erase checkbox inside the yellow box, on its left", pg.evaluate("(() => { const i = document.getElementById('erase-ok'), w = i.closest('.warn-box'); if (!w) return false; const t = w.querySelector('span').getBoundingClientRect(), r = i.getBoundingClientRect(); return r.right <= t.left && r.top < t.bottom && document.querySelectorAll('[data-step=prep] .check').length === 0; })()"))
    pg.check("#erase-ok"); pg.click("#start-install")
    pg.wait_for_selector("#wizard [data-step=flash]:not([hidden])", state="attached")
    fills = []
    pg.wait_for_timeout(350)
    check("V30 install button row folded away while installing", not pg.is_visible("#board-actions"))
    check("V30 status names the version while installing", pg.inner_text("#board-status").startswith("Installing " + LISTED), pg.inner_text("#board-status"))
    for _ in range(12):
        pg.wait_for_timeout(150); fills.append(pg.evaluate("getComputedStyle(document.getElementById('board-status')).getPropertyValue('--fill')"))
    check("V29 status line is the progress bar (fill grows), no sub card", any(f.strip() not in ("", "0%") for f in fills)
          and pg.evaluate("getComputedStyle(document.getElementById('wizard')).borderTopWidth") == "0px"
          and not pg.is_visible("#flash-status"), str(fills))
    pg.wait_for_function("document.getElementById('wizard').hidden", timeout=20000)
    check("V30 status line: 'Version 30 Installed'", pg.inner_text("#board-status").split("\n")[0].split(" Next:")[0].strip() == LISTED + " Installed" and "Next: click Set Up Wi-Fi" in pg.inner_text("#board-status"), pg.inner_text("#board-status"))
    pg.wait_for_timeout(400)
    check("V30 install button row back after the install", pg.is_visible("#board-actions") and pg.is_visible("#install-btn"))
    out = pg.inner_text("#console-out")
    check("esptool output in the one console", "[esptool]" in out and "[Installing" in out, out[-300:].replace("\n"," | "))
    log = pg.evaluate("window.__log")
    opens = [l for l in log if isinstance(l, str) and l.startswith("open")]
    # V49: the install reopens the port for the faster rate and back to 115200 after; the pick opens it once
    check("V64: only ever 115200 opens, run state, reset after flash", opens[0] == "open 115200" and opens[-1] == "open 115200" and "open 921600" not in log and "RESET" in log
          # 115.10: the pick sets no lines (the board keeps running; log[1] was its run state); the reset after the
          #  flash still goes back to the run state
          and log[1] != "signals dtr=false rts=false" and "signals dtr=false rts=true" in log
          and log[log.index("signals dtr=false rts=true") + 1] == "signals dtr=false rts=false", str(log[:6]))
    pg.wait_for_timeout(800)
    check("re-detected GSP32 after install", pg.is_visible("#wifi-setup") and pg.inner_text("#wifi-setup") == "Set Up Wi-Fi" and pg.inner_text("#install-btn") == "Reinstall GSP32"
          and pg.inner_text("#board-state") == "GSP32 " + LISTED + " Found" and pg.locator("#board-hint, [data-step=choice], [data-step=usb]").count() == 0 and not pg.is_visible("#console-webui"), pg.inner_text("#board-state"))
    # V30: a button that is hidden or shown slides sideways (its width animates), never jumps
    widths = pg.evaluate("""(async () => { const b = document.getElementById('wifi-setup'); const out = [];
      gsp32.setShown(b, false); for (let i = 0; i < 5; i++) { await new Promise(r => setTimeout(r, 40)); out.push(b.hidden ? -1 : b.getBoundingClientRect().width); }
      await new Promise(r => setTimeout(r, 200)); out.push(b.hidden ? -1 : 0);
      gsp32.setShown(b, true); for (let i = 0; i < 5; i++) { await new Promise(r => setTimeout(r, 40)); out.push(b.getBoundingClientRect().width); }
      await new Promise(r => setTimeout(r, 200)); out.push(b.getBoundingClientRect().width); return out; })()""")
    shut, opened = widths[:5], widths[6:]
    check("V30 buttons slide out and in (width animates both ways)", widths[5] == -1 and any(0 < w < opened[-1] for w in shut) and any(0 <= w < opened[-1] - 2 for w in opened[:3]) and opened[-1] > 40, str(widths))
    check("after install: Set Up Wi-Fi primary, Reinstall secondary", "primary" in pg.get_attribute("#wifi-setup", "class") and "secondary" in pg.get_attribute("#install-btn", "class"))
    check("chip title and MAC from esptool", pg.inner_text("#board-chip").startswith("ESP32-D0WD-V3") and "F8:B3:B7:22:05:E8" in pg.inner_text("#board-mac")
          and pg.evaluate("getComputedStyle(document.getElementById('board-mac')).textTransform") == "uppercase", pg.inner_text("#board-chip") + " / " + pg.inner_text("#board-mac"))
    # Version 43.1: the version is known from the install, so nothing is asked; nothing ever reaches a board that is not listening
    # Flasher Version 104: three-digit versions (106) count too
    check("V43.1: version known after install, no Improv to a quiet device", re.search(r"Version (4[3-9]|[5-9][0-9]|[1-9][0-9]{2})", pg.inner_text("#board-state")) is not None and pg.evaluate("window.__badPk") == 0, pg.inner_text("#board-state"))
    pg.screenshot(path=shots + "/03-choice.png")
    pg.click("#wifi-setup"); pg.wait_for_timeout(600)
    check("Wi-Fi wizard scrolled into view", pg.evaluate("(() => { const r = document.getElementById('wizard').getBoundingClientRect(); return r.top >= 0 && r.top < innerHeight; })()"))
    pg.wait_for_selector("#wifi-list li", timeout=20000)
    check("networks listed", pg.locator("#wifi-list li").count() == 2)
    pg.click("#wifi-list li:first-child label"); pg.click("#wifi-connect"); pg.fill("#wifi-password", "secret"); pg.click("#wifi-modal-connect")
    pg.wait_for_function("document.getElementById('wizard').hidden", timeout=30000); pg.wait_for_timeout(400)
    pg.screenshot(path=shots + "/04-done.png")
    check("V39: status line: Wi-Fi Connected! + ready text with the address as a link", pg.inner_text("#board-status").startswith("Wi-Fi Connected!")
          and "Your device is ready. Open http://192.168.2.77/ in a browser on the same network to use GSP32, or click Open Web UI." in pg.inner_text("#board-status")
          and pg.get_attribute("#board-status a", "href") == "http://192.168.2.77/", pg.inner_text("#board-status"))
    st = pg.locator("#board-state a")
    check("badge address is a link", st.count() == 1 and st.get_attribute("href") == "http://192.168.2.77/" and "Web UI: http://192.168.2.77/" in pg.inner_text("#board-state .web-line"), pg.inner_text("#board-state"))
    check("Change Wi-Fi + Open GSP32 Web UI, nothing greyed", pg.inner_text("#wifi-setup") == "Change Wi-Fi" and pg.is_visible("#console-webui")
          and pg.get_attribute("#console-webui", "href") == "http://192.168.2.77/" and pg.is_enabled("#install-btn") and pg.is_enabled("#wifi-setup"))
    check("after Wi-Fi: Open GSP32 Web UI primary, Reinstall and Change Wi-Fi secondary", "primary" in pg.get_attribute("#console-webui", "class")
          and "secondary" in pg.get_attribute("#install-btn", "class") and "secondary" in pg.get_attribute("#wifi-setup", "class"))
    out = pg.inner_text("#console-out")
    check("console agrees: connecting, connected, no reset claim", "[Connecting to Wi-Fi (HomeNet)...]" in out and "[Wi-Fi connected." in out and "Restarting" not in pg.inner_text("#console").split("Console")[0])
    check("never Ctrl-C, few packets", pg.evaluate("window.__ctrlc") == 0 and pg.evaluate("window.__pk") < 15, str(pg.evaluate("window.__pk")))
    check("wizard folds away", not pg.is_visible("#wizard"))
    sc = pg.evaluate("""(async () => { const c = document.getElementById('console-out'); const add = () => { for (let i = 0; i < 40; i++) gsp32.appendConsole('line ' + i + '\\n'); };
      add(); await new Promise(r => setTimeout(r, 50)); const bottom1 = c.scrollHeight - c.scrollTop - c.clientHeight;
      c.scrollTop = 0; await new Promise(r => setTimeout(r, 50)); add(); await new Promise(r => setTimeout(r, 50)); const top = c.scrollTop;
      c.scrollTop = c.scrollHeight; await new Promise(r => setTimeout(r, 50)); add(); await new Promise(r => setTimeout(r, 50));
      return [bottom1, top, c.scrollHeight - c.scrollTop - c.clientHeight]; })()""")
    check("console follows new output, pauses when scrolled up, resumes at the bottom", sc[0] < 4 and sc[1] == 0 and sc[2] < 4, str(sc))
    noscroll = pg.evaluate("document.documentElement.scrollHeight - innerHeight")
    check("no extra page scroll with the console open", noscroll <= 2, str(noscroll))
    pg.click("#copy-log"); pg.wait_for_timeout(100)
    check("Copy Log", pg.inner_text("#copy-log") == "Copied")
    pg.click("#disconnect"); pg.wait_for_timeout(700)
    log = pg.evaluate("window.__log")
    check("Disconnect: run state, card gone, steps and Get Started back", log[-1] == "close dtr=false rts=false" and not pg.is_visible("#console") and pg.is_visible("#installer") and pg.is_visible("#connect"))
    # error path
    pg.click("#connect"); pg.wait_for_timeout(2500)
    pg.evaluate("window.__failFlash = true")
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install")
    # 115.10: a classic board whose first connect fails gets the hold-BOOT note and 2.5 s before the second try
    try: pg.wait_for_selector("#wizard [data-step=error]", state="visible", timeout=20000)
    except Exception: pass
    pg.wait_for_timeout(600)
    check("error step inline, console still open", pg.is_visible("#wizard [data-step=error]") and pg.is_visible("#console-out") and pg.is_visible("#copy-log"), pg.inner_text("#wizard")[:200])
    pg.wait_for_timeout(500); check("warning gone after failed flash", not pg.is_visible("#flash-warn"))
    check("V30 install button row back after a failed install", pg.is_visible("#install-btn"))
    check("status line shows the error", "did not finish" in pg.inner_text("#board-status") and "error" in pg.get_attribute("#board-status", "class"), pg.inner_text("#board-status"))
    pg.screenshot(path=shots + "/05-error.png")
    check("latest build only, as plain text (no dropdown)", pg.inner_text("#version") == LISTED and pg.locator("select:not(#release-channel)").count() == 0, pg.inner_text("#version"))
    check("no page errors", not errors, str(errors))
    o = b.new_page(viewport={"width": 1280, "height": 900}); o.add_init_script(path=here + "/mock.js"); o.add_init_script(path=here + "/classic.js"); o.add_init_script("window.__other = true")
    o.add_init_script("try { localStorage.clear(); } catch (e) {}")
    o.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    o.goto(U); o.evaluate("localStorage.clear()"); o.wait_for_timeout(300); o.click("#connect")
    o.wait_for_function("""() => {
      const d = document.getElementById('board-details');
      const out = document.getElementById('console-out');
      return (d && !d.hidden && d.textContent) || (out && /Reading board info|Could not read|Board:|keeps running/.test(out.textContent||''));
    }""", timeout=15000)
    o.wait_for_timeout(400)
    o.click("#reset"); o.wait_for_timeout(21500)
    check("other firmware: No GSP32 Found, only Install, no Improv sent", not o.is_visible("#wifi-setup") and not o.is_visible("#console-webui") and o.inner_text("#board-state") == "No GSP32 Found"
          and o.inner_text("#install-btn") == "Install GSP32" and not o.evaluate("window.__info")
          and "ESP32" in o.inner_text("#board-chip"), o.inner_text("#board-state") + " | " + o.inner_text("#board-chip"))
    o.screenshot(path=shots + "/06-other.png")
    f = b.new_page(viewport={"width": 1280, "height": 900}); f.add_init_script(path=here + "/mock.js"); f.add_init_script(path=here + "/classic.js")
    f.add_init_script("window.__flashDelay = 300; ")
    f.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    f.goto(U); f.wait_for_timeout(300); f.click("#connect"); f.wait_for_timeout(2500)
    check("no warning before flashing", not f.is_visible("#flash-warn"))
    f.click("#install-btn"); f.check("#erase-ok"); f.click("#start-install"); f.wait_for_timeout(600)
    wb = f.locator("#flash-warn").bounding_box()
    pad = f.evaluate("parseFloat(getComputedStyle(document.getElementById('flash-warn')).paddingTop)")
    check("status line: Installing Version N (N%)", f.inner_text("#board-status").startswith("Installing " + LISTED), f.inner_text("#board-status"))
    pb = f.locator("#board-status").bounding_box()
    check("V42.1: red warning text directly under the progress bar, slim", f.is_visible("#flash-warn") and 0 <= wb["y"] - (pb["y"] + pb["height"]) <= 8
          and wb["height"] <= 24 and f.inner_text("#flash-warn") == "Changing Tabs Could Cause the Install to Fail", str((pb, wb)))
    check("V38: page title and text folded away with the steps", not f.is_visible("#page-head"))
    check("V39: green device box folded away while installing", not f.is_visible("#board-state"))
    check("V42.1 warning: red text, no fill or border, centered", f.evaluate("(() => { const c = getComputedStyle(document.getElementById('flash-warn')); return [c.backgroundColor, c.color, c.borderTopWidth, c.textAlign]; })()") == ["rgba(0, 0, 0, 0)", "rgb(198, 40, 40)", "0px", "center"])
    check("during install: Wi-Fi and Web UI buttons hidden (not greyed)", not f.is_visible("#wifi-setup") and not f.is_visible("#console-webui"))
    check("old inline warning gone", f.locator(".danger-note").count() == 0 and f.inner_text("body").count("Changing Tabs Could") == 1)
    f.screenshot(path=shots + "/08-banner.png")
    f.wait_for_function("document.getElementById('wizard').hidden", timeout=20000); f.wait_for_timeout(500)
    check("warning slides away after flash", not f.is_visible("#flash-warn"))
    f.wait_for_timeout(800); check("V39: green device box back after the install", f.is_visible("#board-state"))
    f.wait_for_timeout(1000); check("Set Up Wi-Fi back after the install", f.is_visible("#wifi-setup"))
    k = b.new_page(viewport={"width": 1280, "height": 900}); k.add_init_script(path=here + "/mock.js"); k.add_init_script(path=here + "/classic.js")
    k.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    k.goto(U); k.wait_for_timeout(300); k.click("#connect")
    k.wait_for_function("""() => {
      const d = document.getElementById('board-details');
      return d && !d.hidden && d.textContent;
    }""", timeout=15000)
    k.wait_for_timeout(500)
    k.evaluate("window.__bootGap = 2000"); k.click("#reset"); k.wait_for_timeout(900)
    mid = (k.inner_text("#board-status") if k.is_visible("#board-status") else "", k.is_visible("#install-btn"))
    k.wait_for_timeout(2500)
    end = (k.is_visible("#board-status"), k.is_visible("#install-btn"), k.is_visible("#wifi-setup"))
    check("boot banner: 'Board Booting Up...', buttons stay (V42.1), status gone at the ready marker", mid == ("Device Booting Up...", True) and end == (False, True, True), str((mid, end)))
    m = b.new_page(viewport={"width": 390, "height": 800}, is_mobile=True, user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile")
    m.goto(U); check("mobile blocked", m.is_visible("#browser-block")); m.screenshot(path=shots + "/07-mobile.png")
    b.close()
print(ok, "passed", bad, "failed")
