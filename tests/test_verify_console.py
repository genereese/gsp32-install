# Fix (verify + console flood, Gene's Linux laptop): an install "finished" but the board boot-looped
#  ("E esp_image: invalid segment length", "No bootable app partitions"), and the flood of restart output froze
#  Chromium. Now (a) every region is checked by MD5 after writing, a mismatch writes once more, and success is never
#  reported unverified; (b) the console paints at most once a frame, keeps 500 lines in the page and holds back a
#  boot loop's output; (c) those boot errors mean a broken install: Recover/Install GSP32
import os, http.server, threading, functools, hashlib, time
from playwright.sync_api import sync_playwright
here = os.path.dirname(os.path.abspath(__file__)); site = os.path.dirname(here)
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8799), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)
IMAGE_MD5 = hashlib.md5(open(os.path.join(site, "firmware/gsp32-esp32.bin"), "rb").read()).hexdigest()
LOOP = ("rst:0xc (SW_CPU_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)\r\nconfigsip: 0, SPIWP:0xee\r\n"
        "clk_drv:0x00,q_drv:0x00,d_drv:0x00,cs0_drv:0x00,hd_drv:0x00,wp_drv:0x00\r\nmode:DIO, clock div:2\r\n"
        "load:0x3fff0030,len:4888\r\nload:0x40078000,len:16516\r\nentry 0x40080570\r\n"
        "E (31) esp_image: invalid segment length 0xe0f6e781\r\nE (37) boot: Factory app partition is not bootable\r\n"
        "E (42) boot: No bootable app partitions in the partition table\r\n")
def page(b, init=""):
    pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.add_init_script(path=here + "/mock.js")
    pg.add_init_script("window.__ver = '47';" + init)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.route("**/gsp32-telemetry.genereese.workers.dev/**", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true}'))
    errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:8799/index.html"); pg.wait_for_timeout(300)
    return pg, errors
def install(pg):
    pg.click("#connect"); pg.wait_for_timeout(1500)
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install")
    pg.wait_for_function("document.getElementById('wizard').hidden || document.body.innerText.includes('did not finish')", timeout=40000)
    pg.wait_for_timeout(300)
    return [l for l in pg.evaluate("window.__log") if isinstance(l, str)]
def out(pg): return pg.inner_text("#console-out")
with sync_playwright() as p:
    b = p.chromium.launch()
    # (a) 1. A good write is checked: the app's MD5 is the image's, and only then Installed
    pg, errors = page(b)
    log = install(pg)
    check("MD5 passed to esptool-js is the image's", ("md5 " + IMAGE_MD5) in log, str([l for l in log if l.startswith("md5")]))
    check("verified, then Installed", "md5 verified" in log and "Installed" in pg.inner_text("#board-status"))
    check("console says verified", "verified (MD5 matches)" in out(pg))
    check("no page errors (a1)", not errors, str(errors)); pg.close()
    # (a) 2. One mismatch: written again, verified, Installed
    pg, errors = page(b, "window.__md5Bad = 1;")
    log = install(pg)
    check("mismatch once: written again", log.count("md5 mismatch") == 1 and len([l for l in log if l.startswith("files")]) == 2, str([l for l in log if l.startswith(("md5", "files"))]))
    check("mismatch once: then verified and Installed", log[-1:] and "md5 verified" in log and "Installed" in pg.inner_text("#board-status"))
    check("console names the MD5 retry", "did not match (MD5 check). Writing it again" in out(pg))
    pg.close()
    # (a) 3. Three mismatches (every attempt): never Installed; a clear error naming cable and port; Recover/Install offered
    pg, errors = page(b, "window.__md5Bad = 3; window.__other = true;")
    log = install(pg)
    body = pg.inner_text("body")
    check("three mismatches: not reported as installed", "Installed" not in pg.inner_text("#board-status") and "[Installed" not in out(pg))
    check("three mismatches: clear error (cable, port)", "did not match what was sent" in body and "cable" in body and "port" in body, pg.inner_text("#error-text") if pg.is_visible("#error-text") else "")
    note = pg.evaluate("JSON.parse(localStorage.getItem('gsp32.flash'))")
    check("three mismatches: the install note stays (device needs Recover)", bool(note) and note.get("writing") is True)
    pg.click("[data-step=error] [data-action=close]"); pg.wait_for_timeout(600)
    check("three mismatches: Recover/Install GSP32 offered", pg.inner_text("#install-btn") == "Recover/Install GSP32", pg.inner_text("#install-btn"))
    check("no page errors (a3)", not errors, str(errors)); pg.close()
    # (c) One boot with a corrupted app: broken install, Recover/Install GSP32
    pg, errors = page(b, "window.__other = true;")
    pg.click("#connect"); pg.wait_for_timeout(1500)
    pg.evaluate("t => window.__say(t)", LOOP.split("E (31)")[0] + "E (31) esp_image: invalid segment length 0xe0f6e781\r\n"); pg.wait_for_timeout(400)
    check("invalid segment length: Recover/Install GSP32", pg.inner_text("#install-btn") == "Recover/Install GSP32", pg.inner_text("#install-btn"))
    pg.close()
    for msg in ("E (37) boot: Factory app partition is not bootable", "E (42) boot: No bootable app partitions in the partition table"):
        pg, errors = page(b, "window.__other = true;")
        pg.click("#connect"); pg.wait_for_timeout(1500)
        pg.evaluate("t => window.__say(t)", msg + "\r\n"); pg.wait_for_timeout(400)
        check(msg.split(": ")[1][:30] + ": Recover/Install GSP32", pg.inner_text("#install-btn") == "Recover/Install GSP32", pg.inner_text("#install-btn"))
        pg.close()
    # (b) A boot-loop flood (one restart every few ms, 600 restarts): the page stays responsive, the console keeps at
    #  most 500 lines in the page, the restart output is held back behind one counting line, Copy Log still has it
    pg, errors = page(b, "window.__other = true;")
    pg.click("#connect"); pg.wait_for_timeout(1500)
    pg.evaluate("t => window.__say('sketch says hi\\r\\n')"); pg.wait_for_timeout(200)
    t0 = time.time()
    pg.evaluate("""t => new Promise(res => { let n = 0; const tick = () => { for (let k = 0; k < 20; k++) window.__say(t); if ((n += 20) < 600) setTimeout(tick, 5); else res(); }; tick(); })""", LOOP)
    pg.wait_for_timeout(500)
    took = time.time() - t0
    lag = pg.evaluate("() => new Promise(r => { const t = performance.now(); setTimeout(() => r(performance.now() - t), 0); })")
    dom_lines = pg.evaluate("document.getElementById('console-out').textContent.split('\\n').length")
    check("flood: page stays responsive", took < 15 and lag < 200, "%.1f s, lag %d ms" % (took, lag))
    check("flood: at most ~500 lines in the page", dom_lines <= 502, str(dom_lines))
    check("flood: Recover/Install GSP32", pg.inner_text("#install-btn") == "Recover/Install GSP32")
    tail = out(pg)
    check("flood: restart output held back behind one line", "lines of its restart output hidden" in tail and tail.count("invalid segment length") <= 3, tail[-300:])
    check("flood: the sketch's own line before it kept", "sketch says hi" in tail)
    check("no page errors (b)", not errors, str(errors)); pg.close()
    # (b) Paint batching: 2000 quick lines produce far fewer console paints than lines
    pg, errors = page(b)
    pg.click("#connect"); pg.wait_for_timeout(1500)
    pg.evaluate("""() => { window.__paints = 0; new MutationObserver(() => window.__paints++).observe(document.getElementById('console-out'), { childList: true, characterData: true, subtree: true }); }""")
    pg.evaluate("() => { for (let i = 0; i < 2000; i++) window.gsp32.appendConsole('line ' + i + '\\n'); }"); pg.wait_for_timeout(400)
    paints = pg.evaluate("window.__paints")
    check("2000 lines: a handful of paints, not 2000", 0 < paints <= 5, str(paints))
    check("2000 lines: the newest is shown", "line 1999" in out(pg) and "line 1000" not in out(pg))
    pg.close()
    b.close()
print("FAILURES:", fails)
raise SystemExit(1 if fails else 0)
