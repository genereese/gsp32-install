""" Flasher Version 115.19 (Gene, 2026-10-27): the flasher only does clean installs. The Update (Keep Files) path of
115.16 is gone: no Update button, no keep-files hint or text, no partition-table read, no "update" flag in versions.json.
Every pick (GSP32 and GSP32-C, V127.3 included) installs with the erase tick and Erase and Install, which erases the
whole chip and writes the one merged image; afterwards the next step is Set Up Wi-Fi. To keep files, the yellow erase box points to
the Backup app (Flasher 115.20: the GSP32-C note is gone) """
import http.server, threading, functools, os, json, re, sys
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); here = os.path.dirname(os.path.abspath(__file__))
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8831), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)

html = open(os.path.join(site, "index.html")).read(); js = open(os.path.join(site, "app.js")).read()
versions = json.load(open(os.path.join(site, "versions.json")))
check("versions.json: no entry carries an update flag", all("update" not in e for e in versions))
check("index.html: no Update button or keep-files hint", "start-update" not in html and "update-hint" not in html and "Keep Files" not in html and "(or <b>Update</b>)" not in html)
for word in ("start-update", "update-hint", "updateOffered", "updateLayoutCheck", "updatePieces", "installKeeps", "readFlash", "Keep Files", "were kept", "Updating to", "eraseAll: !"):
    check("app.js: no " + word, word not in js)
check("app.js: the install always erases the whole chip", "eraseAll: true," in js)
check("app.js: install() takes no mode", "async function install() {" in js)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script("window.__ver = '84';")
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r, _q=None: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:8831/index.html"); pg.wait_for_timeout(600)
    pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(4500); pg.click("#install-btn"); pg.wait_for_timeout(500)
    for key in ("stable", "beta", "gspc-127.3", "gspc-127.2", "gspc-126"):
        pg.select_option("#release-channel", key); pg.wait_for_timeout(250)
        step = pg.inner_text('[data-step="prep"]')
        check(key + ": no Update button, no keep-files text", pg.locator("#start-update").count() == 0 and "Update" not in step and "Keep Files" not in step, step[-300:])
        check(key + ": Erase and Install needs the tick", not pg.is_enabled("#start-install"))
    pg.select_option("#release-channel", "gspc-127.3"); pg.wait_for_timeout(300)
    box = " ".join(pg.text_content("label[for=erase-ok]").split())
    check("Flasher 115.20: no GSP32-C note; the yellow erase box mentions Backup", pg.locator("#gspc-note").count() == 0 and "Backup" in box and "erases everything" in box, box)
    pg.check("#erase-ok"); pg.wait_for_timeout(100)
    check("ticked: Erase and Install usable", pg.is_enabled("#start-install"))
    pg.evaluate("window.__log.length = 0"); pg.click("#start-install"); pg.wait_for_timeout(6000)
    L = pg.evaluate("window.__log.slice()")
    check("install: erases the whole chip", "erase all" in L, str(L))
    check("install: one merged image, eraseAll true, no flash read", any(x.startswith("files 1 ") and x.endswith("eraseAll true") for x in L) and not any(x.startswith("read flash") for x in L), str(L))
    status = pg.text_content("#board-status")
    check("installed: next step is Set Up Wi-Fi", "Set Up Wi-Fi" in status and "kept" not in status, status)
    check("no page errors", not errs, str(errs))
    b.close()
print("FAILURES:", fails); sys.exit(1 if fails else 0)
