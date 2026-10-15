# Version 79: multi-chip install; unsupported chip/flash shows Title-Case warn-box (no write);
#  subtle board-details line (MAC-style) with cores/flash/crystal/USB when readable
import sys, os, json, http.server, threading, functools
from playwright.sync_api import sync_playwright
here = os.path.dirname(os.path.abspath(__file__)); site = os.path.dirname(here)
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8789), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)
m = json.load(open(os.path.join(site, "manifest.json")))
fam = {b["chipFamily"]: b["parts"] for b in m["builds"]}
check("manifest: ESP32 and ESP32-S3 builds", sorted(fam) == ["ESP32", "ESP32-S3"], str(sorted(fam)))
check("both at offset 0", all(len(p) == 1 and p[0]["offset"] == 0 for p in fam.values()))
sz = {f: os.path.getsize(os.path.join(site, p[0]["path"])) for f, p in fam.items()}
check("ESP32 image 4 MB, S3 image 16 MB", sz == {"ESP32": 0x400000, "ESP32-S3": 0x1000000}, str(sz))
s3img = open(os.path.join(site, fam["ESP32-S3"][0]["path"]), "rb").read(4)
check("S3 image starts with a bootloader header at 0", s3img[0] == 0xE9)
v = json.load(open(os.path.join(site, "versions.json")))
check("versions.json: Version 79 only", len(v) == 1 and v[0]["label"].startswith("Version 79") and v[0]["manifest"] == "manifest.json")
js = open(os.path.join(site, "app.js")).read()
html = open(os.path.join(site, "index.html")).read()
css = open(os.path.join(site, "style.css")).read()
check("erase wording per chip (S3 16 MB about a minute)", 'family === "ESP32-S3" ? "about a minute" : "about 15 seconds"' in js)
check("cache-bust 77-fw79 everywhere", html.count("?v=77-fw79") == 3 and "fw78" not in html and "fw76" not in html, str(html.count("?v=77-fw79")))
check("no Compatible Boards card", 'id="compatible"' not in html)
check("compat-notice warn-box present", 'id="compat-notice"' in html and "compat-notice" in css)
check("board-details MAC-style", 'id="board-details"' in html and "board-details" in css and "formatBoardDetails" in js)
check("compatIssue + showCompatNotice", "compatIssue" in js and "showCompatNotice" in js and "This Board Is Not Supported" in js)

def run(b, chip, flash_kb=None, usb=None):
    pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.add_init_script(path=here + "/mock.js")
    init = "window.__ver = '47'; window.__log = [];"
    if chip: init += "window.__chip = %s;" % json.dumps(chip)
    if flash_kb is not None: init += "window.__flashKb = %s;" % json.dumps(flash_kb)
    if usb is not None: init += "window.__usb = %s;" % json.dumps(usb)
    pg.add_init_script(init)
    pg.add_init_script("""window.__status = []; addEventListener('DOMContentLoaded', () => { const el = document.getElementById('board-status');
      new MutationObserver(() => window.__status.push(el.textContent)).observe(el, {childList: true, characterData: true, subtree: true}); });""")
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.goto("http://127.0.0.1:8789/index.html"); pg.wait_for_timeout(300); pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(4500)
    # USB bridge name can show before install (from getInfo)
    details_early = pg.evaluate("(() => { const el = document.getElementById('board-details'); return el && !el.hidden ? el.textContent : ''; })()")
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(6000)
    log = [l for l in pg.evaluate("window.__log") if isinstance(l, str)]
    notice = pg.evaluate("""() => {
      const box = document.getElementById('compat-notice');
      if (!box || box.hidden) return null;
      return { title: document.getElementById('compat-notice-title').textContent,
               text: document.getElementById('compat-notice-text').textContent };
    }""")
    details = pg.evaluate("(() => { const el = document.getElementById('board-details'); return el && !el.hidden ? el.textContent : ''; })()")
    mac = pg.evaluate("(() => { const el = document.getElementById('board-mac'); return el && !el.hidden ? el.textContent : ''; })()")
    return pg, log, pg.evaluate("window.__status"), notice, details, mac, details_early

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(); pg.goto("http://127.0.0.1:8789/index.html"); body = pg.inner_text("body")
    check("text names ESP32 and ESP32-S3", "ESP32 and ESP32-S3" in body)
    check("footer Flasher Version 79", "Flasher Version 79" in pg.text_content(".flasher-version"))
    check("no Compatible Boards on page", "Compatible Boards" not in body); pg.close()

    pg, log, st, notice, details, mac, early = run(b, None)
    w = [l for l in log if l.startswith("files")]
    check("classic ESP32 gets the 4 MB image at 0", w == ["files 1 size 4194304 at 0 eraseAll true"], str(w))
    check("ESP32 installed", "Installed" in pg.inner_text("body"))
    check("no compat notice on good ESP32", notice is None, str(notice))
    check("MAC line shown", mac.upper().startswith("MAC ") and "F8:B3:B7:22:05:E8" in mac.upper(), mac)
    check("board details subtle (dual + flash + crystal + CP2102)",
          "Dual Core" in details and "4 MB flash" in details and "40 MHz" in details and "CP2102" in details, details)
    check("USB shown early from getInfo", "CP2102" in early, early)
    pg.close()

    pg, log, st, notice, details, mac, early = run(b, "ESP32-S3 (QFN56) (revision v0.2)")
    w = [l for l in log if l.startswith("files")]
    check("ESP32-S3 gets the 16 MB image at 0", w == ["files 1 size 16777216 at 0 eraseAll true"], str(w))
    check("S3 detected in the console", "[ESP32-S3 detected: installing its build]" in pg.inner_text("#console-out"))
    check("S3 installed", "Installed" in pg.inner_text("body"), str(st[-3:]))
    check("S3 details include PSRAM + 16 MB", "16 MB flash" in details and "Embedded PSRAM" in details and "Dual Core" in details, details)
    check("no compat notice on good S3", notice is None); pg.close()

    pg, log, st, notice, details, mac, early = run(b, "ESP32-C3 (QFN32) (revision v0.4)")
    check("ESP32-C3: nothing written", not [l for l in log if l.startswith("files")], str(log))
    check("ESP32-C3: compat notice shown", notice and notice["title"] == "This Board Is Not Supported", str(notice))
    check("ESP32-C3: Title Case + chip in text", notice and "This board is ESP32-C3" in notice["text"] and "Nothing was installed" in notice["text"], str(notice))
    check("ESP32-C3: no old clear-error string", "GSP32 runs on ESP32 and ESP32-S3 boards" not in pg.inner_text("body"))
    check("ESP32-C3: Single Core in details", "Single Core" in details, details)
    pg.close()

    # Classic ESP32 with too-small flash
    pg, log, st, notice, details, mac, early = run(b, "ESP32-D0WD-V3 (revision v3.1)", flash_kb=2048)
    check("small flash ESP32: nothing written", not [l for l in log if l.startswith("files")])
    check("small flash: notice names 2 MB", notice and "2 MB flash" in notice["text"] and "This Board Is Not Supported" == notice["title"], str(notice))
    check("small flash: details show 2 MB", "2 MB flash" in details, details)
    pg.close()

    # S3 with too-small flash
    pg, log, st, notice, details, mac, early = run(b, "ESP32-S3 (QFN56) (revision v0.2)", flash_kb=8192)
    check("S3 8 MB: nothing written", not [l for l in log if l.startswith("files")])
    check("S3 8 MB: notice", notice and "8 MB flash" in notice["text"], str(notice))
    pg.close()

    # CH343 USB bridge
    pg, log, st, notice, details, mac, early = run(b, None, usb={"usbVendorId": 0x1a86, "usbProductId": 0x55d3})
    check("CH343 named from VID/PID", "CH343" in details, details)
    check("CH343 early", "CH343" in early, early)
    pg.close()

    b.close()
srv.shutdown()
print("FAILURES:", fails); sys.exit(1 if fails else 0)
