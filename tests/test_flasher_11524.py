""" Flasher 115.24 (Gene, 2026-10-28): GSP32-C V130 is the only version on the site. No classic Version 114.2
("Previous"), no Beta 115, no GSP32-C Betas V117-V129: their versions.json entries, manifests and firmware folders are
gone (git history keeps them; tests/oldsite.py brings them back for the suites that test several releases). The
Release dropdown stays hidden (Stable is the only pick), the page Installs GSP32-C V130 and Erase and Install loads
manifest-gspc-v130.json and firmware/gspc-v130/; the old addresses answer 404. The unlisted rollbacks V84, V85 and V99
stay as they were. No update flag, no note """
import sys, http.server, threading, functools, os, json, re, urllib.request, urllib.error
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); here = os.path.dirname(os.path.abspath(__file__))
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8904), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, "" if ok else extra); sys.stdout.flush()

versions = json.load(open(os.path.join(site, "versions.json")))
check("versions.json: one entry, GSP32-C V130, Stable (no channel), line GSP32-C", len(versions) == 1 and re.fullmatch(r"GSP32-C V130 \([0-9a-f]{7,}\)", versions[0]["label"])
      and "channel" not in versions[0] and versions[0].get("line") == "GSP32-C" and versions[0]["manifest"] == "manifest-gspc-v130.json", str(versions))
check("no update flag, no note", all("update" not in e and "note" not in e for e in versions))
mans = sorted(n for n in os.listdir(site) if n.startswith("manifest"))
check("manifests: V130 and the unlisted rollbacks only", mans == ["manifest-gspc-v130.json", "manifest-v84.json", "manifest-v85.json", "manifest-v99.json"], str(mans))
fw = sorted(os.listdir(os.path.join(site, "firmware")))
check("firmware/: gspc-v130 and the rollbacks only", fw == ["gspc-v130", "v84", "v85", "v99"], str(fw))
m = json.load(open(os.path.join(site, "manifest-gspc-v130.json")))
parts = [p["path"] for b in m["builds"] for p in b["parts"]]
check("V130: five images there", len(parts) == 5 and all(os.path.exists(os.path.join(site, p)) for p in parts), str(parts))
html = open(os.path.join(site, "index.html"), encoding="utf-8").read()
check("cache tag 115.24-s130 on style.css, app.js, tour.js", html.count("?v=115.24-s130\"") == 3)
def status(path):
    try: return urllib.request.urlopen("http://127.0.0.1:8904/" + path).status
    except urllib.error.HTTPError as e: return e.code
for path in ("manifest.json", "manifest-beta.json", "manifest-gspc-beta.json", "manifest-gspc-v129.json", "manifest-gspc-v118.json",
             "firmware/gsp32-esp32.bin", "firmware/beta/gsp32-esp32.bin", "firmware/gspc-v129/gsp32c-esp32.bin"):
    check("gone: " + path, status(path) == 404, status(path))

with sync_playwright() as p:
    b = p.chromium.launch()
    for width in (1100, 390):
        pg = b.new_page(viewport={"width": width, "height": 900}); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script("window.__ver = '84';")
        pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
        asked = []; errs = []
        pg.on("request", lambda r: asked.append(r.url)); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://127.0.0.1:8904/index.html"); pg.wait_for_timeout(800)
        w = " @%d" % width
        check("footer Flasher Version 115.24" + w, "Flasher Version 115.24" in pg.text_content(".flasher-version"))
        check("Release dropdown hidden (Stable is the only version)" + w, pg.locator(".release-field").is_hidden())
        usable = pg.evaluate("[...document.querySelectorAll('#release-channel option')].filter(o => !o.hidden && !o.disabled).map(o => o.value)")
        check("only Stable can be picked" + w, usable == ["stable"], str(usable))
        check("Installs GSP32-C V130" + w, pg.text_content("#version").strip() == "GSP32-C V130", pg.text_content("#version"))
        check("no old manifest asked for" + w, not any(re.search(r"/manifest(-beta|-gspc-beta|-gspc-v1[12]\d[.\d]*)?\.json", u) for u in asked), str([u for u in asked if "manifest" in u]))
        if width < 500:
            check("no sideways scroll on a phone", pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"))
            check("no page errors" + w, not errs, str(errs)); pg.close(); continue
        pg.click("#connect"); pg.wait_for_timeout(100)
        pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
        pg.wait_for_timeout(4500); pg.click("#install-btn"); pg.wait_for_timeout(500)
        check("after connect: Installs GSP32-C V130", pg.text_content("#version").strip() == "GSP32-C V130", pg.text_content("#version"))
        asked.clear()
        pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(3000)
        man = [u for u in asked if "manifest" in u]
        check("Erase and Install loads manifest-gspc-v130.json", any("manifest-gspc-v130.json" in u for u in man), str(man))
        img = [u for u in asked if u.endswith(".bin")]
        check("images from firmware/gspc-v130/", bool(img) and all("/firmware/gspc-v130/" in u for u in img), str(img))
        check("no page errors" + w, not errs, str(errs))
        pg.close()
print("fails", fails); sys.exit(1 if fails else 0)
