# Flasher Version 115.10 (Gene's classic ESP32, CP2102, 26 Oct 2026): after a good GSP32-C Beta V125 install the board
#  printed "GSP32-C: no Wi-Fi set; gsp.wifi(...) sets it" and "main.py running", but Set Up Wi-Fi led nowhere and the
#  console box stayed "Busy ...". V125 answers the Improv scan with an empty list while no Wi-Fi is set (its radio is
#  off), the page then showed "No networks found" with only Scan Again, and the open Wi-Fi step locked the console, so
#  gsp.wifi(...) could not be typed either. Now: the name can be typed, the console way is shown, the console stays
#  usable whenever the page is not talking to the board, and every install end hands the port back to the page.
#  Also: a classic board that no reset style puts into download mode gets the hold-BOOT note (it folds in), at once in
#  the install step and again with the error. GSP32-C's main.py in the foreground keeps Improv from the board until
#  Ctrl-C: Set Up Wi-Fi sends it and waits for >>> (or says it could not). A plain connect, reconnect or Disconnect of a
#  classic board never restarts it (no probe, DTR and RTS untouched on connect, set RTS first on Disconnect), modelled
#  on Chromium on Windows: the port opens with both lines on, and setSignals sets DTR, then RTS. The password of an
#  echoed gsp.wifi(...) line is shown as dots.
#  SITE=<dir> runs the same checks against another copy of the page (e.g. Flasher 115.9, where they fail)
import sys, http.server, threading, functools, os, json
from playwright.sync_api import sync_playwright
here = os.path.dirname(os.path.abspath(__file__))
site = os.environ.get("SITE") or os.path.dirname(here)
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8893), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
U = "http://127.0.0.1:8893/index.html"
SECRET = "Sekr3t-Gene-125"
fails = 0
def check(name, ok, extra=""):
    # The mock board prints MicroPython's KeyboardInterrupt traceback (after Ctrl-C); echoed console text must not read
    #  as this suite's own Python traceback to tools/flasher_tests.py
    extra = str(extra).replace("Traceback (most recent call last)", "Traceback (board output)")
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra); sys.stdout.flush()
# What Gene's ESP32 printed after the install (V125, first boot, nothing saved): ROM lines, the first-boot setup, the
#  GSP32-C line, the no-Wi-Fi line and main.py, no >>> prompt (main.py runs). Third item: whether it takes Improv
GENE_BOOT = [
    [150, "ets Jul 29 2019 12:21:46\r\n\r\nrst:0x1 (POWERON_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)\r\nconfigsip: 0, SPIWP:0xee\r\n"
          "clk_drv:0x00,q_drv:0x00,d_drv:0x00,cs0_drv:0x00,hd_drv:0x00,wp_drv:0x00\r\nmode:DIO, clock div:2\r\nload:0x3fff0030,len:4892\r\n"
          "ho 0 tail 12 room 4\r\nload:0x40078000,len:14896\r\nload:0x40080400,len:4\r\nload:0x40080404,len:3372\r\nentry 0x400805b0\r\n"],
    [600, "Performing initial setup\r\n"],
    [2500, "\r\n\r\nGSP32-C Beta V125 on ESP32 (GSP32-C ESP32), boot 1, reset: power-on\r\n\r\ngsp.help() lists the GSP32-C commands.\r\n\r\n", True],
    [2600, "GSP32-C: no Wi-Fi set; gsp.wifi('name', 'password') sets it\r\n\r\n"],
    [3200, "main.py running\r\n"],
]
def page(b, init=""):
    pg = b.new_page(viewport={"width": 1280, "height": 900}); pg.add_init_script(path=here + "/mock.js")
    pg.add_init_script("window.__usb = {usbVendorId: 0x10c4, usbProductId: 0xea60}; window.__geneBoot = %s;" % json.dumps(GENE_BOOT))
    if init: pg.add_init_script(init)
    errors = []; pg.on("pageerror", lambda e: errors.append(str(e))); pg.__errors = errors
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.route("**/gsp32-telemetry.genereese.workers.dev/**", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true}'))
    pg.goto(U); pg.wait_for_timeout(300); return pg
def connect(pg):
    pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(3000)
def install(pg, script="window.__geneBoot"):
    pg.click("#install-btn"); pg.wait_for_timeout(400)
    pg.select_option("#release-channel", "gspc-125"); pg.wait_for_timeout(300)
    pg.evaluate("window.__bootScript = %s" % script); pg.check("#erase-ok"); pg.click("#start-install")
def console_ok(pg):
    return pg.evaluate("({dis: document.getElementById('console-in').disabled, send: document.getElementById('console-send').disabled, ph: document.getElementById('console-in').placeholder})")
def typed_reaches_board(pg, text):
    pg.evaluate("window.__typed = ''")
    try:
        pg.fill("#console-in", text, timeout=1500); pg.press("#console-in", "Enter", timeout=1500); pg.wait_for_timeout(300)
    except Exception:
        return False  # the box is locked
    return text in pg.evaluate("window.__typed || ''")
def board_text_shows(pg, text):
    pg.evaluate("window.__say(%s)" % json.dumps(text + "\r\n")); pg.wait_for_timeout(400)
    return text in pg.inner_text("#console-out")

with sync_playwright() as p:
    b = p.chromium.launch()
    # 1. Gene's flow: a V120 board, Install GSP32-C Beta V125, the board starts with no Wi-Fi saved (V125: empty scan)
    pg = page(b, "window.__gspc = '120'; window.__noNets = true;")
    connect(pg); install(pg)
    pg.wait_for_function("/main\\.py running/.test(document.getElementById('console-out').innerText)", timeout=60000)
    pg.wait_for_timeout(800)
    st = pg.inner_text("#board-state")
    check("install: GSP32-C Beta V125 Found", "GSP32-C Beta V125 Found" in st, st)
    c = console_ok(pg)
    check("install done: console box takes typing (not Busy ...)", not c["dis"] and not c["send"] and c["ph"] != "Busy ...", c)
    check("install done: Set Up Wi-Fi shown and enabled", pg.is_visible("#wifi-setup") and pg.is_enabled("#wifi-setup"))
    check("install done: the page writes to the port again (typed text reaches the board)", typed_reaches_board(pg, "print('hi')"))
    check("install done: the page reads the port again (board text shows)", board_text_shows(pg, "board-says-hello-1"))
    # Set Up Wi-Fi: visible at once, then the empty scan is no dead end
    pg.click("#wifi-setup"); pg.wait_for_timeout(150)
    ws = pg.inner_text("#board-status")
    check("Set Up Wi-Fi: the Wi-Fi step opens at once with a status", pg.is_visible("[data-step=wifi]") and ws.strip() != "", ws)
    pg.wait_for_function("/No networks found/.test(document.getElementById('board-status').innerText)", timeout=30000); pg.wait_for_timeout(500)
    st = pg.inner_text("#board-status")
    check("empty scan: says why (GSP32-C lists networks once Wi-Fi was set) and to type the name", "Type your network name" in st and "GSP32-C" in st, st)
    check("empty scan: a box for the network name", pg.is_visible("#wifi-name"))
    fb = pg.inner_text("#wifi-fallback") if pg.is_visible("#wifi-fallback") else ""
    check("empty scan: the console way is shown (Send Ctrl-C, gsp.wifi('name', 'password'))", "gsp.wifi('name', 'password')" in fb and "Send Ctrl-C" in fb, fb)
    c = console_ok(pg)
    check("empty scan: console box usable while the Wi-Fi step waits (the bug: Busy ...)", not c["dis"] and c["ph"] != "Busy ...", c)
    check("empty scan: Ctrl-C button usable", pg.is_enabled("#ctrl-c"))
    check("empty scan: Connect greyed until a name is typed", pg.is_disabled("#wifi-connect") and "Type your network name" in pg.inner_text("#wifi-note"),
          pg.inner_text("#wifi-note"))
    check("Set Up Wi-Fi: Ctrl-C sent first (main.py ran in the foreground)", pg.evaluate("window.__ctrl1 || 0") >= 1 and "[Set Up Wi-Fi: Ctrl-C stops main.py" in pg.inner_text("#console-out"),
          pg.evaluate("window.__ctrl1 || 0"))
    check("Set Up Wi-Fi: Improv reached the board only after the prompt", pg.evaluate("window.__mainPy") is False and ">>>" in pg.inner_text("#console-out"))
    check("empty scan: gsp.wifi(...) typed in the console reaches the board", typed_reaches_board(pg, "import gsp; gsp.wifi('HomeNet', 'x')"))
    # The REPL echoes the line: the password is shown as dots (console and Copy Log); the board's own hint stays
    pg.evaluate("window.__say(%s)" % json.dumps(">>> import gsp; gsp.wifi('HomeNet', '%s')\r\n" % SECRET)); pg.wait_for_timeout(400)
    out = pg.inner_text("#console-out")
    check("echoed gsp.wifi(...): password masked in the console", SECRET not in out and "gsp.wifi('HomeNet', '\u2022" in out, out[-300:])
    check("echoed gsp.wifi(...): the board's hint gsp.wifi('name', 'password') kept", "gsp.wifi('name', 'password')" in out)
    pg.fill("#wifi-name", "HomeNet")
    check("typed name: Connect enabled", pg.is_enabled("#wifi-connect"))
    pg.click("#wifi-connect"); pg.fill("#wifi-password", SECRET); pg.click("#wifi-modal-connect")
    pg.wait_for_function("document.getElementById('wizard').hidden", timeout=30000); pg.wait_for_timeout(300)
    st = pg.inner_text("#board-status")
    check("typed name: Wi-Fi Connected! with the address", st.startswith("Wi-Fi Connected!") and "192.168.2.77" in st, st)
    check("typed name: the board got that name", pg.evaluate("window.__wifiSet") == "HomeNet", pg.evaluate("window.__wifiSet"))
    check("typed name: password not in the console", SECRET not in pg.inner_text("#console-out"))
    check("flow 1: no page errors", not pg.__errors, pg.__errors)
    pg.close()

    # 2. A V125 board that never answers Improv: a clear error with the console way, console usable, Try Again
    silent = [[t, x] for t, x, *rest in GENE_BOOT]  # the GSP32-C line without listening (window.__listen stays false)
    pg = page(b, "window.__gspc = '120'; window.__silentBoot = %s;" % json.dumps(silent))
    connect(pg); install(pg, "window.__silentBoot")
    pg.wait_for_function("/main\\.py running/.test(document.getElementById('console-out').innerText)", timeout=60000); pg.wait_for_timeout(500)
    pg.click("#wifi-setup")
    pg.wait_for_function("/did not answer Wi-Fi setup/.test(document.getElementById('board-status').innerText)", timeout=90000); pg.wait_for_timeout(500)
    fb = pg.inner_text("#wifi-fallback") if pg.is_visible("#wifi-fallback") else ""
    check("no answer: main.py stopped first (Ctrl-C)", pg.evaluate("window.__ctrl1 || 0") >= 1)
    check("no answer: error with the console way", "gsp.wifi('name', 'password')" in fb, pg.inner_text("#board-status") + " | " + fb)
    check("no answer: Try Again offered", pg.is_visible("#wifi-rescan") and pg.inner_text("#wifi-rescan") == "Try Again")
    c = console_ok(pg)
    check("no answer: console box usable", not c["dis"] and c["ph"] != "Busy ...", c)
    check("no answer: typed text reaches the board", typed_reaches_board(pg, "gsp.wifi('a', 'b')"))
    check("flow 2: no page errors", not pg.__errors, pg.__errors)
    pg.close()

    # 2b. main.py that ignores Ctrl-C: no prompt, so Set Up Wi-Fi says so (with the console way), console usable
    pg = page(b, "window.__gspc = '120'; window.__mainPyStuck = true;")
    connect(pg); install(pg)
    pg.wait_for_function("/main\\.py running/.test(document.getElementById('console-out').innerText)", timeout=60000); pg.wait_for_timeout(500)
    pg.click("#wifi-setup")
    pg.wait_for_function("/main\\.py did not stop/.test(document.getElementById('board-status').innerText)", timeout=30000); pg.wait_for_timeout(500)
    fb = pg.inner_text("#wifi-fallback") if pg.is_visible("#wifi-fallback") else ""
    check("main.py stuck: two Ctrl-C at most, then the error", pg.evaluate("window.__ctrl1 || 0") == 2, pg.evaluate("window.__ctrl1 || 0"))
    check("main.py stuck: the console way shown", "Send Ctrl-C" in fb, fb)
    check("main.py stuck: no Improv sent into main.py", (pg.evaluate("window.__blockedPk") or 0) == 0)
    c = console_ok(pg)
    check("main.py stuck: console box usable", not c["dis"] and c["ph"] != "Busy ...", c)
    pg.close()

    # 3. Gene's earlier tries: no reset style reaches download mode (the board keeps starting its program): the install
    #  error, the hold-BOOT note folding in under it, and the port back to the page (console usable, reader running)
    pg = page(b, "window.__gspc = '120'; window.__resetWorks = 'none';")
    connect(pg)
    pg.click("#install-btn"); pg.wait_for_timeout(400); pg.select_option("#release-channel", "gspc-125"); pg.wait_for_timeout(300)
    pg.check("#erase-ok"); pg.click("#start-install")
    # The first connect fails: the hold-BOOT note folds into the install step at once, before the second try
    pg.wait_for_function("!document.getElementById('boot-now').hidden", timeout=90000)
    seen = pg.evaluate("({step: !document.querySelector('[data-step=flash]').hidden, text: document.getElementById('boot-now').innerText, syncs: window.__syncs || 0, err: !document.getElementById('boot-hint').hidden})")
    check("first connect failed: hold-BOOT now note in the install step, error not yet", seen["step"] and "Hold BOOT now" in seen["text"] and not seen["err"], seen)
    s0 = pg.evaluate("window.__syncs || 0"); pg.wait_for_timeout(1500)
    check("hold-BOOT now: a pause to press BOOT before the second try", pg.evaluate("window.__syncs || 0") == s0, (s0, pg.evaluate("window.__syncs")))
    pg.wait_for_function("!document.getElementById('boot-hint').hidden", timeout=90000)
    h0 = pg.evaluate("document.getElementById('boot-hint').getBoundingClientRect().height")
    pg.wait_for_timeout(700)
    h1 = pg.evaluate("document.getElementById('boot-hint').getBoundingClientRect().height")
    hint = pg.inner_text("#boot-hint")
    check("connect failed: error says the board did not answer", "did not answer" in pg.inner_text("#board-status"), pg.inner_text("#board-status"))
    check("connect failed: Resets tried listed in the console", "[Resets tried:" in pg.inner_text("#console-out"))
    check("connect failed: hold-BOOT note shown", pg.is_visible("#boot-hint") and "Hold BOOT" in hint and "keep holding BOOT until" in hint, hint)
    check("hold-BOOT note folds in (grows, no jump)", h0 < h1 and h1 > 20, (h0, h1))
    c = console_ok(pg)
    check("install failed: console box usable", not c["dis"] and c["ph"] != "Busy ...", c)
    check("install failed: the page reads the port again", board_text_shows(pg, "board-says-hello-3"))
    check("install failed: typed text reaches the board", typed_reaches_board(pg, "help()"))
    # Try Again with BOOT held (the reset now works): the install goes through and the note is gone
    pg.evaluate("window.__resetWorks = undefined; window.__bootScript = window.__geneBoot")
    pg.click("#error-retry"); pg.wait_for_timeout(400)
    pg.check("#erase-ok"); pg.click("#start-install")
    pg.wait_for_function("/main\\.py running/.test(document.getElementById('console-out').innerText)", timeout=60000); pg.wait_for_timeout(800)
    check("retry: installed, hold-BOOT notes gone", "Installed" in pg.inner_text("body") and not pg.is_visible("#boot-hint") and not pg.is_visible("#boot-now"))
    c = console_ok(pg)
    check("retry: console box usable", not c["dis"] and c["ph"] != "Busy ...", c)
    check("flow 3: no page errors", not pg.__errors, pg.__errors)
    pg.close()

    # 5. Plain connect, Disconnect, reconnect of a running classic board (port opens with DTR and RTS on): no restart
    pg = page(b, "window.__gspc = '125'; window.__openAsserts = true;")
    pg.click("#connect"); pg.wait_for_timeout(2500)
    log = pg.evaluate("window.__log"); out = pg.inner_text("#console-out")
    check("connect: no restart (no RESET, no signals set)", "RESET" not in log and not any(x.startswith("signals") for x in log), log)
    check("connect: no Reading board info, says the board keeps running", "Reading board info" not in out and "keeps running (no restart)" in out, out[-300:])
    st = pg.inner_text("#board-state")
    check("connect: board shown as left running, Set Up Wi-Fi and Install offered", "Left Running" in st and pg.is_visible("#wifi-setup") and pg.is_enabled("#install-btn"), st)
    c = console_ok(pg)
    check("connect: console usable", not c["dis"] and c["ph"] != "Busy ...", c)
    check("connect: the board's output shows", board_text_shows(pg, "running-board-says-hi"))
    pg.click("#disconnect"); pg.wait_for_timeout(800)
    log = pg.evaluate("window.__log")
    sig = [x for x in log if x.startswith("signals")]
    check("Disconnect: no restart (RTS off first, then DTR, then close)", "RESET" not in log and sig[:2] == ["signals dtr=true rts=false", "signals dtr=false rts=false"]
          and any(x.startswith("close") for x in log), log)
    lines = pg.evaluate("window.__lines || []")
    check("115.11 connect + Disconnect: EN never pulled low", pg.evaluate("window.__enPulses || 0") == 0, lines)
    check("115.11 Disconnect: two separate calls, RTS off, a gap, then DTR off",
          [x[0] for x in lines[:2]] == ["rts=false", "dtr=false"] and lines[1][1] - lines[0][1] >= 20, lines)
    pg.evaluate("window.__log.length = 0; window.__lines = []"); pg.click("#connect"); pg.wait_for_timeout(2000)
    log = pg.evaluate("window.__log")
    check("reconnect: no restart", "RESET" not in log and not any(x.startswith("signals") for x in log), log)
    # Leaving the page: RTS off first too, no EN pulse
    pg.evaluate("window.dispatchEvent(new Event('pagehide'))"); pg.wait_for_timeout(300)
    lines = pg.evaluate("window.__lines")
    check("115.11 page leave: RTS off, then DTR off, EN never low", [x[0] for x in lines] == ["rts=false", "dtr=false"] and pg.evaluate("window.__enPulses || 0") == 0, lines)
    # Back to both on (as the port opened), for the Set Up Wi-Fi restart below
    pg.evaluate("window.__port.setSignals({ requestToSend: true }).then(() => window.__port.setSignals({ dataTerminalReady: true }))"); pg.wait_for_timeout(200)
    pg.evaluate("window.__enPulses = 0; window.__lines = []; window.__log.length = 0")
    # Set Up Wi-Fi on the quiet board restarts it once (the click asks for it), then GSP32-C is found and asked
    pg.click("#wifi-setup")
    pg.wait_for_function("/GSP32-C Beta V125 Found/.test(document.getElementById('board-state').innerText)", timeout=30000)
    check("Set Up Wi-Fi on a quiet board: restarted once, GSP32-C found", pg.evaluate("window.__log").count("RESET") == 1, pg.evaluate("window.__log"))
    pg.wait_for_function("/Pick your network|HomeNet/.test(document.getElementById('wizard').innerText)", timeout=30000)
    check("Set Up Wi-Fi on a quiet board: networks listed", "HomeNet" in pg.inner_text("#wifi-list"))
    lines = [x[0] for x in pg.evaluate("window.__lines")]
    # The restart the click asks for is the one EN pulse; back to run state RTS first (both lines off, never DTR first)
    check("115.11 Set Up Wi-Fi restart: one EN pulse, run state RTS off then DTR off", pg.evaluate("window.__enPulses") == 1
          and all(lines[k + 1] == "dtr=false" for k in range(len(lines) - 1) if lines[k] == "rts=false" and k + 1 < len(lines) and lines[k + 1].startswith("dtr")), lines)
    check("flow 5: no page errors", not pg.__errors, pg.__errors)
    pg.close()

    # 5b. The mock is faithful: one setSignals call with both lines off, from both on, goes DTR first and pulses EN
    #  (what 115.10's single call did on Gene's board); two calls RTS first do not
    pg = page(b, "window.__gspc = '125'; window.__openAsserts = true;")
    pg.click("#connect"); pg.wait_for_timeout(1500)
    pg.evaluate("window.__port.setSignals({ dataTerminalReady: false, requestToSend: false })"); pg.wait_for_timeout(100)
    check("mock: single call from both on = DTR first, an EN pulse (a restart)", pg.evaluate("window.__enPulses") == 1 and "RESET" in pg.evaluate("window.__log"))
    pg.close()

    # 4. Native USB (0x303A): a failed connect gets the BOOT and RST guide as before, not the classic note
    pg = page(b, "window.__usb = {usbVendorId: 0x303a, usbProductId: 0x1001}; window.__ver = '116'; window.__resetWorks = 'none';")
    connect(pg)
    pg.click("#install-btn"); pg.wait_for_timeout(300); pg.check("#erase-ok"); pg.click("#start-install")
    pg.wait_for_function("/did not finish/.test(document.getElementById('board-status').innerText)", timeout=90000); pg.wait_for_timeout(400)
    check("native USB: no classic hold-BOOT note", not pg.is_visible("#boot-hint"))
    pg.close()
    b.close()
print("fails", fails); sys.exit(1 if fails else 0)
