# Fix (Gene, live b92e): a boot loop with no esp_image error (ROM banner, load, entry, SW_RESET) must not be called
#  "no bootable firmware"; and every broken state reads Recover/Install GSP32 in full (one line, nothing clipped)
import os, http.server, threading, functools, json
from playwright.sync_api import sync_playwright
here = os.path.dirname(os.path.abspath(__file__)); site = os.path.dirname(here)
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8803), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)
RECOVER = "Recover/Install GSP32"
BANNER = ("rst:0xc (SW_CPU_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)\r\nconfigsip: 0, SPIWP:0xee\r\n"
          "clk_drv:0x00,q_drv:0x00,d_drv:0x00,cs0_drv:0x00,hd_drv:0x00,wp_drv:0x00\r\nmode:DIO, clock div:2\r\n"
          "load:0x3fff0030,len:1184\r\nload:0x40078000,len:13232\r\nload:0x40080400,len:3028\r\nentry 0x400806ac\r\n")
IMAGE_ERR = "E (31) esp_image: invalid segment length 0xe0f6e781\r\nE (37) boot: Factory app partition is not bootable\r\nE (42) boot: No bootable app partitions in the partition table\r\n"
def page(b, init="", width=1100):
    pg = b.new_page(viewport={"width": width, "height": 900}); pg.add_init_script(path=here + "/mock.js")
    pg.add_init_script("window.__ver = '47';" + init)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.route("**/gsp32-telemetry.genereese.workers.dev/**", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true}'))
    errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:8803/index.html"); pg.wait_for_timeout(300)
    return pg, errors
def loop(pg, text, n=200):
    pg.evaluate("([t, n]) => new Promise(res => { let k = 0; const tick = () => { for (let i = 0; i < 10; i++) window.__say(t); if ((k += 10) < n) setTimeout(tick, 20); else res(); }; tick(); })", [text, n])
    pg.wait_for_timeout(400)
def last_line(pg): return pg.inner_text("#console-out").strip().splitlines()[-1]
def label_full(pg):
    return pg.evaluate("""(() => { const e = document.getElementById('install-btn'), lh = parseFloat(getComputedStyle(e).lineHeight) || 24;
      const r = document.createRange(); r.selectNodeContents(e); const rects = [...r.getClientRects()];
      return { text: e.textContent, inner: e.innerText, lines: rects.length, clipped: e.scrollWidth > e.clientWidth + 1, visible: !!e.offsetParent }; })()""")
def label_ok(name, pg):
    l = label_full(pg)
    check(name + ": reads Recover/Install GSP32 in full, one line", l["text"] == RECOVER and l["inner"] == RECOVER and l["lines"] == 1 and not l["clipped"] and l["visible"], str(l))
with sync_playwright() as p:
    b = p.chromium.launch()
    # (a) Gene's loop: ROM banner, load, entry, SW_RESET, no esp_image error
    pg, errors = page(b, "window.__other = true;")
    pg.click("#connect"); pg.wait_for_timeout(1500)
    loop(pg, BANNER)
    ll = last_line(pg)
    check("restart loop, no image error: 'The device keeps restarting:'", ll.startswith("[The device keeps restarting: ") and "no bootable" not in ll, ll)
    check("it still names the button", ("Click " + RECOVER + ".]") in ll, ll)
    label_ok("restart loop", pg)
    check("no page errors (a)", not errors, str(errors)); pg.close()
    # With the image errors, it says why
    pg, errors = page(b, "window.__other = true;")
    pg.click("#connect"); pg.wait_for_timeout(1500)
    loop(pg, BANNER + IMAGE_ERR)
    ll = last_line(pg)
    check("restart loop with esp_image errors: '(no bootable firmware)'", ll.startswith("[The device keeps restarting (no bootable firmware): "), ll)
    label_ok("loop with image errors", pg); pg.close()
    # A new Get Started forgets it (the next board's loop is judged afresh)
    # (b) Every broken state, wide and narrow window
    for width in (1100, 420):
        cases = [
            ("boot loop (mock)", "window.__bootLoop = true;", "reset"),
            ("ROM error line", "window.__other = true;", "say:ota data partition invalid, falling back to factory\r\n"),
            ("invalid segment length", "window.__other = true;", "say:" + IMAGE_ERR.splitlines()[0] + "\r\n"),
            ("No bootable app partitions", "window.__other = true;", "say:E (42) boot: No bootable app partitions in the partition table\r\n"),
            ("cut-off install note for this MAC", "window.__other = true; localStorage.setItem('gsp32.flash', JSON.stringify({mac: 'f8:b3:b7:22:05:e8', version: '92', startedAt: 1, writing: true}));", ""),
        ]
        for name, init, how in cases:
            pg, errors = page(b, init, width)
            pg.click("#connect"); pg.wait_for_timeout(1500)
            if how == "reset": pg.click("#reset"); pg.wait_for_timeout(3800)
            elif how.startswith("say:"): pg.evaluate("t => window.__say(t)", how[4:]); pg.wait_for_timeout(400)
            label_ok("%s at %d px" % (name, width), pg)
            check("%s at %d px: status names the same label" % (name, width), RECOVER in (pg.inner_text("#board-status") if pg.is_visible("#board-status") else "") or "Incomplete Install Detected" in pg.inner_text("#board-state"))
            pg.close()
    b.close()
print("FAILURES:", fails)
raise SystemExit(1 if fails else 0)
