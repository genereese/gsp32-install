# Fix (S3 native USB): a board on Espressif's own USB (VID 0x303A) running GSP32 (TinyUSB, the T-Display-S3's COM12)
#  can't be reset into download mode from the page, and when it restarts its port goes (COM10 in download mode). The
#  guide "Hold BOOT, Tap RST, Release BOOT, Then Pick the Port Again" folds open, the picker asks again (0x303A ports
#  only) or a port the page may already use is taken when it comes back, and the page goes on: board info read without
#  a reset (download mode is checked with one SYNC), the install, the restart onto GSP32's port, Wi-Fi. Wi-Fi setup
#  works without the board info. Other USB bridges keep the old behaviour
import sys, http.server, threading, functools, os, time, json
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=site)
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8820), handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
here = os.path.dirname(os.path.abspath(__file__)); fails = 0
SHOTS = os.environ.get("SHOTS", "/tmp/flasher-shots"); os.makedirs(SHOTS, exist_ok=True)
TITLE = "Hold BOOT, Tap RST, Release BOOT, Then Pick the Port Again"
def check(name, ok, info=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  " + str(info)[:600])); fails += not ok
def shown(pg, sel):
    return pg.evaluate("(s) => { const e = document.querySelector(s); return !!e && !e.hidden && !e.shutting && !(e.sliding && !e.sliding.on) && e.getBoundingClientRect().width > 0; }", sel)
def out(pg): return pg.inner_text("#console-out")
def log(pg): return pg.evaluate("window.__log")
def wait_text(pg, text, ms=15000):
    try: pg.wait_for_function("t => document.getElementById('console-out').innerText.includes(t)", arg=text, timeout=ms); return True
    except Exception: return False
def wait_js(pg, js, ms=15000):
    try: pg.wait_for_function(js, timeout=ms); return True
    except Exception: return False
# A second port for the same board in download mode (USB-JTAG/serial 303a:1001) next to the mock's own port (TinyUSB
#  303a:4001 here); the picker and the connect/disconnect events are scripted
HELPERS = """(() => {
  const base = window.__port, serial = navigator.serial;
  const fns = { connect: [], disconnect: [] };
  serial.addEventListener = (type, fn) => { if (fns[type]) fns[type].push(fn); };
  const dl = Object.create(base);
  dl.getInfo = () => ({ usbVendorId: 0x303a, usbProductId: 0x1001 });
  const ports = { base, dl };
  window.__syncs = 0; window.__requests = []; window.__pickQueue = [];
  // Download mode answers esptool's SYNC; anything else goes to the mock board
  for (const p of [base, dl]) {
    const open = base.open;
    p.open = async function (o) {
      await open.call(this, o);
      const inner = this.writable;
      this.writable = new WritableStream({ write: async (c) => {
        const a = Array.from(c);
        if (a[0] === 0xc0 && a[1] === 0x00 && a[2] === 0x08) {
          window.__syncs++; window.__log.push("sync " + (this === dl ? "dl" : "base"));
          if (window.__downloadMode && this.getInfo().usbProductId === 0x1001) setTimeout(() => window.__sayBytes([0xc0, 0x01, 0x08, 0x04, 0x00, 0, 0, 0, 0, 0, 0, 0xc0]), 5);
          return;
        }
        const w = inner.getWriter(); try { await w.write(c); } finally { w.releaseLock(); }
      } });
      window.__log.push("open " + (this === dl ? "dl" : "base"));
    };
  }
  // A restart that moves the board to a new port: the first DTR-on step of a reset (or any reset when asked) loses it.
  //  __silentReset: GSP32's TinyUSB port ignores the page's resets (the board neither restarts nor prints)
  const setSignals = base.setSignals;
  let sigDtr = false, sigRts = false;
  base.setSignals = async function (s) {
    let next = s;
    if (this === base) {
      const dtr = "dataTerminalReady" in s ? s.dataTerminalReady : sigDtr, rts = "requestToSend" in s ? s.requestToSend : sigRts;
      if (window.__silentReset && sigRts && !rts && !dtr) { window.__log.push("silent reset"); next = { dataTerminalReady: true, requestToSend: false }; }
      sigDtr = dtr; sigRts = rts;
    }
    await setSignals.call(this, next);
    if (this === base && window.__reenumArm && s.dataTerminalReady === true) { window.__reenumArm = false; setTimeout(() => window.__lose("base"), 0); }
    if (this === base && window.__reenumOnRun && s.requestToSend === true) { window.__reenumOnRun = false; setTimeout(() => window.__lose("base"), 30); }
    if (this === dl && window.__reenumDlOnRun && s.requestToSend === true) { window.__reenumDlOnRun = false; setTimeout(() => window.__lose("dl"), 200); }
  };
  window.__lose = (name) => { const p = ports[name]; window.__log.push("LOSE " + name); p.close(); p.writable = null; fns.disconnect.forEach((fn) => fn({ target: p })); };
  // The board starting GSP32 (as after a reset; GSP32's boot lines come on its own port once it is open)
  window.__boot = async () => { const quiet = window.__silentReset; window.__silentReset = false;
    try { await base.setSignals({ dataTerminalReady: false, requestToSend: true }); await base.setSignals({ requestToSend: false }); } finally { window.__silentReset = quiet; } };
  window.__arrive = (name) => { window.__log.push("ARRIVE " + name); fns.connect.forEach((fn) => fn({ target: ports[name] })); };
  serial.requestPort = async (o) => {
    window.__requests.push(JSON.stringify(o || null));
    const next = window.__pickQueue.shift();
    if (next === "cancel") throw new DOMException("No port selected by the user.", "NotFoundError");
    return ports[next || "base"];
  };
  window.__portName = () => null;
})();"""
def page(b, init="", w=1280):
    pg = b.new_page(viewport={"width": w, "height": 900}); pg.add_init_script(path=here + "/mock.js")
    pg.add_init_script("window.__ver = '102'; window.__ets = true; window.__usb = { usbVendorId: 0x303a, usbProductId: 0x4001 }; window.__chip = 'ESP32-S3 (QFN56) (revision v0.2)'; window.__features = ['Wi-Fi', 'BT 5', 'Dual Core', '240MHz', 'Embedded PSRAM 8MB (AP_3v3)'];" + init)
    pg.add_init_script(HELPERS)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.route("**/gsp32-telemetry.genereese.workers.dev/**", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true}'))
    errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:8820/index.html"); pg.wait_for_timeout(300)
    return pg, errors
def since(pg, n): return log(pg)[n:]
def install(pg):
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install")
with sync_playwright() as p:
    b = p.chromium.launch()

    # 1. GSP32 on the T-Display's TinyUSB port: no reset gets it into download mode. The guide folds open; the board
    #    stays connected (Wi-Fi setup still works); BOOT+RST moves it to the download-mode port, picked again; read
    #    without a reset and left in download mode; Install; the restart moves it back (a port the page may use: taken
    #    at once); Set Up Wi-Fi
    pg, errors = page(b, "window.__resetWorks = 'none'; window.__silentReset = true;")
    pg.evaluate("""(() => { window.__guideAnim = []; const a = Element.prototype.animate; Element.prototype.animate = function (k, o) {
        if (this.id === 'usb-guide' && Array.isArray(k)) window.__guideAnim.push(Object.keys(k[0]).join(',')); return a.call(this, k, o); }; })()""")
    t0 = time.time(); pg.click("#connect")
    check("probe on native USB: the guide folds open", wait_js(pg, "() => !document.getElementById('usb-guide').hidden", 20000))
    check("Flasher Version 105: at once (no 12 s of resets first)", time.time() - t0 < 3, round(time.time() - t0, 1))
    pg.wait_for_timeout(400)
    check("guide title in Title Case", pg.inner_text("#usb-guide-title").strip() == TITLE, pg.inner_text("#usb-guide-title"))
    check("guide text is short (one or two sentences)", 0 < len(pg.inner_text("#usb-guide-text")) <= 130, pg.inner_text("#usb-guide-text"))
    check("buttons: Pick the Port Again (primary), Set Up Wi-Fi Instead", pg.inner_text("#usb-guide-pick").strip() == "Pick the Port Again" and "primary" in pg.get_attribute("#usb-guide-pick", "class") and shown(pg, "#usb-guide-wifi") and pg.inner_text("#usb-guide-wifi").strip() == "Set Up Wi-Fi Instead")
    anim = pg.evaluate("window.__guideAnim")
    check("it slides and fades open (height, opacity)", bool(anim) and "height" in anim[0] and "opacity" in anim[0], anim)
    check("warn-box style like the compat notice", "warn-box" in pg.get_attribute("#usb-guide", "class"))
    check("console: GSP32's own port can't be switched from the page", "[GSP32's own USB port: the page can't switch it into download mode" in out(pg), out(pg)[-400:])
    check("not the plain 'Install can try again' line", "Install can try again" not in out(pg))
    check("still connected: Install and Disconnect usable", pg.evaluate("!document.getElementById('install-btn').disabled && !document.getElementById('disconnect').disabled"))
    check("silent device: no GSP32 seen, so no Set Up Wi-Fi in the row", not shown(pg, "#wifi-setup"))
    check("Flasher Version 105: no reset sequence, no esptool connect, no SYNC on GSP32's TinyUSB port", "[Resets tried:" not in out(pg) and not any(l.startswith(("reset ", "loader", "sync")) for l in log(pg)), log(pg))
    pg.screenshot(path=SHOTS + "/s3-guide.png")
    # BOOT + RST by hand: the TinyUSB port goes, the board now waits in download mode on its USB-JTAG port
    pg.evaluate("window.__downloadMode = true; window.__lose('base')"); pg.wait_for_timeout(500)
    check("old port gone: 'USB port changed' line, not the unplug one", "USB port changed" in out(pg) and "The device disconnected" not in out(pg), out(pg)[-300:])
    check("guide still there", shown(pg, "#usb-guide"))
    check("greyed buttons say to pick the port again", "Pick the port again" in pg.inner_text("#actions-note"), pg.inner_text("#actions-note"))
    n = len(log(pg))
    pg.evaluate("window.__pickQueue = ['dl']"); pg.click("#usb-guide-pick")
    check("picked again: device read", wait_text(pg, "Device: ESP32-S3", 15000), out(pg)[-400:])
    pg.wait_for_timeout(600)
    req = pg.evaluate("window.__requests")
    check("picker filtered to Espressif USB (0x303A)", req[-1] == json.dumps({"filters": [{"usbVendorId": 0x303a}]}).replace(" ", ""), req)
    after = since(pg, n)
    check("download mode checked with one SYNC on the new port", "sync dl" in after, after)
    check("read with no_reset (no reset sequence)", "main no_reset" in after and not any(l.startswith("reset ") for l in after), after)
    check("left in download mode (no RESET after reading)", "RESET" not in after, after)
    check("device state: Download Mode: Ready to Install", "Download Mode: Ready to Install" in pg.inner_text("#board-state"), pg.inner_text("#board-state"))
    check("guide folded away", not shown(pg, "#usb-guide"))
    check("device details read (flash, PSRAM)", "16 MB flash" in pg.inner_text("#board-details") and "8 MB PSRAM" in pg.inner_text("#board-details"), pg.inner_text("#board-details"))
    pg.screenshot(path=SHOTS + "/s3-download-mode.png")
    # Install: no reset into the bootloader again; the restart afterwards moves the board back to GSP32's port
    n = len(log(pg))
    # Flasher Version 105: the restart is the watchdog reset through the stub (a system reset: the board leaves
    #  download mode), and its USB-JTAG port goes
    pg.evaluate("""() => { window.__onWdt = () => { window.__lose('dl'); window.__boot(); }; }""")
    install(pg)
    check("install finishes", wait_js(pg, "() => /Installed/.test(document.getElementById('board-status').innerText)", 20000), pg.inner_text("#board-status"))
    after = since(pg, n)
    regs = [l for l in after if l.startswith(("writeReg", "readReg"))]
    check("Flasher Version 105: watchdogs off after the connect (esptool's S3 USB-JTAG disable_watchdogs)", regs[:7] == [
        "writeReg 0x600080b0=0x50d83aa1", "writeReg 0x60008098=0x0", "writeReg 0x600080b0=0x0", "readReg 0x600080b4",
        "writeReg 0x600080b8=0x8f1d312a", "writeReg 0x600080b4=0x80000000", "writeReg 0x600080b8=0x0"] and "writeReg 0x600080b8=0x0" in regs, regs)
    tail = after[after.index("md5 verified"):] if "md5 verified" in after else after
    check("watchdog reset: FORCE_DOWNLOAD_BOOT cleared, then esptool's S3 RTC WDT writes", [l for l in tail if l.startswith("writeReg")] == [
        "writeReg 0x6000812c=0x0/0x1", "writeReg 0x600080b0=0x50d83aa1/0xffffffff", "writeReg 0x6000809c=0x7d0/0xffffffff",
        "writeReg 0x60008098=0xd0000102/0xffffffff", "writeReg 0x600080b0=0x0/0xffffffff"] or [l for l in tail if l.startswith("writeReg")] == [
        "writeReg 0x6000812c=0x0/0x1", "writeReg 0x600080b0=0x50d83aa1", "writeReg 0x6000809c=0x7d0", "writeReg 0x60008098=0xd0000102", "writeReg 0x600080b0=0x0"], [l for l in tail if l.startswith("writeReg")])
    check("no RTS restart after the watchdog reset", "RESET" not in (tail[:tail.index("LOSE dl")] if "LOSE dl" in tail else tail), tail)
    check("no Next step while GSP32 hasn't started", "Next:" not in pg.inner_text("#board-status"), pg.inner_text("#board-status"))
    check("install connects with no_reset too", "main no_reset" in after and not any(l.startswith("reset ") for l in after), after)
    check("written", any(l.startswith("write at") for l in after))
    check("restart moved the device: repick guide", wait_js(pg, "() => !document.getElementById('usb-guide').hidden", 5000))
    pg.wait_for_timeout(400)
    check("repick title: Pick the Port Again", pg.inner_text("#usb-guide-title").strip() == "Pick the Port Again", pg.inner_text("#usb-guide-title"))
    check("text says installed, pick it to set up Wi-Fi", "installed" in pg.inner_text("#usb-guide-text") and "Wi-Fi" in pg.inner_text("#usb-guide-text"), pg.inner_text("#usb-guide-text"))
    check("post-install repick offers Set Up Wi-Fi Instead", shown(pg, "#usb-guide-wifi") and pg.inner_text("#usb-guide-wifi").strip() == "Set Up Wi-Fi Instead")
    check("Installed status kept", "Installed" in pg.inner_text("#board-status"))
    reqs = len(pg.evaluate("window.__requests"))
    pg.evaluate("window.__arrive('base')"); pg.wait_for_timeout(800)
    # (the old port's esptool session is closed within 1 s once the watchdog reset took it away)
    back = wait_js(pg, "() => !document.getElementById('disconnect').disabled", 4000)
    check("allowed port back: taken without the picker", len(pg.evaluate("window.__requests")) == reqs and back)
    check("guide gone after reconnecting", not shown(pg, "#usb-guide"))
    pg.wait_for_timeout(600)  # the row folds open
    check("Set Up Wi-Fi offered (GSP32 just installed)", shown(pg, "#wifi-setup"))
    check("Next step once GSP32's port is back", "Next: click Set Up Wi-Fi" in pg.inner_text("#board-status"), pg.inner_text("#board-status"))
    pg.wait_for_timeout(4500)
    n = len(log(pg))
    pg.click("#wifi-setup")
    check("Wi-Fi networks listed", wait_js(pg, "() => document.getElementById('wifi-list').innerText.includes('HomeNet')", 15000), pg.inner_text("#wifi-status"))
    check("quiet fresh install taken as listening (no restart for Wi-Fi)", not any(l in ("RESET", "silent reset") for l in since(pg, n)), since(pg, n))
    check("no page errors (flow)", not errors, errors)
    pg.close()

    # 2. A board whose reset would move it to a new port (MicroPython's own DTR/RTS reboot into download mode):
    #    Flasher Version 105 sends no reset to GSP32's TinyUSB port, so it stays put; the guide at once, and an allowed
    #    port that comes back (BOOT+RST by hand) is used
    pg, errors = page(b, "window.__resetWorks = 'none';")
    pg.wait_for_timeout(100)
    t0 = time.time(); pg.evaluate("window.__reenumArm = true"); pg.click("#connect")
    ok = wait_js(pg, "() => !document.getElementById('usb-guide').hidden", 15000); dt = time.time() - t0
    check("guide within a second or two", ok and dt < 3, round(dt, 1))
    check("guide title (boot)", pg.inner_text("#usb-guide-title").strip() == TITLE)
    check("no reset sent, so the port never moved", "LOSE base" not in log(pg) and "USB port changed" not in out(pg), log(pg)[-8:])
    pg.evaluate("window.__lose('base')"); pg.wait_for_timeout(300)
    pg.wait_for_timeout(300)
    reqs = len(pg.evaluate("window.__requests"))
    pg.evaluate("window.__downloadMode = true; window.__arrive('dl')")
    check("came back in download mode: read", wait_text(pg, "Device: ESP32-S3", 15000), out(pg)[-300:])
    check("without the picker", len(pg.evaluate("window.__requests")) == reqs)
    pg.wait_for_timeout(500)
    check("Download Mode: Ready to Install", "Download Mode" in pg.inner_text("#board-state"))
    check("no page errors (re-enumeration)", not errors, errors)
    pg.close()

    # 3. Install straight away on the TinyUSB port: no second connect try, the guide (resume install); after BOOT+RST
    #    and the pick the install goes on by itself
    pg, errors = page(b, "window.__resetWorks = 'none'; window.__silentReset = true;")
    pg.click("#connect"); wait_js(pg, "() => !document.getElementById('usb-guide').hidden", 20000); pg.wait_for_timeout(600)
    pg.evaluate("window.gsp32.appendConsole('[mark]\\n')")
    install(pg)
    check("install: guide again, error says BOOT/RST", wait_js(pg, "() => /Hold BOOT, tap RST/.test(document.getElementById('board-status').innerText)", 20000), pg.inner_text("#board-status"))
    tail = out(pg).split("[mark]")[-1]
    check("no 'trying once more' on native USB", "trying once more" not in tail, tail[-400:])
    check("no Set Up Wi-Fi Instead while installing", not shown(pg, "#usb-guide-wifi"))
    pg.evaluate("window.__downloadMode = true; window.__lose('base')"); pg.wait_for_timeout(400)
    pg.evaluate("window.__pickQueue = ['dl']"); pg.click("#usb-guide-pick")
    check("install goes on after the pick", wait_js(pg, "() => /Installed/.test(document.getElementById('board-status').innerText)", 25000), pg.inner_text("#board-status"))
    check("no page errors (install resume)", not errors, errors)
    pg.close()

    # 4. Picked again without BOOT+RST (still running): no download mode answer, no reset, the guide stays
    pg, errors = page(b, "window.__resetWorks = 'none'; window.__silentReset = true;")
    pg.click("#connect"); wait_js(pg, "() => !document.getElementById('usb-guide').hidden", 20000); pg.wait_for_timeout(600)
    pg.evaluate("window.__lose('base')"); pg.wait_for_timeout(300)
    n = len(log(pg))
    pg.evaluate("window.__pickQueue = ['base']"); pg.click("#usb-guide-pick"); pg.wait_for_timeout(1500)
    after = since(pg, n)
    check("not in download mode: says so", "Not in download mode yet" in out(pg), out(pg)[-300:])
    check("no esptool connect, no reset", not any(l.startswith("loader") or l == "RESET" for l in after), after)
    check("no SYNC sent to GSP32's own TinyUSB port", not any(l.startswith("sync") for l in after), after)
    check("guide shown again", shown(pg, "#usb-guide") and pg.inner_text("#usb-guide-title").strip() == TITLE)
    # The picker closed: nothing happens, the guide stays
    pg.evaluate("window.__pickQueue = ['cancel']"); pg.click("#usb-guide-pick"); pg.wait_for_timeout(400)
    check("picker closed: guide stays, no error", shown(pg, "#usb-guide") and "Something went wrong" not in out(pg))
    check("no page errors (not ready)", not errors, errors)
    pg.close()

    # 5. Set Up Wi-Fi Instead (no board info needed) on a silent board: the page's restart does nothing, the status
    #    says to tap RST; RST moves it to a new port, which comes back (allowed already); Wi-Fi goes on
    pg, errors = page(b, "window.__resetWorks = 'none'; window.__silentReset = true;")
    pg.click("#connect"); wait_js(pg, "() => !document.getElementById('usb-guide').hidden", 20000); pg.wait_for_timeout(600)
    pg.click("#usb-guide-wifi"); pg.wait_for_timeout(800)
    check("Wi-Fi instead: guide folded away", not shown(pg, "#usb-guide"))
    check("Wi-Fi status says to tap RST if nothing happens", "tap RST" in pg.inner_text("#board-status"), pg.inner_text("#board-status"))
    pg.wait_for_timeout(1500)
    pg.evaluate("window.__lose('base')")
    check("RST moved it: repick guide", wait_js(pg, "() => !document.getElementById('usb-guide').hidden && document.getElementById('usb-guide-title').innerText.trim() === 'Pick the Port Again'", 8000), pg.inner_text("#usb-guide-title"))
    pg.wait_for_timeout(300)
    pg.evaluate("window.__arrive('base')"); pg.wait_for_timeout(300)
    # The board's boot after RST, on the port that came back
    pg.evaluate("(async () => { window.__silentReset = false; await window.__port.setSignals({ dataTerminalReady: false, requestToSend: true }); await window.__port.setSignals({ dataTerminalReady: false, requestToSend: false }); })()")
    check("Wi-Fi without device info: networks listed", wait_js(pg, "() => document.getElementById('wifi-list').innerText.includes('HomeNet')", 20000), pg.inner_text("#wifi-status"))
    check("no page errors (Wi-Fi instead)", not errors, errors)
    pg.close()
    # 5b. The page's restart does work but moves the board to a new port: the guide, the port back, Wi-Fi goes on
    pg, errors = page(b, "window.__resetWorks = 'none';")
    pg.click("#connect"); wait_js(pg, "() => !document.getElementById('usb-guide').hidden", 20000); pg.wait_for_timeout(600)
    # GSP32 prints its lines (it just booted: the page sends no reset to this port since Flasher Version 105)
    pg.evaluate("(async () => { await window.__port.setSignals({ dataTerminalReady: false, requestToSend: true }); await window.__port.setSignals({ dataTerminalReady: false, requestToSend: false }); })()"); pg.wait_for_timeout(1200)
    check("GSP32 seen (its boot lines): Set Up Wi-Fi in the row, no Instead", shown(pg, "#wifi-setup") and not shown(pg, "#usb-guide-wifi"))
    # GSP32 on Wi-Fi stopped listening after its first 30 s: Set Up Wi-Fi restarts it, and the restart moves the port
    pg.evaluate("window.__stopListening()"); pg.wait_for_timeout(200)
    pg.evaluate("window.__reenumOnRun = true"); pg.click("#wifi-setup")
    check("Wi-Fi restart moved it: repick guide", wait_js(pg, "() => !document.getElementById('usb-guide').hidden && document.getElementById('usb-guide-title').innerText.trim() === 'Pick the Port Again'", 8000), pg.inner_text("#usb-guide-title"))
    pg.wait_for_timeout(300)
    pg.evaluate("window.__arrive('base')"); pg.wait_for_timeout(300)
    pg.evaluate("window.__listen = true; window.__say('Server listening on port 80\\r\\nGSP32 Improv Listening\\r\\n')")
    check("Wi-Fi goes on after the port is back", wait_js(pg, "() => document.getElementById('wifi-list').innerText.includes('HomeNet')", 20000), pg.inner_text("#wifi-status"))
    check("no page errors (Wi-Fi moved)", not errors, errors)
    pg.close()

    # 6. Picked by hand in download mode (Gene's BOOT+RST first, Get Started, COM10): one SYNC, read without a reset
    pg, errors = page(b, "window.__downloadMode = true; window.__usb = { usbVendorId: 0x303a, usbProductId: 0x1001 };")
    n = len(log(pg)); pg.click("#connect")
    check("USB-JTAG port in download mode: read", wait_text(pg, "Device: ESP32-S3", 15000), out(pg)[-300:])
    pg.wait_for_timeout(500)
    after = since(pg, n)
    check("SYNC answered: no_reset, no RESET after", "sync base" in after and "main no_reset" in after and "RESET" not in after, after)
    check("no guide", not shown(pg, "#usb-guide"))
    # Flasher Version 105: the install finds the stub the board check left running and takes it for the stub, so the
    #  chip erase runs (esptool-js 0.5.7 alone skipped it: the very fast first install with MD5 mismatches)
    n = len(log(pg))
    install(pg)
    check("install from download mode finishes", wait_js(pg, "() => /Installed/.test(document.getElementById('board-status').innerText)", 20000), pg.inner_text("#board-status"))
    after = since(pg, n)
    check("the running stub is used as the stub (console line)", "[The flasher stub was still running: using it]" in out(pg), out(pg)[-400:])
    check("the chip erase runs (not skipped)", "erase all" in after and not any(l.startswith("erase skipped") for l in after), after)
    # Flasher Version 105: nothing restarted the board (still in download mode, still answering SYNC): the guide says
    #  to tap RST; no Next step yet. RST: the port goes, GSP32's port comes, the Next step then
    check("still in download mode: Tap RST guide", wait_js(pg, "() => !document.getElementById('usb-guide').hidden", 5000))
    pg.wait_for_timeout(400)
    check("rst guide title (Title Case)", pg.inner_text("#usb-guide-title").strip() == "Tap RST to Start GSP32", pg.inner_text("#usb-guide-title"))
    check("rst guide text short, says download mode", "download mode" in pg.inner_text("#usb-guide-text") and len(pg.inner_text("#usb-guide-text")) <= 130, pg.inner_text("#usb-guide-text"))
    check("rst guide: Pick the Port Again and Set Up Wi-Fi Instead", shown(pg, "#usb-guide-pick") and shown(pg, "#usb-guide-wifi") and pg.inner_text("#usb-guide-wifi").strip() == "Set Up Wi-Fi Instead")
    check("console: still in download mode line", "[The device is still in download mode. Tap RST (not BOOT)" in out(pg), out(pg)[-400:])
    check("no Next step in download mode", "Next:" not in pg.inner_text("#board-status"), pg.inner_text("#board-status"))
    pg.screenshot(path=SHOTS + "/s3-tap-rst.png")
    pg.evaluate("window.__downloadMode = false; window.__lose('base')"); pg.wait_for_timeout(300)
    check("RST: 'USB port changed', guide stays", "USB port changed" in out(pg) and shown(pg, "#usb-guide"), out(pg)[-300:])
    pg.evaluate("window.__arrive('base')"); pg.wait_for_timeout(900)
    check("GSP32's port back: guide gone, Next step shown", not shown(pg, "#usb-guide") and "Next: click Set Up Wi-Fi" in pg.inner_text("#board-status"), pg.inner_text("#board-status"))
    check("no page errors (manual download mode)", not errors, errors)
    pg.close()
    # 6c. The stub never answers the watchdog writes: time-limited, then the usual RTS restart
    pg, errors = page(b, "window.__downloadMode = true; window.__usb = { usbVendorId: 0x303a, usbProductId: 0x1001 };")
    pg.click("#connect"); wait_text(pg, "Device: ESP32-S3", 15000); pg.wait_for_timeout(500)
    pg.evaluate("window.__wdtSilent = true"); n = len(log(pg)); install(pg)
    check("silent stub: install still finishes", wait_js(pg, "() => /Installed/.test(document.getElementById('board-status').innerText)", 25000), pg.inner_text("#board-status"))
    after = since(pg, n)
    check("silent stub: the watchdogs line (connect goes on)", "[Could not turn off the device's watchdogs" in out(pg), out(pg)[-600:])
    check("silent stub: the watchdog line, then the RTS restart", "[The watchdog reset did not answer" in out(pg) and "RESET" in after, out(pg)[-400:])
    check("no page errors (silent stub)", not errors, errors)
    pg.close()
    # 6b. A USB-JTAG port running firmware (no SYNC answer): the usual reset, USB-JTAG first, and the board restarted
    pg, errors = page(b, "window.__usb = { usbVendorId: 0x303a, usbProductId: 0x1001 }; window.__resetWorks = 'usbJtag';")
    n = len(log(pg)); pg.click("#connect")
    check("USB-JTAG running: read with the reset", wait_text(pg, "Device: ESP32-S3", 15000), out(pg)[-300:])
    pg.wait_for_timeout(800)
    after = since(pg, n)
    check("reset usbJtag, then restarted (RESET)", "reset usbJtag" in after and "main no_reset" not in after and "RESET" in after, after)
    check("no guide (usbJtag)", not shown(pg, "#usb-guide"))
    pg.close()

    # 7. Other bridges unchanged: a CP2102 board that can't be reset keeps the old line and no guide
    pg, errors = page(b, "window.__usb = { usbVendorId: 0x10c4, usbProductId: 0xea60 }; window.__chip = 'ESP32-D0WD-V3 (revision v3.1)'; window.__features = undefined; window.__resetWorks = 'none';")
    # Flasher Version 115.10 (Gene's ESP32): a classic bridge is not read on a plain connect (the board keeps running)
    pg.click("#connect"); wait_text(pg, "keeps running", 20000); pg.wait_for_timeout(500)
    check("CP2102: connected without a board-info read, no guide", "keeps running" in out(pg) and "Reading device info" not in out(pg) and not shown(pg, "#usb-guide"), out(pg)[-300:])
    pg.evaluate("window.__lose('base')"); pg.wait_for_timeout(300)
    check("CP2102 unplug: the plain disconnect line", "The device disconnected" in out(pg) and not shown(pg, "#usb-guide"))
    check("no page errors (CP2102)", not errors, errors)
    pg.close()

    # 8. Phone width: the guide fits, its buttons wrap inside the card
    pg, errors = page(b, "window.__resetWorks = 'none'; window.__silentReset = true;", w=375)
    pg.click("#connect"); wait_js(pg, "() => !document.getElementById('usb-guide').hidden", 20000); pg.wait_for_timeout(600)
    g, c = pg.locator("#usb-guide").bounding_box(), pg.locator("#console").bounding_box()
    check("phone: guide inside the card", g and c and g["x"] >= c["x"] and g["x"] + g["width"] <= c["x"] + c["width"] + 1, (g, c))
    check("phone: no sideways scroll", pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
    pg.screenshot(path=SHOTS + "/s3-guide-phone.png")
    pg.close(); b.close()
print("fails", fails); sys.exit(1 if fails else 0)
