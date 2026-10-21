# Flasher Version 105 (S3 web flash fix): Chromium kills the tab (RESULT_CODE_KILLED_BAD_MESSAGE) when the page asks for
#  port.readable after a close() that threw because the writable was still locked: the readable was already cancelled
#  without a flush, Chromium's device side still holds the old read pipe, and a new StartReading is a "bad message". The
#  mock port here behaves like Chromium's (close() order, locked streams, a write that never ends once the device stops
#  taking data, a close that never ends with a write in flight) and counts a new readable asked for in that state as
#  the crash. Checked: the stalled connect (esptool-js going on in the background), a write that stalls mid-install, and
#  Get Started on the stuck port: never the crash, writes bounded, esptool-js stopped, "Unplug and Replug the Board"
import os, http.server, threading, functools, time
from playwright.sync_api import sync_playwright
here = os.path.dirname(os.path.abspath(__file__)); site = os.path.dirname(here)
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8841), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
SHOTS = os.environ.get("SHOTS", "/tmp/flasher-shots"); os.makedirs(SHOTS, exist_ok=True)
APP = os.environ.get("APP_JS")  # another app.js to check against (the crash itself: the Version 104 page)
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, "" if ok else str(extra)[:600])
STUCK = "The USB connection got stuck. Unplug and replug the board, then click Get Started."
# Chromium-like port on top of mock.js's board
CHROMIUM = """(() => {
  const p = window.__port;
  const baseOpen = p.open.bind(p), baseClose = p.close.bind(p), baseSignals = p.setSignals.bind(p);
  const desc = Object.getOwnPropertyDescriptor(p, "readable");
  let open = false, closing = false, stale = false, last = null, inflight = 0;
  window.__badMessage = 0; window.__readableGets = 0; window.__writes = 0; window.__writeBytes = 0; window.__closes = [];
  Object.defineProperty(p, "readable", { configurable: true, get() {
    window.__readableGets++;
    if (!open || closing) return null;
    const r = desc.get.call(p);
    // A new readable (a new StartReading) while the device side still holds the old pipe: Chromium kills the tab
    if (r !== last && stale) { window.__badMessage++; window.__log.push("BAD MESSAGE"); }
    last = r;
    return r;
  } });
  p.open = async function (o) {
    if (open || closing) throw new DOMException("The port is already open.", "InvalidStateError");
    await baseOpen(o); open = true; last = null; stale = false; inflight = 0;
    const inner = p.writable;
    p.writable = new WritableStream({ write: async (c) => {
      window.__writes++; window.__writeBytes += c.length;
      if (window.__stallAfter != null && window.__writeBytes > window.__stallAfter) { inflight++; window.__log.push("write stalls"); return new Promise(() => {}); }
      const w = inner.getWriter(); try { await w.write(c); } finally { w.releaseLock(); }
    } });
  };
  p.setSignals = async function (s) { if (!open || closing) throw new DOMException("The port is closed.", "InvalidStateError"); return baseSignals(s); };
  // SerialPort::close(): the readable is cancelled first (while closing: no flush, the device keeps its pipe), then the
  //  writable aborted; a locked one throws and the close is dropped (AbortClose) with the port still open
  p.close = async function () {
    window.__closes.push(Date.now());
    if (!open) throw new DOMException("The port is already closed.", "InvalidStateError");
    if (closing) throw new DOMException("A call to close() is already in progress.", "InvalidStateError");
    const r = last;
    if (r && r.locked) throw new TypeError("Cannot cancel a locked stream");
    closing = true;
    if (r) { stale = true; r.cancel().catch(() => {}); last = null; }
    const w = p.writable;
    if (w && w.locked) { closing = false; window.__log.push("ABORT CLOSE"); throw new TypeError("Cannot abort a locked stream"); }
    if (inflight > 0) { window.__log.push("close waits on a stuck write"); await new Promise(() => {}); }
    await baseClose(); open = false; closing = false; stale = false; last = null;
  };
})();"""
def page(b, init=""):
    pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.add_init_script(path=here + "/mock.js")
    pg.add_init_script("window.__ver = '106'; window.__ets = true;" + init)
    pg.add_init_script(CHROMIUM)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    if (APP): pg.route("**/app.js*", lambda r: r.fulfill(path=APP, content_type="text/javascript"))
    pg.route("**/gsp32-telemetry.genereese.workers.dev/**", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true}'))
    errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:8841/index.html"); pg.wait_for_timeout(300)
    return pg, errors
def out(pg): return pg.inner_text("#console-out")
def js(pg, expr): return pg.evaluate(expr)
def wait_js(pg, expr, ms):
    try: pg.wait_for_function(expr, timeout=ms); return True
    except Exception: return False
def start_visible(pg):
    return js(pg, "(() => { const b = document.getElementById('connect'); return !b.hidden && !b.disabled && b.offsetParent !== null; })()")
with sync_playwright() as p:
    b = p.chromium.launch()

    # 1. Reading board info from a board that never answers and stops taking data after a few SYNCs (GSP32's TinyUSB
    #    port with its input full): the connect runs out of time while esptool-js still writes in the background
    pg, errors = page(b, "window.__syncWrites = true; window.__stallAfter = 300;")
    t0 = time.time(); pg.click("#connect")
    done = wait_js(pg, "() => document.getElementById('console-out').innerText.includes('Could not read the board yet') || document.getElementById('console-out').innerText.includes('got stuck') || window.__badMessage > 0", 30000)
    check("1. the connect ends within its time limit", done and time.time() - t0 < 20, round(time.time() - t0, 1))
    stop_writes = js(pg, "window.__writes"); stop_log = len(js(pg, "window.__log"))
    wait_js(pg, "() => document.getElementById('console-out').innerText.includes('stuck') || window.__badMessage > 0", 12000)
    pg.wait_for_timeout(9000)  # esptool-js's background loop would go on for about 14 s
    log = js(pg, "window.__log")
    check("1. never the crash (no new readable while Chromium still holds the old pipe)", js(pg, "window.__badMessage") == 0, [l for l in log if "BAD" in l or "ABORT" in l])
    check("1. the stalled write was bounded (no close dropped with the writable locked)", "ABORT CLOSE" not in log, log[-12:])
    check("1. esptool-js stopped: nothing written after the time limit", js(pg, "window.__writes") == stop_writes, (stop_writes, js(pg, "window.__writes")))
    check("1. esptool-js stopped: its writes fail at once", not [l for l in log[stop_log:] if l == "sync write"], log[stop_log:][-6:])
    check("1. the stuck port: Unplug and Replug, once", out(pg).count(STUCK) == 1, out(pg)[-400:])
    check("1. status says Unplug and Replug the Board", "Unplug and Replug the Board" in pg.inner_text("#board-status"), pg.inner_text("#board-status"))
    check("1. Get Started is back", start_visible(pg))
    check("1. no page errors", not errors, errors)
    gets = js(pg, "window.__readableGets")
    # 2. Get Started again picks the same (stuck) port: a clear line, the port is never touched
    pg.click("#connect"); pg.wait_for_timeout(1500)
    check("2. the stuck port is refused with the unplug line", STUCK in pg.inner_text("#start-error"), pg.inner_text("#start-error"))
    check("2. its readable is never asked for again", js(pg, "window.__readableGets") == gets, (gets, js(pg, "window.__readableGets")))
    check("2. still no crash, no page errors", js(pg, "window.__badMessage") == 0 and not errors, errors)
    pg.screenshot(path=SHOTS + "/crashproof-stuck.png"); pg.close()

    # 3. A board that stops taking data partway through the install's write: the write runs out of time and is aborted,
    #    the reconnect finds the port stuck, the install stops with the unplug line (never the crash)
    pg, errors = page(b, "window.__stallInWrite = true;")
    pg.click("#connect"); pg.wait_for_timeout(4500)
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install")
    wait_js(pg, "() => document.getElementById('console-out').innerText.includes('stuck') || window.__badMessage > 0", 30000)
    pg.wait_for_timeout(1500)
    log = js(pg, "window.__log")
    check("3. the write stalled", "write stalls" in log, log[-10:])
    check("3. the write ran out of time (bounded)", "Writing to the board took longer than" in out(pg), out(pg)[-500:])
    check("3. never the crash", js(pg, "window.__badMessage") == 0 and "ABORT CLOSE" not in log, log[-10:])
    check("3. the install stops with the unplug line", STUCK in out(pg) and "Installed" not in pg.inner_text("#board-status"), out(pg)[-300:])
    check("3. Get Started is back", start_visible(pg))
    check("3. no page errors", not errors, errors)
    pg.close()

    # 4. A short stall (the board catches up): the write finishes, the install goes on as before
    pg, errors = page(b, "")
    pg.click("#connect"); pg.wait_for_timeout(4500)
    pg.evaluate("window.__stallAfter = null")
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install")
    ok = wait_js(pg, "() => document.getElementById('board-status').innerText.includes('Installed')", 30000)
    check("4. no stall: installs as before", ok and js(pg, "window.__badMessage") == 0, out(pg)[-300:])
    check("4. no stuck line", STUCK not in out(pg))
    check("4. no page errors", not errors, errors)
    pg.close()
    b.close()
print("FAILURES:", fails)
raise SystemExit(1 if fails else 0)
