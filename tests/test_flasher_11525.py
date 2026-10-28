""" Flasher 115.25 (Gene, 2026-10-28): GSP32-C V130 stays the Stable pick and GSP32-C Beta V131 is listed next to it
(its own pick in the GSP32-C group of the Release dropdown). The unlisted rollbacks V84, V85 and V99 are gone (Gene:
"remove all previous versions"; git history keeps them, tests/oldsite.py brings them back for test_v79). The page
names a board from its start-up line or Improv answer in both forms: "GSP32-C Beta V131" and, from a Stable build,
"GSP32-C V132". Replaces test_flasher_11524 (V130 the only entry). No update flag, no note """
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
check("versions.json: GSP32-C V130 Stable first (no channel), then GSP32-C Beta V131 (gspc-beta)", len(versions) == 2 and re.fullmatch(r"GSP32-C V130 \([0-9a-f]{7,}\)", versions[0]["label"])
      and "channel" not in versions[0] and versions[0].get("line") == "GSP32-C" and versions[0]["manifest"] == "manifest-gspc-v130.json"
      and re.fullmatch(r"GSP32-C Beta V131 \([0-9a-f]{7,}\)", versions[1]["label"]) and versions[1].get("channel") == "gspc-beta"
      and versions[1].get("line") == "GSP32-C" and versions[1]["manifest"] == "manifest-gspc-v131.json", str(versions))
check("no update flag, no note", all("update" not in e and "note" not in e for e in versions))
mans = sorted(n for n in os.listdir(site) if n.startswith("manifest"))
check("manifests: V130 and V131 only (no rollbacks)", mans == ["manifest-gspc-v130.json", "manifest-gspc-v131.json"], str(mans))
fw = sorted(os.listdir(os.path.join(site, "firmware")))
check("firmware/: gspc-v130 and gspc-v131 only", fw == ["gspc-v130", "gspc-v131"], str(fw))
for v in ("130", "131"):
    m = json.load(open(os.path.join(site, "manifest-gspc-v%s.json" % v)))
    parts = [p["path"] for b in m["builds"] for p in b["parts"]]
    check("V%s: five images there, in firmware/gspc-v%s/" % (v, v), len(parts) == 5 and all(os.path.exists(os.path.join(site, p)) and p.startswith("firmware/gspc-v%s/" % v) for p in parts), str(parts))
    check("V%s manifest names itself" % v, re.fullmatch(r"GSP32-C (Beta )?V%s \([0-9a-f]{7,}\)" % v, m["version"]) is not None, m["version"])
html = open(os.path.join(site, "index.html"), encoding="utf-8").read()
tag = re.search(r"\?v=(115\.25-[\w.-]+)\"", html)
check("cache tag 115.25-* on style.css, app.js, tour.js", bool(tag) and html.count("?v=" + tag.group(1) + "\"") == 3, tag and tag.group(1))
def status(path):
    try: return urllib.request.urlopen("http://127.0.0.1:8904/" + path).status
    except urllib.error.HTTPError as e: return e.code
for path in ("manifest.json", "manifest-beta.json", "manifest-gspc-beta.json", "manifest-gspc-v129.json", "manifest-gspc-v118.json",
             "firmware/gsp32-esp32.bin", "firmware/beta/gsp32-esp32.bin", "firmware/gspc-v129/gsp32c-esp32.bin",
             "manifest-v84.json", "manifest-v85.json", "manifest-v99.json", "firmware/v84/gsp32-esp32.bin", "firmware/v99/gsp32-esp32.bin"):
    check("gone: " + path, status(path) == 404, status(path))

def pick(pg, value):   # the dropdown sits in the install step (hidden before connect): set it as a pick does
    pg.evaluate("v => { const s = document.getElementById('release-channel'); s.value = v; s.dispatchEvent(new Event('change')); }", value); pg.wait_for_timeout(200)

with sync_playwright() as p:
    b = p.chromium.launch()
    for width in (1100, 390):
        pg = b.new_page(viewport={"width": width, "height": 900}); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script("window.__ver = '84';")
        pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
        asked = []; errs = []
        pg.on("request", lambda r: asked.append(r.url)); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://127.0.0.1:8904/index.html"); pg.wait_for_timeout(800)
        w = " @%d" % width
        check("footer Flasher Version 115.25" + w, "Flasher Version 115.25" in pg.text_content(".flasher-version"))
        check("Release dropdown shown (Stable and the Beta)" + w, pg.evaluate("!document.querySelector('.release-field').hidden"))   # (in the install step, shown after connect)
        usable = pg.evaluate("[...document.querySelectorAll('#release-channel option')].filter(o => !o.hidden && !o.disabled).map(o => o.value + '=' + o.textContent.trim())")
        check("picks: Stable, GSP32-C Beta V131" + w, usable == ["stable=Stable", "gspc-131=GSP32-C Beta V131"], str(usable))
        check("Stable is the default pick" + w, pg.eval_on_selector("#release-channel", "e => e.value") == "stable")
        check("Installs GSP32-C V130" + w, pg.text_content("#version").strip() == "GSP32-C V130", pg.text_content("#version"))
        check("no old manifest asked for" + w, not any(re.search(r"/manifest(-beta|-gspc-beta|-gspc-v1[12]\d[.\d]*|-v\d+)?\.json", u) for u in asked), str([u for u in asked if "manifest" in u]))
        pick(pg, "gspc-131")
        check("Beta pick: Installs GSP32-C Beta V131" + w, pg.text_content("#version").strip() == "GSP32-C Beta V131", pg.text_content("#version"))
        pick(pg, "stable")
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
    # the Beta pick installs V131 from its own files
    pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script("window.__ver = '84';")
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    asked = []; errs = []
    pg.on("request", lambda r: asked.append(r.url)); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:8904/index.html"); pg.wait_for_timeout(800)
    pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(4500); pg.click("#install-btn"); pg.wait_for_timeout(500)
    check("Beta: Release dropdown visible in the install step", pg.locator(".release-field").is_visible())
    pg.select_option("#release-channel", "gspc-131"); pg.wait_for_timeout(300)
    check("Beta: after connect still Installs GSP32-C Beta V131", pg.text_content("#version").strip() == "GSP32-C Beta V131", pg.text_content("#version"))
    asked.clear(); pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(3000)
    man = [u for u in asked if "manifest" in u]; img = [u for u in asked if u.endswith(".bin")]
    check("Beta: Erase and Install loads manifest-gspc-v131.json", any("manifest-gspc-v131.json" in u for u in man) and not any("v130" in u for u in man), str(man))
    check("Beta: images from firmware/gspc-v131/", bool(img) and all("/firmware/gspc-v131/" in u for u in img), str(img))
    check("Beta: no page errors", not errs, str(errs)); pg.close()
    # a found board is named as it names itself: "GSP32-C Beta V131" from a Beta, "GSP32-C V132" from a Stable build
    for init, want, bad in (("window.__gspc = '131'", "GSP32-C Beta V131 Found", None), ("window.__gspc = '132'; window.__gspcStable = true", "GSP32-C V132 Found", "Beta")):
        pg = b.new_page(viewport={"width": 1280, "height": 900}); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script(init)
        pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://127.0.0.1:8904/index.html"); pg.wait_for_timeout(300)
        pg.click("#connect"); pg.wait_for_timeout(100)
        pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
        pg.wait_for_timeout(2500)
        st = pg.inner_text("#board-state")
        check("found: " + want, want in st and (bad is None or bad not in st), st)
        if bad:   # its Improv answer (Set Up Wi-Fi asks for it) keeps the Stable name
            pg.wait_for_timeout(1500); st = pg.inner_text("#board-state")
            check("found: still " + want + " after Improv", "GSP32-C V132" in st and "Beta" not in st, st)
        check("found: no page errors (" + want + ")", not errs, str(errs)); pg.close()
print("fails", fails); sys.exit(1 if fails else 0)
