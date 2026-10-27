# Fix (unreadable output, Gene's new board): factory firmware at another speed reads as a flood of 0xF0/0xFC/"p"/"|"
#  at 115200. The console stays at 115200 after the board info; that output collapses into one updating line, the
#  page stays responsive, the board is never marked broken, and it gets plain Install GSP32
import os, http.server, threading, functools, time
from playwright.sync_api import sync_playwright
here = os.path.dirname(os.path.abspath(__file__)); site = os.path.dirname(here)
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8801), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)
GARBLE = [0xF0, 0xFC, 0x70, 0x7C, 0x00, 0xFC, 0xF0, 0x80, 0x7C, 0x70, 0xFE, 0x00, 0xF8, 0x70, 0x7C, 0xE0, 0x0A, 0xFC, 0x78, 0x80]
def page(b, init=""):
    pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.add_init_script(path=here + "/mock.js")
    pg.add_init_script("window.__ver = '47'; window.__ets = true;" + init)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.route("**/gsp32-telemetry.genereese.workers.dev/**", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true}'))
    errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:8801/index.html"); pg.wait_for_timeout(300)
    return pg, errors
def out(pg): return pg.inner_text("#console-out")
def flood(pg, kb):
    # kb KB of garbled bytes in 512-byte chunks, as fast as the page takes them
    pg.evaluate("""([g, kb]) => new Promise(res => { const chunk = []; while (chunk.length < 512) chunk.push(...g); let n = 0;
      const tick = () => { for (let k = 0; k < 16; k++) window.__sayBytes(chunk.slice(0, 512)); if ((n += 8) < kb) setTimeout(tick, 2); else res(); }; tick(); })""", [GARBLE, kb])
with sync_playwright() as p:
    b = p.chromium.launch()
    pg, errors = page(b, "window.__other = true;")
    pg.click("#connect"); pg.wait_for_timeout(1800)
    log = [l for l in pg.evaluate("window.__log") if isinstance(l, str)]
    opens = [l for l in log if l.startswith("open ")]
    # 1. After the board info the console listens at 115200 (esptool-js never changed the speed)
    check("connected without a board-info read (115.10: Install reads it)", "keeps running (no restart)" in out(pg) and "[Board:" not in out(pg))
    check("every open at 115200, no baud change", opens and all(l == "open 115200" for l in opens) and not [l for l in log if l.startswith("change baud")], str(opens))
    check("console reads again after board info", pg.evaluate("window.__say('after info 115200\\r\\n')") is None and (pg.wait_for_timeout(300) or "after info 115200" in out(pg)))
    # 2. A 300 KB flood of garbled bytes: one updating line, a few hundred lines at most, the page responsive
    t0 = time.time(); flood(pg, 300); pg.wait_for_timeout(400); took = time.time() - t0
    lag = pg.evaluate("() => new Promise(r => { const t = performance.now(); setTimeout(() => r(performance.now() - t), 0); })")
    text = out(pg); last = text.strip().splitlines()[-1]
    check("flood: page responsive", took < 20 and lag < 200, "%.1f s, lag %d ms" % (took, lag))
    check("flood: one updating line names it", last.startswith("[Board output isn't readable at 115200 (other firmware?): ") and last.endswith(" bytes hidden]"), last)
    hidden = int(last.split(": ")[1].split(" ")[0])
    check("flood: nearly all of it hidden", hidden > 290000, str(hidden))
    check("flood: no garble flood in the page", text.count("\ufffd") < 200 and len(text) < 20000, "%d chars, %d replacement" % (len(text), text.count("\ufffd")))
    check("flood: earlier readable lines kept", "after info 115200" in text)
    # 3. Never broken: Install GSP32, no Incomplete Install
    check("unreadable: plain Install GSP32", pg.inner_text("#install-btn") == "Install GSP32", pg.inner_text("#install-btn"))
    check("unreadable: not broken, no Incomplete", "Incomplete" not in pg.evaluate("document.body.innerText"))
    check("unreadable: Install enabled", pg.is_enabled("#install-btn"))
    # 4. Readable again (a restart's ROM banner at 115200): shown, with the count of what was hidden
    pg.evaluate("window.__say('\\r\\nets Jul 29 2019 12:21:46\\r\\n\\r\\nrst:0x1 (POWERON_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)\\r\\nconfigsip: 0, SPIWP:0xee\\r\\nreadable again\\r\\n')"); pg.wait_for_timeout(400)
    text = out(pg)
    check("readable again: shown", "readable again" in text and "rst:0x1 (POWERON_RESET)" in text, text[-300:])
    check("readable again: count of hidden bytes left in the log", " bytes of unreadable output were hidden]" in text)
    check("readable again: the updating line is gone", "bytes hidden]" not in text.strip().splitlines()[-1])
    # 5. Other firmware after 20 s: No GSP32 Found, Install GSP32 (never Recover)
    flood(pg, 40); pg.wait_for_timeout(20500)
    check("unknown firmware: No GSP32 Found + Install GSP32", "No GSP32 Found" in pg.inner_text("#board-state") and pg.inner_text("#install-btn") == "Install GSP32", pg.inner_text("#board-state") + " / " + pg.inner_text("#install-btn"))
    check("no page errors", not errors, str(errors)); pg.close()
    # 6. Readable non-ASCII text (UTF-8, accents, symbols) is never hidden
    pg, errors = page(b, "window.__other = true;")
    pg.click("#connect"); pg.wait_for_timeout(1800)
    for _ in range(30): pg.evaluate("window.__say('Température 25 °C – ok … ✓\\r\\n')")
    pg.wait_for_timeout(400)
    check("UTF-8 text stays visible", out(pg).count("Température 25 °C") == 30 and "isn't readable" not in out(pg))
    # A short burst of noise (a reset glitch) among readable lines is not hidden either
    pg.evaluate("g => window.__sayBytes(g.slice(0, 6))", GARBLE); pg.evaluate("window.__say('next line\\r\\n')"); pg.wait_for_timeout(300)
    check("a few noisy bytes: no hiding", "next line" in out(pg) and "isn't readable" not in out(pg))
    check("no page errors (6)", not errors, str(errors)); pg.close()
    b.close()
print("FAILURES:", fails)
raise SystemExit(1 if fails else 0)
