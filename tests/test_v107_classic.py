# Flasher Version 107: the S3 fixes of Flasher 105 run only on native USB (Espressif's VID 0x303A). On a classic board
#  (a USB-UART bridge: CP2102, CH340) the page must do exactly what Flasher 104 did. Checked with the REAL vendored
#  esptool-js 0.5.7 (not the fake) against tests/espemu.js, an ESP32 ROM + flasher stub behind a Chromium-like port that
#  records every port call (open, close, signals, readers, writers, each write's size and hash). For each scenario the
#  Flasher 104 page (git f243ed2) and this page run the same seed; their traces and console text must be identical:
#  a clean install (two seeds, two read chunkings), and faults on the line during the write: a flipped byte (MD5
#  mismatch, then the retry), a stray 0xff byte, a serial BreakError, a lost reply, a write that takes 9 s. Then the
#  gate itself: the same 9 s write on a 0x303A port is bounded and aborted (Flasher 105's fix), on a classic port not.
#  Small image (the first 512 KB of the ESP32 build) to keep it short. Faults land in the first install attempt.
#  Flasher Version 115.10 (Gene's ESP32): the one wanted change on a classic port is the connect: no board-info probe
#  and no DTR/RTS (a running board is not restarted). So the traces and console text are compared from the Install
#  click on, and the connect itself is checked on its own (no port signals, no reset)
import os, re, json, subprocess, http.server, threading, functools, socket, tempfile, time
from playwright.sync_api import sync_playwright
here = os.path.dirname(os.path.abspath(__file__)); site = os.path.dirname(here)
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, "" if ok else str(extra)[:900])
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
s = socket.socket(); s.bind(("127.0.0.1", 0)); PORT = s.getsockname()[1]; s.close()
srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
APP104 = os.path.join(tempfile.gettempdir(), "gsp32-flasher-app104-%d.js" % os.getpid())
open(APP104, "wb").write(subprocess.run(["git", "-C", site, "show", "f243ed2:app.js"], capture_output=True, check=True).stdout)
APP_NOW = os.path.join(site, "app.js")
IMAGE = open(os.path.join(site, "firmware", "gsp32-esp32.bin"), "rb").read()[:512 * 1024]
CLASSIC, NATIVE = (0x10c4, 0xea60), (0x303a, 0x1001)

# Static: every function the S3 fixes changed on a classic path is kept twice, <name>Native and <name>Classic, and
#  <name> picks one by nativeUsb(); each Classic copy must be Flasher 104's function, character for character
def grab(src, name):
    m = re.search(r'^(?:async )?function ' + name + r'\(', src, re.M)
    if not m: return None
    st = m.start(); return src[st:src.index("\n}\n", st) + 3]
s104, now = open(APP104).read(), open(APP_NOW).read()
pairs = re.findall(r'^(?:async )?function (\w+)Classic\(', now, re.M)
check("functions kept twice (Native/Classic): %d" % len(pairs), len(pairs) >= 16, pairs)
for n in pairs:
    same = grab(now, n + "Classic").replace("function " + n + "Classic(", "function " + n + "(", 1) == grab(s104, n)
    disp = grab(now, n)
    check(n + ": the Classic copy is Flasher 104's verbatim, the dispatcher picks it off native USB",
          same and re.search(r"return nativeUsb\(\w+\) \? " + n + r"Native\(.*\) : " + n + r"Classic\(", disp) is not None, disp)

def run(b, app, seed=1, chunk=64, faults=None, usb=CLASSIC):
    pg = b.new_page(viewport={"width": 1100, "height": 900})
    pg.add_init_script("window.__emu = {seed: %d, chunk: %d, faults: %s}; window.__usb = {usbVendorId: %d, usbProductId: %d};" % (seed, chunk, json.dumps(faults or {}), usb[0], usb[1]))
    pg.add_init_script(path=os.path.join(here, "espemu.js"))
    pg.route("**/app.js*", lambda r: r.fulfill(path=app, content_type="text/javascript"))
    pg.route("**/firmware/gsp32-esp32.bin*", lambda r: r.fulfill(body=IMAGE, content_type="application/octet-stream"))
    pg.route("**/gsp32-telemetry.genereese.workers.dev/**", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true}'))
    errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:%d/index.html" % PORT); pg.wait_for_timeout(400)
    pg.click("#connect")
    try: pg.wait_for_function("() => /Board:|Could not/.test(document.getElementById('console-out').innerText)", timeout=25000)
    except Exception: pass
    pg.wait_for_timeout(1200)
    at = pg.evaluate("window.__trace.length")
    connect_trace = pg.evaluate("window.__trace.slice()")
    try:
        pg.click("#install-btn", timeout=5000); pg.check("#erase-ok"); pg.click("#start-install", timeout=5000)
        pg.wait_for_function("() => /Installed|did not finish/.test(document.getElementById('board-status').innerText)", timeout=120000)
    except Exception as e:
        errors.append("driver: " + str(e)[:200])
    pg.wait_for_timeout(2500)
    con = pg.inner_text("#console-out")
    out = {"console": con[con.rfind("[Installing"):] if "[Installing" in con else con, "status": pg.inner_text("#board-status"),
           "trace": renum(pg.evaluate("window.__trace")[at:]), "connect": connect_trace, "connect_console": con, "stats": pg.evaluate("window.__emuStats"), "errors": errors}
    pg.close()
    return out

def renum(trace):
    # 115.10: from the Install click on, stream and reader numbers count from where the connect left them: renumbered
    ids = {}
    return [re.sub(r"#(\d+)", lambda m: "#%d" % ids.setdefault(m.group(1), len(ids) + 1), str(t)) for t in trace]

def idle_pairs(trace):
    # 115.11 (Gene's ESP32 on COM4): the run state is two calls, RTS off then DTR off (Flasher 104: one call, which
    #  Chromium applies DTR first). Folded back into Flasher 104's one call so the rest of the trace still compares
    out, i = [], 0
    while i < len(trace):
        if 'signals {"requestToSend":false}' in str(trace[i]) and i + 1 < len(trace) and 'signals {"dataTerminalReady":false}' in str(trace[i + 1]):
            out.append(str(trace[i]).replace('{"requestToSend":false}', '{"dataTerminalReady":false,"requestToSend":false}')); i += 2
        else:
            out.append(trace[i]); i += 1
    return out

def norm(text):
    # Times differ run to run (erase/write seconds); nothing else may
    return re.sub(r"\d+(\.\d+)?(s| s| seconds)\b", "#s", text)

with sync_playwright() as p:
    b = p.chromium.launch()
    scenarios = [("clean install, seed 1", dict(seed=1)), ("clean install, seed 7, 32-byte reads", dict(seed=7, chunk=32)),
                 ("flipped byte in block 8 (MD5 mismatch, retry)", dict(faults={"corrupt": 8})),
                 ("stray 0xff before block 8's reply", dict(faults={"stray": 8})),
                 ("serial BreakError at block 8", dict(faults={"serialError": 8})),
                 ("block 8's reply lost", dict(faults={"dropReply": 8})),
                 ("the 8th big write takes 9 s", dict(faults={"slowWrite": 8, "slowMs": 9000}))]
    for name, kw in scenarios:
        old, new = run(b, APP104, **kw), run(b, APP_NOW, **kw)
        pairs = len(new["trace"]) - len(idle_pairs(new["trace"])); new["trace"] = idle_pairs(new["trace"])
        check(name + ": 115.11 run state set RTS off, then DTR off (%d times)" % pairs, pairs > 0, pairs)
        check(name + ": same port calls as Flasher 104 (%d)" % len(old["trace"]), old["trace"] == new["trace"],
              next(((i, a, c) for i, (a, c) in enumerate(zip(old["trace"], new["trace"])) if a != c), (len(old["trace"]), len(new["trace"]))))
        check(name + ": same console text", norm(old["console"]) == norm(new["console"]), (norm(old["console"])[-300:], norm(new["console"])[-300:]))
        check(name + ": same result (%s)" % old["status"].split("|")[0].strip()[:40], norm(old["status"]) == norm(new["status"]), (old["status"], new["status"]))
        check(name + ": no page errors", not old["errors"] and not new["errors"], (old["errors"], new["errors"]))
        if name.startswith("clean, seed 1") or name == "clean install, seed 1":
            sig = [t for t in new["connect"] if "ignal" in str(t)]
            check("115.10 connect: no DTR/RTS set, no board-info probe (the device keeps running)",
                  not sig and "Reading device info" not in new["connect_console"] and "keeps running" in new["connect_console"], (sig[:6], new["connect_console"][:300]))
        if name.startswith("clean"):
            check(name + ": installed and verified", "Installed" in new["status"] and "verified (MD5 matches)" in new["console"], new["status"])
    # The gate: 105's bounded write only on native USB
    slow = {"faults": {"slowWrite": 8, "slowMs": 9000}}
    native = run(b, APP_NOW, usb=NATIVE, **slow)
    check("0x303A port: the 9 s write is bounded and aborted (Flasher 105's fix runs)", "Writing to the device took longer than" in native["console"] and "writer.abort" in native["trace"], native["console"][-400:])
    classic = run(b, APP_NOW, **slow)
    check("classic port: the same write is waited for, as in 104 (no abort)", "took longer" not in classic["console"] and "writer.abort" not in classic["trace"] and "Installed" in classic["status"], classic["console"][-300:])
    b.close()
os.remove(APP104)
print("FAILURES:", fails)
raise SystemExit(1 if fails else 0)
