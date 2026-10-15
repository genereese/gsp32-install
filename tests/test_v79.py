# Version 79: one manifest with two builds (ESP32 4 MB, ESP32-S3 16 MB, both at 0); the install picks by the chip it
#  finds; other chips get a clear error; footer and text name both chips
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
check("erase wording per chip (S3 16 MB about a minute)", 'family === "ESP32-S3" ? "about a minute" : "about 15 seconds"' in js)
html = open(os.path.join(site, "index.html")).read()
check("cache-bust 76-fw79 everywhere", html.count("?v=76-fw79") == 3 and "fw78" not in html)
def run(b, chip):
    pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.add_init_script(path=here + "/mock.js")
    pg.add_init_script("window.__ver = '47';" + ("window.__chip = %s;" % json.dumps(chip) if chip else ""))
    pg.add_init_script("""window.__status = []; addEventListener('DOMContentLoaded', () => { const el = document.getElementById('board-status');
      new MutationObserver(() => window.__status.push(el.textContent)).observe(el, {childList: true, characterData: true, subtree: true}); });""")
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.goto("http://127.0.0.1:8789/index.html"); pg.wait_for_timeout(300); pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(4500)
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(6000)
    log = [l for l in pg.evaluate("window.__log") if isinstance(l, str)]
    return pg, log, pg.evaluate("window.__status")
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(); pg.goto("http://127.0.0.1:8789/index.html"); body = pg.inner_text("body")
    check("text names ESP32 and ESP32-S3", "ESP32 and ESP32-S3" in body)
    check("footer Flasher Version 79", "Flasher Version 79" in pg.text_content(".flasher-version")); pg.close()
    pg, log, st = run(b, None)
    w = [l for l in log if l.startswith("files")]
    check("classic ESP32 gets the 4 MB image at 0", w == ["files 1 size 4194304 at 0 eraseAll true"], str(w))
    check("ESP32 installed", "Installed" in pg.inner_text("body")); pg.close()
    pg, log, st = run(b, "ESP32-S3 (QFN56) (revision v0.2)")
    w = [l for l in log if l.startswith("files")]
    check("ESP32-S3 gets the 16 MB image at 0", w == ["files 1 size 16777216 at 0 eraseAll true"], str(w))
    check("S3 detected in the console", "[ESP32-S3 detected: installing its build]" in pg.inner_text("#console-out"))
    check("S3 installed", "Installed" in pg.inner_text("body"), str(st[-3:])); pg.close()
    pg, log, st = run(b, "ESP32-C3 (QFN32) (revision v0.4)")
    check("ESP32-C3: nothing written", not [l for l in log if l.startswith("files")])
    check("ESP32-C3: clear error", "GSP32 runs on ESP32 and ESP32-S3 boards" in pg.inner_text("body")); pg.close()
    b.close()
srv.shutdown()
print("FAILURES:", fails); sys.exit(1 if fails else 0)
