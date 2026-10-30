""" Flasher 115.23 (Gene, 2026-10-28): GSP32-C V130 is the Stable pick (the default; a versions.json entry with no
channel and line "GSP32-C"); "Installs GSP32-C V130"; Erase and Install loads manifest-gspc-v130.json and
firmware/gspc-v130/. The classic GSP32 Version 114.2 is one pick away as "Previous (Version 114.2)" (manifest.json);
classic Beta 115 and the GSP32-C Betas V129-V117 are unchanged; no update flag, no note """
import sys, http.server, threading, functools, os, json, re
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); here = os.path.dirname(os.path.abspath(__file__))
import oldsite; site = oldsite.overlay(site)  # Flasher 115.24: several releases come from the 115.23 list (tests/oldsite.py)
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8903), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)

versions = json.load(open(os.path.join(site, "versions.json")))
st = [e for e in versions if "channel" not in e and not e.get("prototype")]
check("one Stable entry: GSP32-C V130, first, line GSP32-C", len(st) == 1 and versions[0] is st[0] and re.fullmatch(r"GSP32-C V130 \([0-9a-f]{7,}\)", st[0]["label"]) and st[0].get("line") == "GSP32-C" and st[0]["manifest"] == "manifest-gspc-v130.json", str(st))
pv = [e for e in versions if e.get("channel") == "previous"]
check("Previous is the classic Version 114.2 (manifest.json)", len(pv) == 1 and pv[0]["label"].startswith("Version 114.2 ") and pv[0]["manifest"] == "manifest.json", str(pv))
bt = [e for e in versions if e.get("channel") == "beta"]
check("classic Beta 115 kept", len(bt) == 1 and bt[0]["label"].startswith("Version 115 ") and bt[0]["manifest"] == "manifest-beta.json", str(bt))
gc = [e for e in versions if e.get("channel") == "gspc-beta"]
check("GSP32-C Betas V129..V117 kept (15)", len(gc) == 15 and gc[0]["label"].startswith("GSP32-C Beta V129 "), str([e["label"] for e in gc]))
check("no update flag anywhere", all("update" not in e for e in versions))
m = json.load(open(os.path.join(site, "manifest-gspc-v130.json")))
parts = [p["path"] for b in m["builds"] for p in b["parts"]]
check("V130 manifest names it", m["version"] == st[0]["label"], m["version"])
check("V130: five chips' images in firmware/gspc-v130/", len(m["builds"]) == 5 and all(p.startswith("firmware/gspc-v130/") and os.path.exists(os.path.join(site, p)) for p in parts), str(parts))
check("V130: every build says improv", all(b.get("improv") is True for b in m["builds"]))
check("V130: offsets 4096 (ESP32) and 0", all(p["offset"] == (4096 if b["chipFamily"] == "ESP32" else 0) for b in m["builds"] for p in b["parts"]))
esp = open(os.path.join(site, "firmware/gspc-v130/gsp32c-esp32.bin"), "rb").read(4)
check("V130 ESP32 image: 80 MHz flash header", esp[0] == 0xE9 and esp[3] & 0x0F == 0x0F, esp.hex())

def show(pg):
    pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(4500); pg.click("#install-btn"); pg.wait_for_timeout(500)

with sync_playwright() as p:
    b = p.chromium.launch()
    for width in (1100, 390):
        pg = b.new_page(viewport={"width": width, "height": 900}); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script("window.__ver = '84';")
        pg.route("**/vendor/esptool-js-0.5.7.js", lambda r, _q=None: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
        asked = []; errs = []
        pg.on("request", lambda r: asked.append(r.url)); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://127.0.0.1:8903/index.html"); pg.wait_for_timeout(600)
        w = " @%d" % width
        check("footer Flasher Version 115.29" + w, "Flasher Version 115.29" in pg.content())
        check("Stable is the default pick" + w, pg.input_value("#release-channel") == "stable")
        top = pg.evaluate("[...document.querySelectorAll('#release-channel > option')].map(o => [o.value, o.textContent, o.hidden || o.disabled])")
        check("Release: Stable, Beta, Previous (Version 114.2), all usable" + w, [o[:2] for o in top] == [["stable", "Stable"], ["beta", "Beta"], ["previous", "Previous (Version 114.2)"]] and not any(o[2] for o in top), str(top))
        check("Installs GSP32-C V130 (Stable, before connecting)" + w, pg.text_content("#version").strip() == "GSP32-C V130", pg.text_content("#version"))
        opts = pg.evaluate("[...document.querySelectorAll('#gspc-group option')].map(o => o.value)")
        check("GSP32-C group still lists V129 first (15 Betas)" + w, len(opts) == 15 and opts[0] == "gspc-129", str(opts))
        if width < 500:
            check("no sideways scroll on a phone", pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"))
            pg.close(); continue
        show(pg)
        check("after connect: still Installs GSP32-C V130", pg.text_content("#version").strip() == "GSP32-C V130", pg.text_content("#version"))
        pg.select_option("#release-channel", "previous"); pg.wait_for_timeout(300)
        check("Previous: Installs Version 114.2", pg.text_content("#version").strip() == "Version 114.2", pg.text_content("#version"))
        pg.select_option("#release-channel", "beta"); pg.wait_for_timeout(300)
        check("Beta: Installs Version 115", pg.text_content("#version").strip() == "Version 115", pg.text_content("#version"))
        pg.select_option("#release-channel", "gspc-129"); pg.wait_for_timeout(300)
        check("gspc-129: Installs GSP32-C Beta V129", pg.text_content("#version").strip() == "GSP32-C Beta V129", pg.text_content("#version"))
        pg.select_option("#release-channel", "stable"); pg.wait_for_timeout(300)
        check("back to Stable: Installs GSP32-C V130", pg.text_content("#version").strip() == "GSP32-C V130", pg.text_content("#version"))
        asked.clear()
        pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(3000)
        man = [u for u in asked if "manifest" in u]
        check("Stable installs manifest-gspc-v130.json only", any("manifest-gspc-v130.json" in u for u in man) and not any(re.search(r"manifest(-beta|-gspc-v1[12]\d[.\d]*|-gspc-beta)?\.json", u) for u in man), str(man))
        img = [u for u in asked if u.endswith(".bin")]
        check("Stable loads firmware/gspc-v130 images", bool(img) and all("/firmware/gspc-v130/" in u for u in img), str(img))
        st_txt = pg.text_content("body")
        check("status names GSP32-C V130 while installing", "Installing GSP32-C V130" in st_txt or "GSP32-C V130" in st_txt)
        check("no page errors", not errs, str(errs))
        pg.close()
print("fails", fails); sys.exit(1 if fails else 0)
