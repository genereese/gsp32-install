""" Flasher 115.55 (Gene t3088u): GSP32-C V137.10 (dccdc26) stays the Stable default; Beta V137.12 (b8b4eed) is listed
next to it (streamed ZIP downloads for multi-file/folder; single-file Download unchanged).
Shape: test_flasher_11554 (stable + beta). """
import sys, time, http.server, threading, functools, os, json, re, urllib.request, urllib.error
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); here = os.path.dirname(os.path.abspath(__file__))
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8908), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, "" if ok else extra); sys.stdout.flush()

versions = json.load(open(os.path.join(site, "versions.json")))
check("versions.json: two entries: GSP32-C V137.10 Stable (no channel) first, then GSP32-C Beta V137.12", len(versions) == 2
      and re.fullmatch(r"GSP32-C Beta V137\.12 \([0-9a-f]{7,}\)", versions[1]["label"]) and versions[1].get("channel") == "gspc-beta"
      and versions[1]["manifest"] == "manifest-gspc-v137.12.json" and versions[1].get("line") == "GSP32-C" and re.fullmatch(r"GSP32-C V137\.10 \([0-9a-f]{7,}\)", versions[0]["label"])
      and "channel" not in versions[0] and versions[0].get("line") == "GSP32-C" and versions[0]["manifest"] == "manifest-gspc-v137.10.json", str(versions))
check("label has no Beta and no (before Projects)", "Beta" not in versions[0]["label"] and "before Projects" not in versions[0]["label"], versions[0]["label"])
check("versions.json version is the label's hash", all(e["label"].endswith("(%s)" % e["version"]) for e in versions), str(versions))
check("V137.10 Stable still dccdc26", versions[0]["version"] == "dccdc26", versions[0]["version"])
check("no update flag, no note", all("update" not in e and "note" not in e for e in versions))
mans = sorted(n for n in os.listdir(site) if n.startswith("manifest"))
check("manifests: V137.10 and Beta V137.12 only", mans == ["manifest-gspc-v137.10.json", "manifest-gspc-v137.12.json"], str(mans))
fw = sorted(os.listdir(os.path.join(site, "firmware")))
check("firmware/: gspc-v137.10 and gspc-v137.12 only", fw == ["gspc-v137.10", "gspc-v137.12"], str(fw))
import hashlib, subprocess
for n in sorted(os.listdir(os.path.join(site, "firmware/gspc-v137.10"))):   # Stable V137.10 images unchanged since Flasher 115.53
    old = subprocess.run(["git", "-C", site, "show", "114e179:firmware/gspc-v137.10/" + n], capture_output=True).stdout
    check("V137.10 %s unchanged since 115.53" % n, old and hashlib.sha256(old).digest() == hashlib.sha256(open(os.path.join(site, "firmware/gspc-v137.10", n), "rb").read()).digest())
for v, entry in (("137.10", versions[0]), ("137.12", versions[1])):
    m = json.load(open(os.path.join(site, "manifest-gspc-v%s.json" % v)))
    parts = [p["path"] for b in m["builds"] for p in b["parts"]]
    check("V%s: five images there, in firmware/gspc-v%s/" % (v, v), len(parts) == 5 and all(os.path.exists(os.path.join(site, p)) and p.startswith("firmware/gspc-v%s/" % v) for p in parts), str(parts))
    check("V%s manifest names itself as the versions.json label" % v, m["version"] == entry["label"], m["version"])
    check("V%s manifest: ESP32 at 4096, C3/S3 at 0" % v, all(p["offset"] == (4096 if b["chipFamily"] == "ESP32" else 0) for b in m["builds"] for p in b["parts"]))
    check("V%s manifest: ESP32, three S3 and the C3, every build improv" % v, sorted(b["chipFamily"] for b in m["builds"]) == ["ESP32", "ESP32-C3", "ESP32-S3", "ESP32-S3", "ESP32-S3"] and all(b.get("improv") is True for b in m["builds"]))
    esp = open(os.path.join(site, "firmware/gspc-v%s/gsp32c-esp32.bin" % v), "rb").read(4)
    check("V%s ESP32 image: 80 MHz flash header" % v, esp[0] == 0xE9 and esp[3] & 0x0F == 0x0F, esp.hex())
for n in os.listdir(os.path.join(site, "firmware/gspc-v137.12")):
    data = open(os.path.join(site, "firmware/gspc-v137.12", n), "rb").read()
    check("V137.12 %s names itself GSP32-C Beta V137.12" % n, b"GSP32-C Beta V137.12" in data and b"V137.10" not in data.split(b"GSP32-C Beta V137.12")[0][-64:])
html = open(os.path.join(site, "index.html"), encoding="utf-8").read()
check("cache tag 115.55-s137.10-c137.12 on style.css, app.js, tour.js", html.count("?v=115.55-s137.10-c137.12\"") == 3)
def status(path):
    try: return urllib.request.urlopen("http://127.0.0.1:8908/" + path).status
    except urllib.error.HTTPError as e: return e.code
for path in ("manifest-gspc-v137.8.json", "firmware/gspc-v137.8/gsp32c-esp32.bin", "firmware/gspc-v137.8/gsp32c-esp32c3.bin", "firmware/gspc-v137.8/gsp32c-esp32s3.bin", "manifest-gspc-v137.7.json", "firmware/gspc-v137.7/gsp32c-esp32.bin", "firmware/gspc-v137.7/gsp32c-esp32c3.bin", "manifest-gspc-v137.6.json", "firmware/gspc-v137.6/gsp32c-esp32.bin", "firmware/gspc-v137.6/gsp32c-esp32c3.bin", "manifest-gspc-v137.4.json", "firmware/gspc-v137.4/gsp32c-esp32.bin", "manifest-gspc-v137.1.json", "firmware/gspc-v137.1/gsp32c-esp32.bin", "manifest-gspc-v137.3.json", "firmware/gspc-v137.3/gsp32c-esp32.bin", "firmware/gspc-v137.3/gsp32c-esp32c3.bin", "firmware/gspc-v137.3/gsp32c-esp32s3.bin", "manifest-gspc-v137.2.json", "firmware/gspc-v137.2/gsp32c-esp32.bin", "firmware/gspc-v137.2/gsp32c-esp32c3.bin", "firmware/gspc-v137.2/gsp32c-esp32s3.bin", "manifest.json", "manifest-beta.json", "manifest-gspc-beta.json", "manifest-gspc-v129.json", "manifest-gspc-v118.json", "firmware/gsp32-esp32.bin", "firmware/beta/gsp32-esp32.bin", "firmware/gspc-v129/gsp32c-esp32.bin", "manifest-gspc-v136.json", "firmware/gspc-v136/gsp32c-esp32.bin", "firmware/gspc-v136/gsp32c-esp32c3.bin", "firmware/gspc-v136/gsp32c-esp32s3.bin", "manifest-gspc-v141.1.json", "firmware/gspc-v141.1/gsp32c-esp32.bin", "firmware/gspc-v141.1/gsp32c-esp32c3.bin", "firmware/gspc-v141.1/gsp32c-esp32s3.bin", "firmware/gspc-v141.1/gsp32c-esp32s3-n8r8.bin", "firmware/gspc-v141.1/gsp32c-esp32s3-n8r2.bin", "manifest-gspc-v138.json", "firmware/gspc-v138/gsp32c-esp32.bin", "manifest-gspc-v139.json", "firmware/gspc-v139/gsp32c-esp32.bin", "manifest-gspc-v140.json", "firmware/gspc-v140/gsp32c-esp32.bin", "manifest-gspc-v141.json", "firmware/gspc-v141/gsp32c-esp32.bin", "manifest-gspc-v131.json", "firmware/gspc-v131/gsp32c-esp32.bin", "manifest-gspc-v132.json", "firmware/gspc-v132/gsp32c-esp32.bin", "manifest-gspc-v130.json", "manifest-gspc-v133.json", "manifest-gspc-v134.json", "firmware/gspc-v130/gsp32c-esp32.bin", "firmware/gspc-v133/gsp32c-esp32.bin", "firmware/gspc-v134/gsp32c-esp32.bin", "manifest-gspc-v135.json", "firmware/gspc-v135/gsp32c-esp32.bin", "manifest-gspc-v135.1.json", "firmware/gspc-v135.1/gsp32c-esp32.bin", "manifest-gspc-v136.1.json", "firmware/gspc-v136.1/gsp32c-esp32.bin", "manifest-gspc-v136.2.json", "firmware/gspc-v136.2/gsp32c-esp32.bin", "manifest-gspc-v137.json", "firmware/gspc-v137/gsp32c-esp32.bin", "manifest-v84.json", "manifest-v85.json", "manifest-v99.json", "firmware/v84/gsp32-esp32.bin", "firmware/v99/gsp32-esp32.bin"):
    check("gone: " + path, status(path) == 404, status(path))

def pick(pg, value):   # the dropdown sits in the install step (hidden before connect): set it as a pick does
    pg.evaluate("v => { const s = document.getElementById('release-channel'); s.value = v; s.dispatchEvent(new Event('change')); }", value); pg.wait_for_timeout(200)

# V132 (a): Gene's V131 first boot after a fresh install (his log, 28 Oct 11:30 MT): no Wi-Fi saved, main.py running
GENE131 = [[150, "ets Jul 29 2019 12:21:46\r\n\r\nrst:0x1 (POWERON_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)\r\n"], [600, "Performing initial setup\r\n"],
           [2500, "\r\nGSP32-C V137.10 on ESP32 (GSP32-C ESP32), boot 1, reset: power-on\r\n", True],
           [2600, "GSP32-C: no Wi-Fi set; gsp.wifi('name', 'password') sets it\r\n"], [3200, "main.py running\r\n"]]
def gspc_page(init):
    pg = b.new_page(viewport={"width": 1280, "height": 900}); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script(init)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.__errs = errs
    pg.goto("http://127.0.0.1:8908/index.html"); pg.wait_for_timeout(300)
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
        pg.goto("http://127.0.0.1:8908/index.html"); pg.wait_for_timeout(800)
        w = " @%d" % width
        check("footer Flasher Version 115.55" + w, "Flasher Version 115.55" in pg.text_content(".flasher-version"))
        check("Release dropdown shown (Stable and the Beta)" + w, pg.evaluate("!document.querySelector('.release-field').hidden"))
        usable = pg.evaluate("[...document.querySelectorAll('#release-channel option')].filter(o => !o.hidden && !o.disabled).map(o => o.value + '=' + o.textContent.trim())")
        check("picks: Stable, GSP32-C Beta V137.12" + w, usable == ["stable=Stable", "gspc-137.12=GSP32-C Beta V137.12"], str(usable))
        check("Stable is the default pick" + w, pg.eval_on_selector("#release-channel", "e => e.value") == "stable")
        check("Installs GSP32-C V137.10" + w, pg.text_content("#version").strip() == "GSP32-C V137.10", pg.text_content("#version"))
        pick(pg, "gspc-137.12")
        check("Beta pick: Installs GSP32-C Beta V137.12" + w, pg.text_content("#version").strip() == "GSP32-C Beta V137.12", pg.text_content("#version"))
        pick(pg, "stable")
        check("back to Stable: Installs GSP32-C V137.10" + w, pg.text_content("#version").strip() == "GSP32-C V137.10", pg.text_content("#version"))
        check("no old manifest asked for" + w, not any(re.search(r"/manifest(-beta|-gspc-beta|-gspc-v1[123][0-4][.\d]*|-gspc-v1[12]\d[.\d]*|-v\d+)?\.json", u) for u in asked), str([u for u in asked if "manifest" in u]))
        if width < 500:
            check("no sideways scroll on a phone", pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"))
            check("no page errors" + w, not errs, str(errs)); pg.close(); continue
        pg.click("#connect"); pg.wait_for_timeout(100)
        pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
        pg.wait_for_timeout(4500); pg.click("#install-btn"); pg.wait_for_timeout(500)
        check("after connect: Installs GSP32-C V137.10", pg.text_content("#version").strip() == "GSP32-C V137.10", pg.text_content("#version"))
        asked.clear()
        pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(3000)
        man = [u for u in asked if "manifest" in u]
        check("Erase and Install loads manifest-gspc-v137.10.json", any("manifest-gspc-v137.10.json" in u for u in man) and not any(re.search(r"v13[0-5]\b", u) for u in man), str(man))
        img = [u for u in asked if u.endswith(".bin")]
        check("images from firmware/gspc-v137.10/", bool(img) and all("/firmware/gspc-v137.10/" in u for u in img), str(img))
        check("no page errors" + w, not errs, str(errs))
        pg.close()
    # Flasher 115.55: the Beta pick installs Beta V137.12 from its own files
    pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script("window.__ver = '84';")
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    asked = []; errs = []
    pg.on("request", lambda r: asked.append(r.url)); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:8908/index.html"); pg.wait_for_timeout(800)
    pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(4500); pg.click("#install-btn"); pg.wait_for_timeout(500)
    check("Beta: Release dropdown visible in the install step", pg.locator(".release-field").is_visible())
    pg.select_option("#release-channel", "gspc-137.12"); pg.wait_for_timeout(300)
    check("Beta: Installs GSP32-C Beta V137.12", pg.text_content("#version").strip() == "GSP32-C Beta V137.12", pg.text_content("#version"))
    asked.clear(); pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(3000)
    man = [u for u in asked if "manifest" in u]
    check("Beta: Erase and Install loads manifest-gspc-v137.12.json", any("manifest-gspc-v137.12.json" in u for u in man) and not any("v137.10" in u for u in man), str(man))
    img = [u for u in asked if u.endswith(".bin")]
    check("Beta: images from firmware/gspc-v137.12/", bool(img) and all("/firmware/gspc-v137.12/" in u for u in img), str(img))
    check("Beta: no page errors", not errs, str(errs)); pg.close()
    # a found board is named as it names itself: "GSP32-C Beta V131" from a Beta, "GSP32-C V132" from a Stable build
    for init, want, bad in (("window.__gspc = '131'", "GSP32-C Beta V131 Found", None), ("window.__gspc = '132'; window.__gspcStable = true", "GSP32-C V132 Found", "Beta")):
        pg = b.new_page(viewport={"width": 1280, "height": 900}); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script(init)
        pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://127.0.0.1:8908/index.html"); pg.wait_for_timeout(300)
        pg.click("#connect"); pg.wait_for_timeout(100)
        pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
        pg.wait_for_timeout(2500)
        st = pg.inner_text("#board-state")
        check("found: " + want, want in st and (bad is None or bad not in st), st)
        if bad:   # its Improv answer (Set Up Wi-Fi asks for it) keeps the Stable name
            pg.wait_for_timeout(1500); st = pg.inner_text("#board-state")
            check("found: still " + want + " after Improv", "GSP32-C V132" in st and "Beta" not in st, st)
        check("found: no page errors (" + want + ")", not errs, str(errs)); pg.close()
    # V132 (a) 1. Gene's flow (115.43: on V137.10, the Stable default): Erase and Install (the REPL echo on, as on the real board), Set Up
    #  Wi-Fi as soon as main.py runs: the first scan lists the networks, no Ctrl-C, no restart, nothing echoed
    pg = gspc_page("window.__gspc = '130'; window.__gspcStable = true; window.__replEcho = true;")
    pg.click("#install-btn"); pg.wait_for_timeout(400)
    check("V132 (a) Gene's flow: installs GSP32-C V137.10 (the Stable default)", pg.text_content("#version").strip() == "GSP32-C V137.10", pg.text_content("#version"))
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
