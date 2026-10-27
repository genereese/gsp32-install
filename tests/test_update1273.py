""" Flasher Version 115.16 (GSP32-C Beta V127.3, Gene 2026-10-27): Update (Keep Files). Shown only for picks with
"update": true (V127.3); it needs no tick. It reads the device's partition table (0x8000) first: when it matches the
image's, it writes the image in two pieces, start to 0x9000 and 0x10000 on, with no erase (NVS pairings, Wi-Fi and the
file system are kept) and says so; a different table or a failed read stops it with nothing written. Erase and Install
still erases the whole chip """
import sys, http.server, threading, functools, os, json
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); here = os.path.dirname(os.path.abspath(__file__))
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8831), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)

fw = os.path.join(site, "firmware/gspc-v127.3")
def table(name, base):
    d = open(os.path.join(fw, name), "rb").read()
    return list(d[0x8000 - base:0x8000 - base + 0xC00]), len(d)
t_esp32, n_esp32 = table("gsp32c-esp32.bin", 0x1000)
t_c3, n_c3 = table("gsp32c-esp32c3.bin", 0)
t_s3, _ = table("gsp32c-esp32s3.bin", 0)
check("test data: the S3 16 MB table differs from the ESP32's", t_s3 != t_esp32)

def page(b, chip=None):
    pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script("window.__ver = '84';")
    if chip: pg.add_init_script("window.__chip = %s;" % json.dumps(chip))
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r, _q=None: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.goto("http://127.0.0.1:8831/index.html"); pg.wait_for_timeout(600)
    pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(4500); pg.click("#install-btn"); pg.wait_for_timeout(500)
    return pg
def log(pg): return pg.evaluate("window.__log.slice()")

with sync_playwright() as p:
    b = p.chromium.launch()
    errs = []
    # 1. which picks offer it
    pg = page(b); pg.on("pageerror", lambda e: errs.append(str(e)))
    check("Stable: no Update button", not pg.is_visible("#start-update"))
    for key in ("gspc-127.2", "gspc-127.1", "gspc-126", "beta"):
        pg.select_option("#release-channel", key); pg.wait_for_timeout(250)
        check(key + ": no Update button", not pg.is_visible("#start-update") and not pg.is_visible("#update-hint"))
    pg.select_option("#release-channel", "gspc-127.3"); pg.wait_for_timeout(300)
    check("gspc-127.3: Update (Keep Files) shown and usable without the erase tick", pg.is_visible("#start-update") and pg.is_enabled("#start-update")
          and not pg.is_checked("#erase-ok") and pg.text_content("#start-update").strip() == "Update (Keep Files)")
    check("gspc-127.3: the hint is shown", pg.is_visible("#update-hint") and "Update (Keep Files)" in pg.text_content("#update-hint"))
    check("gspc-127.3: Erase and Install still needs the tick", not pg.is_enabled("#start-install"))
    # 2. matching table (ESP32): two pieces, no erase, kept text
    pg.evaluate("t => { window.__devTable = t; window.__log.length = 0; }", t_esp32)
    pg.click("#start-update"); pg.wait_for_timeout(5000)
    L = log(pg)
    check("ESP32 update: read the table at 0x8000 first", "read flash 0x8000 3072" in L and L.index("read flash 0x8000 3072") < next((i for i, x in enumerate(L) if x.startswith("parts ")), 10**6), str(L))
    want = "parts 0x1000:%d 0x10000:%d" % (0x9000 - 0x1000, n_esp32 - (0x10000 - 0x1000))
    check("ESP32 update: writes " + want, want in L, str([x for x in L if x.startswith("parts")]))
    check("ESP32 update: no erase", not any(x in L for x in ("erase all", "erase skipped (IS_STUB false)")) and any("eraseAll false" in x for x in L), str(L))
    body = pg.text_content("body")
    check("ESP32 update: says files, settings, Wi-Fi and paired devices were kept", "paired devices were kept" in body and "Set Up Wi-Fi\" above" not in body, pg.text_content("#board-status"))
    pg.close()
    # 3. matching table (C3)
    pg = page(b, "ESP32-C3 (QFN32) (revision v0.4)"); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.select_option("#release-channel", "gspc-127.3"); pg.wait_for_timeout(300)
    pg.evaluate("t => { window.__devTable = t; window.__log.length = 0; }", t_c3)
    pg.click("#start-update"); pg.wait_for_timeout(5000)
    L = log(pg); want = "parts 0x0:%d 0x10000:%d" % (0x9000, n_c3 - 0x10000)
    check("C3 update: writes " + want + ", no erase", want in L and "erase all" not in L, str([x for x in L if x.startswith(("parts", "files", "erase"))]))
    pg.close()
    # 4. a different table (an ESP32 holding the S3 16 MB layout): refused, nothing written
    for name, setup in (("different table", "t => { window.__devTable = t; window.__log.length = 0; }"),
                        ("blank table", "t => { window.__devTable = null; window.__log.length = 0; }"),
                        ("failed read", "t => { window.__readFail = true; window.__log.length = 0; }")):
        pg = page(b); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.select_option("#release-channel", "gspc-127.3"); pg.wait_for_timeout(300)
        pg.evaluate(setup, t_s3)
        pg.click("#start-update"); pg.wait_for_timeout(4000)
        L = log(pg); err = pg.text_content("#error-text") or ""
        check(name + ": refused, nothing written or erased", "read flash 0x8000 3072" in L and not any(x.startswith(("write at", "parts", "files", "erase")) for x in L), str(L))
        st = pg.text_content("#board-status") or ""
        check(name + ": the error step and the status line say nothing changed", pg.is_visible("#board-status") and "Nothing on the device was changed" in st
              and "Nothing on the device was changed" in err and "Update stopped before writing anything" in err
              and pg.evaluate("[...document.querySelectorAll('.step')].filter(s => !s.hidden).map(s => s.dataset.step).join()") == "error", st)
        pg.close()
    # 5. Erase and Install on the same pick still erases and writes the whole image
    pg = page(b); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.select_option("#release-channel", "gspc-127.3"); pg.wait_for_timeout(300)
    pg.evaluate("t => { window.__devTable = t; window.__log.length = 0; }", t_esp32)
    pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(5000)
    L = log(pg)
    check("Erase and Install: no table read, erase all, one piece at 0x1000", "read flash 0x8000 3072" not in L and "erase all" in L and ("parts 0x1000:%d" % n_esp32) in L, str([x for x in L if x.startswith(("parts", "erase", "read"))]))
    check("Erase and Install: next step is Set Up Wi-Fi", "Set Up Wi-Fi" in (pg.text_content("#board-status") or ""), pg.text_content("#board-status"))
    pg.close()
    check("no page errors", not errs, str(errs))
print("fails", fails); sys.exit(1 if fails else 0)
