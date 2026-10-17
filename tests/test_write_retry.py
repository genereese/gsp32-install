# Fix (write retries, Gene's new board on Linux): the MD5 check caught a bad write, and the rewrite then broke on
#  "Invalid head of packet (0xff): Possible serial noise or corruption", which ended the install. Now noise and MD5
#  failures are written again from a fresh connect, up to 3 writes in all; the last failure is said plainly (raw
#  text in the console). And a boot-looping board's output stays folded until esptool takes the port
import os, http.server, threading, functools
from playwright.sync_api import sync_playwright
here = os.path.dirname(os.path.abspath(__file__)); site = os.path.dirname(here)
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8804), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)
GARBLED = "The connection to the board kept getting garbled. Try a different (short) USB cable, plugged straight into the computer."
RAW = "Invalid head of packet (0xff): Possible serial noise or corruption."
SLOW_MANIFEST = "const f0 = window.fetch; window.fetch = (u, o) => (window.__slowManifest && /manifest/.test(String(u))) ? new Promise(r => setTimeout(r, 1500)).then(() => f0(u, o)) : f0(u, o);"
def page(b, init=""):
    pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.add_init_script(path=here + "/mock.js")
    pg.add_init_script("window.__ver = '47';" + SLOW_MANIFEST + init)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.route("**/gsp32-telemetry.genereese.workers.dev/**", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true}'))
    errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:8804/index.html"); pg.wait_for_timeout(300)
    return pg, errors
def install(pg, during=None):
    pg.click("#connect"); pg.wait_for_timeout(1500)
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install")
    if during: during(pg)
    pg.wait_for_function("document.getElementById('wizard').hidden || document.body.innerText.includes('did not finish')", timeout=40000)
    pg.wait_for_timeout(300)
    return [l for l in pg.evaluate("window.__log") if isinstance(l, str)]
def out(pg): return pg.inner_text("#console-out")
def installed(pg): return "Installed" in pg.inner_text("#board-status")
with sync_playwright() as p:
    b = p.chromium.launch()
    # 1. Noise breaks two writes: each is reconnected (fresh esptool session) and written again; the third verifies
    pg, errors = page(b, "window.__noiseWrites = 2;")
    log = install(pg)
    check("noise twice: 3 writes, the last verified", log.count("write noise") == 2 and "md5 verified" in log and installed(pg), str([l for l in log if l.startswith(("write", "md5"))]))
    check("noise twice: a fresh connect before each rewrite", log.count("esptool got reader true") >= 4, str(log.count("esptool got reader true")))
    check("noise twice: the console names each retry", "writing it again (2 of 3)" in out(pg) and "writing it again (3 of 3)" in out(pg))
    check("no page errors (1)", not errors, str(errors)); pg.close()
    # 2. MD5 mismatch, then noise, then good: within the 3 attempts
    pg, errors = page(b, "window.__writePlan = ['md5', 'noise', 'ok'];")
    log = install(pg)
    check("mismatch, noise, then verified: Installed", "md5 mismatch" in log and "write noise" in log and "md5 verified" in log and installed(pg), str([l for l in log if l.startswith(("write", "md5"))]))
    pg.close()
    # 3. Noise every time: a plain message, the raw esptool text only in the console, not Installed
    pg, errors = page(b, "window.__noiseWrites = 9; window.__other = true;")
    log = install(pg)
    err = pg.evaluate("document.getElementById('error-text').textContent")
    st = pg.inner_text("#board-status") if pg.is_visible("#board-status") else ""
    check("noise 3 times: stops after 3 writes", log.count("write noise") == 3, str(log.count("write noise")))
    check("noise 3 times: plain message", GARBLED in err and "Invalid head" not in err, err)
    check("noise 3 times: no raw text in the status either", "Invalid head" not in st, st)
    check("noise 3 times: raw text kept in the console", RAW in out(pg) and "Giving up" in out(pg))
    check("noise 3 times: not Installed", not installed(pg))
    check("noise 3 times: Recover/Install GSP32 after closing", (pg.click("[data-step=error] [data-action=close]") or pg.wait_for_timeout(600) or True) and pg.inner_text("#install-btn") == "Recover/Install GSP32", pg.inner_text("#install-btn"))
    check("no page errors (3)", not errors, str(errors)); pg.close()
    # 4. A boot-looping board: after [Installing ...] its restart lines stay folded until esptool takes the port
    LOOP = "rst:0xc (SW_CPU_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)\r\nconfigsip: 0, SPIWP:0xee\r\nmode:DIO, clock div:2\r\nload:0x3fff0030,len:1184\r\nentry 0x400806ac\r\n"
    pg, errors = page(b, "window.__other = true;")
    pg.click("#connect"); pg.wait_for_timeout(1500)
    for _ in range(30): pg.evaluate("t => window.__say(t)", LOOP)
    pg.wait_for_timeout(300)
    check("boot loop folded before the install", pg.inner_text("#install-btn") == "Recover/Install GSP32" and "keeps restarting" in out(pg))
    pg.evaluate("window.__slowManifest = true")
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(200)
    for _ in range(20): pg.evaluate("t => window.__say(t)", LOOP); pg.wait_for_timeout(30)
    text = out(pg)
    after = text.split("[Installing")[-1]
    check("install getting ready: restart lines still folded", "[Installing" in text and "rst:0xc" not in after and "entry 0x400806ac" not in after, after[:300])
    check("install getting ready: the fold line is still last", "keeps restarting" in text.strip().splitlines()[-1], text.strip().splitlines()[-1])
    pg.wait_for_function("document.getElementById('wizard').hidden || document.body.innerText.includes('did not finish')", timeout=40000); pg.wait_for_timeout(300)
    text = out(pg); after = text.split("[Installing")[-1]
    check("esptool took the port: the fold ends with its count, before esptool's lines", " lines of restart output were hidden]" in after and after.index(" lines of restart output were hidden]") < after.index("[esptool]"), after[:300])
    check("no page errors (4)", not errors, str(errors)); pg.close()
    b.close()
print("FAILURES:", fails)
raise SystemExit(1 if fails else 0)
