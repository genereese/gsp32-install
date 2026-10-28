""" Flasher 115.27 (Gene, 2026-10-28): GSP32-C V133 is the Stable default (manifest-gspc-v133.json, firmware/gspc-v133);
V130, the Stable before it, is the Previous pick ("Previous (GSP32-C V130)"), as classic Version 114.2 was in 115.23;
Beta V132 is gone (its manifest and images 404). Footer/tag 115.27-s133-p130. The Wi-Fi checks below (115.26) now run
on the V133 install. Earlier:
Flasher 115.26 (GSP32-C V132 (a), Gene's ESP32, 2026-10-28): the first Wi-Fi setup after a fresh install of
GSP32-C Beta V131 found no networks (Scan Again did). 115.10-115.25 sent Ctrl-C before Wi-Fi setup; at the >>> prompt
the board's REPL echoed each packet's "IMPROV" (plus rub-outs) ahead of the answer, and takeSerialBytes read the echo
as a packet with length '[' (91), holding the real answers back. Now: no Ctrl-C (classic GSP32's rule; GSP32-C takes
Improv while main.py runs), and a header whose version byte isn't 1 or whose type isn't 1-4 is text at once. Checked
below: Gene's flow lists the networks on the first scan with no Ctrl-C and no restart; a board already at >>> (echoing)
does too; takeSerialBytes lets the echo go. Footer/tag 115.26. Earlier (115.25, unchanged):
Flasher 115.25 (Gene, 2026-10-28): GSP32-C V130 stays the Stable pick and GSP32-C Beta V131 is listed next to it
(its own pick in the GSP32-C group of the Release dropdown). The unlisted rollbacks V84, V85 and V99 are gone (Gene:
"remove all previous versions"; git history keeps them, tests/oldsite.py brings them back for test_v79). The page
names a board from its start-up line or Improv answer in both forms: "GSP32-C Beta V131" and, from a Stable build,
"GSP32-C V132". Replaces test_flasher_11524 (V130 the only entry). No update flag, no note.
Flasher 115.26 (Gene): GSP32-C Beta V132 replaces Beta V131 (manifest-gspc-v132.json, firmware/gspc-v132); V130 stays the Stable default """
import sys, time, http.server, threading, functools, os, json, re, urllib.request, urllib.error
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); here = os.path.dirname(os.path.abspath(__file__))
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8904), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, "" if ok else extra); sys.stdout.flush()

versions = json.load(open(os.path.join(site, "versions.json")))
check("versions.json: GSP32-C V133 Stable first (no channel), then GSP32-C V130 (previous)", len(versions) == 2 and re.fullmatch(r"GSP32-C V133 \([0-9a-f]{7,}\)", versions[0]["label"])
      and "channel" not in versions[0] and versions[0].get("line") == "GSP32-C" and versions[0]["manifest"] == "manifest-gspc-v133.json"
      and re.fullmatch(r"GSP32-C V130 \([0-9a-f]{7,}\)", versions[1]["label"]) and versions[1].get("channel") == "previous"
      and versions[1].get("line") == "GSP32-C" and versions[1]["manifest"] == "manifest-gspc-v130.json"
      and not any("Beta" in e["label"] for e in versions), str(versions))
check("no update flag, no note", all("update" not in e and "note" not in e for e in versions))
mans = sorted(n for n in os.listdir(site) if n.startswith("manifest"))
check("manifests: V130 and V133 only (no rollbacks, no Beta)", mans == ["manifest-gspc-v130.json", "manifest-gspc-v133.json"], str(mans))
fw = sorted(os.listdir(os.path.join(site, "firmware")))
check("firmware/: gspc-v130 and gspc-v133 only", fw == ["gspc-v130", "gspc-v133"], str(fw))
for v in ("130", "133"):
    m = json.load(open(os.path.join(site, "manifest-gspc-v%s.json" % v)))
    parts = [p["path"] for b in m["builds"] for p in b["parts"]]
    check("V%s: five images there, in firmware/gspc-v%s/" % (v, v), len(parts) == 5 and all(os.path.exists(os.path.join(site, p)) and p.startswith("firmware/gspc-v%s/" % v) for p in parts), str(parts))
    check("V%s manifest names itself (a Stable name, no Beta)" % v, re.fullmatch(r"GSP32-C V%s \([0-9a-f]{7,}\)" % v, m["version"]) is not None, m["version"])
    check("V%s manifest: ESP32 at 4096, C3/S3 at 0" % v, all(p["offset"] == (4096 if b["chipFamily"] == "ESP32" else 0) for b in m["builds"] for p in b["parts"]))
html = open(os.path.join(site, "index.html"), encoding="utf-8").read()
tag = re.search(r"\?v=(115\.27-[\w.-]+)\"", html)
check("cache tag 115.27-* on style.css, app.js, tour.js", bool(tag) and html.count("?v=" + tag.group(1) + "\"") == 3, tag and tag.group(1))
def status(path):
    try: return urllib.request.urlopen("http://127.0.0.1:8904/" + path).status
    except urllib.error.HTTPError as e: return e.code
for path in ("manifest.json", "manifest-beta.json", "manifest-gspc-beta.json", "manifest-gspc-v129.json", "manifest-gspc-v118.json",
             "firmware/gsp32-esp32.bin", "firmware/beta/gsp32-esp32.bin", "firmware/gspc-v129/gsp32c-esp32.bin",
             "manifest-gspc-v131.json", "firmware/gspc-v131/gsp32c-esp32.bin", "manifest-gspc-v132.json", "firmware/gspc-v132/gsp32c-esp32.bin", "firmware/gspc-v132/gsp32c-esp32s3.bin", "manifest-v84.json", "manifest-v85.json", "manifest-v99.json", "firmware/v84/gsp32-esp32.bin", "firmware/v99/gsp32-esp32.bin"):
    check("gone: " + path, status(path) == 404, status(path))

def pick(pg, value):   # the dropdown sits in the install step (hidden before connect): set it as a pick does
    pg.evaluate("v => { const s = document.getElementById('release-channel'); s.value = v; s.dispatchEvent(new Event('change')); }", value); pg.wait_for_timeout(200)

# V132 (a): Gene's V131 first boot after a fresh install (his log, 28 Oct 11:30 MT): no Wi-Fi saved, main.py running
GENE131 = [[150, "ets Jul 29 2019 12:21:46\r\n\r\nrst:0x1 (POWERON_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)\r\n"], [600, "Performing initial setup\r\n"],
           [2500, "\r\nGSP32-C V133 on ESP32 (GSP32-C ESP32), boot 1, reset: power-on\r\n", True],
           [2600, "GSP32-C: no Wi-Fi set; gsp.wifi('name', 'password') sets it\r\n"], [3200, "main.py running\r\n"]]
def gspc_page(init):
    pg = b.new_page(viewport={"width": 1280, "height": 900}); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script(init)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.__errs = errs
    pg.goto("http://127.0.0.1:8904/index.html"); pg.wait_for_timeout(300)
    pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(2500); return pg

with sync_playwright() as p:
    b = p.chromium.launch()
    for width in (1100, 390):
        pg = b.new_page(viewport={"width": width, "height": 900}); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script("window.__ver = '84';")
        pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
        asked = []; errs = []
        pg.on("request", lambda r: asked.append(r.url)); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://127.0.0.1:8904/index.html"); pg.wait_for_timeout(800)
        w = " @%d" % width
        check("footer Flasher Version 115.27" + w, "Flasher Version 115.27" in pg.text_content(".flasher-version"))
        check("Release dropdown shown (Stable and Previous)" + w, pg.evaluate("!document.querySelector('.release-field').hidden"))   # (in the install step, shown after connect)
        usable = pg.evaluate("[...document.querySelectorAll('#release-channel option')].filter(o => !o.hidden && !o.disabled).map(o => o.value + '=' + o.textContent.trim())")
        check("picks: Stable, Previous (GSP32-C V130); no Beta" + w, usable == ["stable=Stable", "previous=Previous (GSP32-C V130)"], str(usable))
        check("Stable is the default pick" + w, pg.eval_on_selector("#release-channel", "e => e.value") == "stable")
        check("Installs GSP32-C V133" + w, pg.text_content("#version").strip() == "GSP32-C V133", pg.text_content("#version"))
        check("no old manifest asked for" + w, not any(re.search(r"/manifest(-beta|-gspc-beta|-gspc-v1[12]\d[.\d]*|-v\d+)?\.json", u) for u in asked), str([u for u in asked if "manifest" in u]))
        pick(pg, "previous")
        check("Previous pick: Installs GSP32-C V130" + w, pg.text_content("#version").strip() == "GSP32-C V130", pg.text_content("#version"))
        pick(pg, "stable")
        if width < 500:
            check("no sideways scroll on a phone", pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"))
            check("no page errors" + w, not errs, str(errs)); pg.close(); continue
        pg.click("#connect"); pg.wait_for_timeout(100)
        pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
        pg.wait_for_timeout(4500); pg.click("#install-btn"); pg.wait_for_timeout(500)
        check("after connect: Installs GSP32-C V133", pg.text_content("#version").strip() == "GSP32-C V133", pg.text_content("#version"))
        asked.clear()
        pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(3000)
        man = [u for u in asked if "manifest" in u]
        check("Erase and Install loads manifest-gspc-v133.json", any("manifest-gspc-v133.json" in u for u in man) and not any("v130" in u for u in man), str(man))
        img = [u for u in asked if u.endswith(".bin")]
        check("images from firmware/gspc-v133/", bool(img) and all("/firmware/gspc-v133/" in u for u in img), str(img))
        check("no page errors" + w, not errs, str(errs))
        pg.close()
    # the Previous pick installs V130 from its own files
    pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script("window.__ver = '84';")
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    asked = []; errs = []
    pg.on("request", lambda r: asked.append(r.url)); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:8904/index.html"); pg.wait_for_timeout(800)
    pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(4500); pg.click("#install-btn"); pg.wait_for_timeout(500)
    check("Previous: Release dropdown visible in the install step", pg.locator(".release-field").is_visible())
    pg.select_option("#release-channel", "previous"); pg.wait_for_timeout(300)
    check("Previous: after connect still Installs GSP32-C V130", pg.text_content("#version").strip() == "GSP32-C V130", pg.text_content("#version"))
    asked.clear(); pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(3000)
    man = [u for u in asked if "manifest" in u]; img = [u for u in asked if u.endswith(".bin")]
    check("Previous: Erase and Install loads manifest-gspc-v130.json", any("manifest-gspc-v130.json" in u for u in man) and not any("v133" in u for u in man), str(man))
    check("Previous: images from firmware/gspc-v130/", bool(img) and all("/firmware/gspc-v130/" in u for u in img), str(img))
    check("Previous: no page errors", not errs, str(errs)); pg.close()
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
    # V132 (a) 1. Gene's flow (115.27: on the Stable default, V133): Erase and Install (the REPL echo on, as on the real board), Set Up
    #  Wi-Fi as soon as main.py runs: the first scan lists the networks, no Ctrl-C, no restart, nothing echoed
    pg = gspc_page("window.__gspc = '130'; window.__gspcStable = true; window.__replEcho = true;")
    pg.click("#install-btn"); pg.wait_for_timeout(400)
    check("V132 (a) Gene's flow: installs GSP32-C V133 (the default)", pg.text_content("#version").strip() == "GSP32-C V133", pg.text_content("#version"))
    pg.evaluate("window.__bootScript = %s" % json.dumps(GENE131)); pg.check("#erase-ok"); pg.click("#start-install")
    pg.wait_for_function("/main\\.py running/.test(document.getElementById('console-out').innerText)", timeout=60000); pg.wait_for_timeout(300)
    resets = len([x for x in pg.evaluate("window.__log") if "requestToSend" in str(x)])
    t0 = time.time(); pg.click("#wifi-setup")
    pg.wait_for_function("/Pick your network|No networks found|did not answer/.test(document.getElementById('board-status').innerText)", timeout=40000)
    took = time.time() - t0; st = pg.inner_text("#board-status")
    check("V132 (a) Gene's flow: first scan lists the networks", "Pick your network" in st and pg.locator("#wifi-list li").count() == 2, st)
    check("V132 (a) Gene's flow: in a few seconds (115.25: 20 s scan timeout)", took < 8, "%.1f s" % took)
    check("V132 (a) Gene's flow: no Ctrl-C, no console note about it", pg.evaluate("window.__ctrl1 || 0") == 0 and "Ctrl-C stops main.py" not in pg.inner_text("#console-out"))
    check("V132 (a) Gene's flow: no restart (no RTS pulse after Set Up Wi-Fi)", len([x for x in pg.evaluate("window.__log") if "requestToSend" in str(x)]) == resets)
    check("V132 (a) Gene's flow: no REPL echo (main.py kept running)", (pg.evaluate("window.__echoes") or 0) == 0)
    check("V132 (a) Gene's flow: no page errors", not pg.__errs, str(pg.__errs)); pg.close()
    # V132 (a) 2. A board already at >>> (the person sent Ctrl-C): every packet is echoed ahead of its answer, and the
    #  first scan still lists the networks (115.25 held the answers behind the echo)
    pg = gspc_page("window.__gspc = '131'; window.__replEcho = true;")
    t0 = time.time(); pg.click("#wifi-setup")
    pg.wait_for_function("/Pick your network|No networks found|did not answer/.test(document.getElementById('board-status').innerText)", timeout=60000)
    took = time.time() - t0; st = pg.inner_text("#board-status")
    check("V132 (a) at >>> with the echo: first scan lists the networks", "Pick your network" in st and pg.locator("#wifi-list li").count() == 2, st)
    check("V132 (a) at >>> with the echo: echoes really came", (pg.evaluate("window.__echoes") or 0) >= 2, pg.evaluate("window.__echoes"))
    check("V132 (a) at >>> with the echo: quick, no restart retry", took < 8, "%.1f s" % took)
    # takeSerialBytes itself (the page's own module): the echo is text at once, the answer behind it a packet
    r = pg.evaluate("""async () => { const m = await import(document.querySelector('script[type=module]').src);
        const enc = new TextEncoder(); const echo = enc.encode('IMPROV' + '\\b\\x1b[K'.repeat(6));
        const ans = m.buildImprovPacket(1, [2]); const all = new Uint8Array(echo.length + ans.length); all.set(echo, 0); all.set(ans, echo.length);
        const t = m.takeSerialBytes(all); const half = m.takeSerialBytes(enc.encode('IMPROV'));
        const v1 = m.takeSerialBytes(Uint8Array.from([73,77,80,82,79,86,1]));
        return {packets: t.packets.length, type: t.packets.length ? t.packets[0].type : -1, rest: t.rest.length, textLen: t.text.length, half: half.rest.length, v1: v1.rest.length}; }""")
    check("takeSerialBytes: echo then a state answer -> 1 packet, nothing held", r["packets"] == 1 and r["type"] == 1 and r["rest"] == 0 and r["textLen"] == 6 + 24, r)
    check("takeSerialBytes: a bare IMPROV or IMPROV+1 is still held (could be a packet)", r["half"] == 6 and r["v1"] == 7, r)
    check("V132 (a) at >>>: no page errors", not pg.__errs, str(pg.__errs)); pg.close()
print("fails", fails); sys.exit(1 if fails else 0)
