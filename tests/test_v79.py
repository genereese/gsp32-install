# Version 79: multi-chip install; unsupported chip/flash shows Title-Case warn-box (no write);
#  subtle board-details; board-model telemetry (no MAC) once per connect
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
fam = {}
for b in m["builds"]: fam.setdefault(b["chipFamily"], b["parts"])  # Version 83: first S3 build is the 16 MB one
s3_8 = {b["psramMb"]: os.path.getsize(os.path.join(site, b["parts"][0]["path"])) for b in m["builds"] if b.get("flashMb") == 8}
check("V83: 8 MB S3 builds N8R8 + N8R2, 8 MB each", s3_8 == {8: 0x800000, 2: 0x800000}, str(s3_8))
check("manifest: ESP32 and ESP32-S3 builds", sorted(fam) == ["ESP32", "ESP32-S3"], str(sorted(fam)))
check("both at offset 0", all(len(p) == 1 and p[0]["offset"] == 0 for p in fam.values()))
sz = {f: os.path.getsize(os.path.join(site, p[0]["path"])) for f, p in fam.items()}
check("ESP32 image 4 MB, S3 image 16 MB", sz == {"ESP32": 0x400000, "ESP32-S3": 0x1000000}, str(sz))
s3img = open(os.path.join(site, fam["ESP32-S3"][0]["path"]), "rb").read(4)
check("S3 image starts with a bootloader header at 0", s3img[0] == 0xE9)
v = json.load(open(os.path.join(site, "versions.json")))
st = [e for e in v if e.get("channel", "stable") == "stable"]; bt = [e for e in v if e.get("channel") == "beta"]
check("versions.json: Stable Version 85 only (+ at most one Beta)", len(st) == 1 and st[0]["label"].startswith("Version 85") and st[0]["manifest"] == "manifest.json" and len(bt) <= 1)
# Version 84: Version 84 stays (V85) as the single unlisted rollback (manifest-v84.json, firmware/v84/, all four images), not in versions.json
check("versions.json: Beta is Version 92 (manifest-beta.json)", len(bt) == 1 and bt[0]["label"].startswith("Version 92") and bt[0]["manifest"] == "manifest-beta.json")
bm = json.load(open(os.path.join(site, "manifest-beta.json")))
check("manifest-beta.json: Version 92, firmware/beta images exist", bm["version"].startswith("Version 92") and all(os.path.exists(os.path.join(site, p["path"])) and p["path"].startswith("firmware/beta/") for b in bm["builds"] for p in b["parts"]))
rb = json.load(open(os.path.join(site, "manifest-v84.json")))
check("rollback manifest-v84.json points at firmware/v84 images that exist", all(os.path.exists(os.path.join(site, p["path"])) and p["path"].startswith("firmware/v84/") for b in rb["builds"] for p in b["parts"]))
check("rollback not listed in versions.json", all(x["manifest"] != "manifest-v84.json" for x in v))
js = open(os.path.join(site, "app.js")).read()
html = open(os.path.join(site, "index.html")).read()
css = open(os.path.join(site, "style.css")).read()
check("erase wording per chip (S3 16 MB about a minute)", 'family === "ESP32-S3" ? "about a minute" : "about 15 seconds"' in js)
check("cache-bust 85-fw85 everywhere", html.count("?v=85-fw85") == 3, str(html.count("?v=85-fw85")))
check("no Compatible Boards card", 'id="compatible"' not in html)
check("compat-notice warn-box present", 'id="compat-notice"' in html and "compat-notice" in css)
check("board-details MAC-style", 'id="board-details"' in html and "board-details" in css and "formatBoardDetails" in js)
check("no privacy note", 'board-privacy' not in html and 'board-privacy' not in css and "no MAC or personal data" not in html)
check("compatIssue + showCompatNotice", "compatIssue" in js and "showCompatNotice" in js and "This Board Is Not Supported" in js)
check("telemetry hook", "reportBoardTelemetry" in js and "gsp32-telemetry.genereese.workers.dev/log" in js)
check("probe on connect", "probeBoardOnConnect" in js)

TELEMETRY = "https://gsp32-telemetry.genereese.workers.dev/log"

def run(b, chip, flash_kb=None, usb=None, auto_install=True):
    pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.add_init_script(path=here + "/mock.js")
    init = "window.__ver = '47'; window.__log = []; window.__telemetry = [];"
    if chip: init += "window.__chip = %s;" % json.dumps(chip)
    if flash_kb is not None: init += "window.__flashKb = %s;" % json.dumps(flash_kb)
    if usb is not None: init += "window.__usb = %s;" % json.dumps(usb)
    # Mock fetch for telemetry only; pass everything else through
    init += """
    (() => {
      const real = window.fetch.bind(window);
      window.fetch = (input, init) => {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        if (url.indexOf('gsp32-telemetry') >= 0 && url.indexOf('/log') >= 0) {
          let body = null;
          try { body = JSON.parse(init && init.body || '{}'); } catch (e) { body = init && init.body; }
          window.__telemetry.push({ url, method: (init && init.method) || 'GET', body });
          return Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
        }
        return real(input, init);
      };
    })();
    """
    pg.add_init_script(init)
    pg.add_init_script("""window.__status = []; addEventListener('DOMContentLoaded', () => { const el = document.getElementById('board-status');
      new MutationObserver(() => window.__status.push(el.textContent)).observe(el, {childList: true, characterData: true, subtree: true}); });""")
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    # Also block real telemetry network just in case
    pg.route("**/gsp32-telemetry.genereese.workers.dev/**", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true}'))
    pg.goto("http://127.0.0.1:8789/index.html"); pg.wait_for_timeout(300); pg.click("#connect")
    # Wait for connect-time probe to finish (stats or notice or console message)
    for _ in range(80):
        done = pg.evaluate("""() => {
          const d = document.getElementById('board-details');
          const n = document.getElementById('compat-notice');
          const out = document.getElementById('console-out');
          const text = out ? out.textContent : '';
          return (d && !d.hidden && /flash|Core|MHz|CP210|CH3/i.test(d.textContent||''))
            || (n && !n.hidden)
            || /Reading board info|Could not read the board|Board:/.test(text);
        }""")
        if done: break
        pg.wait_for_timeout(100)
    pg.wait_for_timeout(300)
    details_early = pg.evaluate("(() => { const el = document.getElementById('board-details'); return el && !el.hidden ? el.textContent : ''; })()")
    tel_early = pg.evaluate("window.__telemetry || []")
    # Boot-log simulation (after probe released the port back to run)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(4500)
    # Skip install click when incompatible (Install disabled)
    can_install = auto_install and pg.evaluate("!document.getElementById('install-btn').disabled")
    if can_install:
        pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(6000)
    else:
        pg.wait_for_timeout(200)
    log = [l for l in pg.evaluate("window.__log") if isinstance(l, str)]
    notice = pg.evaluate("""() => {
      const box = document.getElementById('compat-notice');
      if (!box || box.hidden) return null;
      return { title: document.getElementById('compat-notice-title').textContent,
               text: document.getElementById('compat-notice-text').textContent };
    }""")
    details = pg.evaluate("(() => { const el = document.getElementById('board-details'); return el && !el.hidden ? el.textContent : ''; })()")
    mac = pg.evaluate("(() => { const el = document.getElementById('board-mac'); return el && !el.hidden ? el.textContent : ''; })()")
    tel = pg.evaluate("window.__telemetry")
    return pg, log, pg.evaluate("window.__status"), notice, details, mac, details_early, tel

ALLOWED = {"chip", "compatible", "revision", "cores", "flash_mb", "psram", "crystal_mhz", "usb_bridge", "flasher_version", "browser"}

def check_tel(name, tel, expect_compatible, expect_chip_substr=None):
    check(name + ": one POST", len(tel) == 1, str(tel))
    if not tel: return
    body = tel[0]["body"]
    check(name + ": POST method", (tel[0].get("method") or "").upper() == "POST")
    check(name + ": required chip+compatible", isinstance(body.get("chip"), str) and isinstance(body.get("compatible"), bool), str(body))
    check(name + ": compatible value", body.get("compatible") is expect_compatible, str(body.get("compatible")))
    if expect_chip_substr:
        check(name + ": chip name", expect_chip_substr in body.get("chip", ""), str(body.get("chip")))
    check(name + ": no MAC", "mac" not in {k.lower() for k in body} and "f8:b3:b7" not in json.dumps(body).lower(), str(body))
    check(name + ": only known keys", set(body) <= ALLOWED, str(set(body) - ALLOWED))
    if "usb_bridge" in body:
        check(name + ": usb_bridge vid:pid name", ":" in body["usb_bridge"] and " " in body["usb_bridge"], body["usb_bridge"])
    if "browser" in body:
        check(name + ": browser enum", body["browser"] in ("chrome", "edge", "opera", "brave", "other"), body["browser"])
    if "flasher_version" in body:
        check(name + ": flasher_version", body["flasher_version"] == "85", body["flasher_version"])

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(); pg.goto("http://127.0.0.1:8789/index.html"); body = pg.inner_text("body")
    check("text names ESP32 and ESP32-S3", "ESP32 and ESP32-S3" in body)
    check("footer Flasher Version 85", "Flasher Version 85" in pg.text_content(".flasher-version"))
    check("no Compatible Boards on page", "Compatible Boards" not in body); pg.close()

    pg, log, st, notice, details, mac, early, tel = run(b, None)
    w = [l for l in log if l.startswith("files")]
    check("classic ESP32 gets the 4 MB image at 0", w == ["files 1 size 4194304 at 0 eraseAll true"], str(w))
    check("ESP32 installed", "Installed" in pg.inner_text("body"))
    check("no compat notice on good ESP32", notice is None, str(notice))
    check("MAC line shown", mac.upper().startswith("MAC ") and "F8:B3:B7:22:05:E8" in mac.upper(), mac)
    check("board details subtle (dual + flash + CPU + CP2102)",
          "Dual Core" in details and "4 MB flash" in details and "240 MHz" in details and "CP2102" in details, details)
    check("stats on connect (before Install)", "Dual Core" in early and "4 MB flash" in early and "240 MHz" in early and "CP2102" in early, early)
    check("no privacy element on page", pg.evaluate("!document.getElementById('board-privacy')"))
    check_tel("ESP32 telemetry", tel, True, "ESP32")
    if tel:
        body = tel[0]["body"]
        check("ESP32 telemetry cores=2", body.get("cores") == 2, str(body.get("cores")))
        check("ESP32 telemetry flash_mb=4", body.get("flash_mb") == 4, str(body.get("flash_mb")))
        check("ESP32 stats use CPU not crystal", "240 MHz" in details and " · 40 MHz" not in details and not details.strip().startswith("40 MHz"), details)
        check("ESP32 telemetry usb", body.get("usb_bridge") == "10c4:ea60 CP2102", str(body.get("usb_bridge")))
        check("ESP32 telemetry revision", body.get("revision") == "v3.1", str(body.get("revision")))
    # second install same connect: still one telemetry
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(6000)
    tel2 = pg.evaluate("window.__telemetry")
    check("telemetry once per connect", len(tel2) == 1, str(tel2))
    pg.close()

    pg, log, st, notice, details, mac, early, tel = run(b, "ESP32-S3 (QFN56) (revision v0.2)")
    w = [l for l in log if l.startswith("files")]
    check("ESP32-S3 gets the 16 MB image at 0", w == ["files 1 size 16777216 at 0 eraseAll true"], str(w))
    check("S3 detected in the console", "[ESP32-S3 detected: installing its build]" in pg.inner_text("#console-out"))
    check("S3 installed", "Installed" in pg.inner_text("body"), str(st[-3:]))
    check("S3 details include PSRAM + 16 MB", "16 MB flash" in details and "Embedded PSRAM" in details and "Dual Core" in details, details)
    check("no compat notice on good S3", notice is None)
    check_tel("S3 telemetry", tel, True, "ESP32-S3")
    if tel:
        check("S3 telemetry psram", tel[0]["body"].get("psram") is True, str(tel[0]["body"]))
        check("S3 telemetry flash_mb=16", tel[0]["body"].get("flash_mb") == 16, str(tel[0]["body"].get("flash_mb")))
    pg.close()

    pg, log, st, notice, details, mac, early, tel = run(b, "ESP32-C3 (QFN32) (revision v0.4)", auto_install=False)
    # Version 92: Stable (the default) has no C3 image: a short Beta-only note, nothing written
    check("ESP32-C3 on Stable: nothing written", not [l for l in log if l.startswith("files")], str(log))
    check("ESP32-C3 on Stable: short Beta-only note", notice and notice["title"] == "The ESP32-C3 Is Only on Beta for Now" and notice["text"] == "Choose Beta under Release to install it.", str(notice))
    check("ESP32-C3 on Stable: Stable stays the default, plain Stable/Beta", pg.input_value("#release-channel") == "stable" and pg.eval_on_selector_all("#release-channel option", "o => o.map(x => x.textContent.trim())") == ["Stable", "Beta"])
    check("ESP32-C3: no old clear-error string", "GSP32 runs on ESP32 and ESP32-S3 boards" not in pg.inner_text("body") and "Not Supported" not in (notice or {}).get("title", ""))
    check("ESP32-C3: Single Core in details", "Single Core" in details, details)
    check_tel("C3 telemetry", tel, True, "ESP32-C3")
    if tel:
        check("C3 telemetry cores=1", tel[0]["body"].get("cores") == 1, str(tel[0]["body"].get("cores")))
    # The user's path: Install opens the step with the Release list; on Stable, Erase and Install stays off
    check("ESP32-C3 on Stable: Install opens the step (to choose Beta)", pg.evaluate("!document.getElementById('install-btn').disabled"))
    pg.click("#install-btn"); pg.wait_for_timeout(500); pg.check("#erase-ok")
    check("ESP32-C3 on Stable: Erase and Install stays off", pg.evaluate("document.getElementById('start-install').disabled"))
    # Choosing Beta clears the note and installs the C3 image (4 MB at 0)
    pg.select_option("#release-channel", "beta"); pg.wait_for_timeout(800)
    hidden = pg.evaluate("document.getElementById('compat-notice').hidden || document.getElementById('compat-notice').shutting === true")
    check("ESP32-C3 on Beta: note gone, Version 92, Erase and Install on", hidden and pg.text_content("#version").strip() == "Version 92" and pg.evaluate("!document.getElementById('start-install').disabled"), str(hidden))
    pg.click("#start-install"); pg.wait_for_timeout(6000)
    w = [l for l in pg.evaluate("window.__log") if isinstance(l, str) and l.startswith("files")]
    check("ESP32-C3 on Beta gets the 4 MB C3 image at 0", w == ["files 1 size 4194304 at 0 eraseAll true"] and "[ESP32-C3 detected: installing its build]" in pg.inner_text("#console-out") and "[Image: ESP32-C3 4 MB (Super Mini)" in pg.inner_text("#console-out"), str(w))
    check("ESP32-C3 installed", "Installed" in pg.inner_text("body"))
    pg.close()

    pg, log, st, notice, details, mac, early, tel = run(b, "ESP32-C3 (QFN32) (revision v0.2)")
    check("ESP32-C3 rev v0.2: not supported, nothing written", not [l for l in log if l.startswith("files")] and notice and notice["title"] == "This Board Is Not Supported" and "v0.3 or newer" in notice["text"], str(notice))
    pg.close()

    pg, log, st, notice, details, mac, early, tel = run(b, "ESP32-D0WD-V3 (revision v3.1)", flash_kb=2048)
    check("small flash ESP32: nothing written", not [l for l in log if l.startswith("files")])
    check("small flash: notice names 2 MB", notice and "2 MB flash" in notice["text"] and "This Board Is Not Supported" == notice["title"], str(notice))
    check("small flash: details show 2 MB", "2 MB flash" in details, details)
    check_tel("small-flash telemetry", tel, False, "ESP32")
    if tel:
        check("small-flash flash_mb=2", tel[0]["body"].get("flash_mb") == 2, str(tel[0]["body"].get("flash_mb")))
    pg.close()

    pg, log, st, notice, details, mac, early, tel = run(b, "ESP32-S3 (QFN56) (revision v0.2)", flash_kb=4096)
    check("S3 4 MB: nothing written", not [l for l in log if l.startswith("files")])
    check("S3 4 MB: notice", notice and "4 MB flash" in notice["text"], str(notice))
    check_tel("S3-4MB telemetry", tel, False, "ESP32-S3")
    pg.close()

    pg, log, st, notice, details, mac, early, tel = run(b, None, usb={"usbVendorId": 0x1a86, "usbProductId": 0x55d3})
    check("CH343 named from VID/PID", "CH343" in details, details)
    check("CH343 on connect", "CH343" in early, early)
    if tel:
        check("CH343 usb_bridge", tel[0]["body"].get("usb_bridge") == "1a86:55d3 CH343", str(tel[0]["body"].get("usb_bridge")))
    pg.close()

    # Telemetry must not delay install even if fetch hangs
    pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.add_init_script(path=here + "/mock.js")
    pg.add_init_script("""
      window.__ver='47'; window.__log=[];
      const real = window.fetch.bind(window);
      window.fetch = (input, init) => {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        if (url.indexOf('gsp32-telemetry') >= 0 && url.indexOf('/log') >= 0) return new Promise(() => {}); // never resolves
        return real(input, init);
      };
    """)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.goto("http://127.0.0.1:8789/index.html"); pg.wait_for_timeout(300); pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(4500)
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(7000)
    log = [l for l in pg.evaluate("window.__log") if isinstance(l, str)]
    check("hanging telemetry does not block install", any(l.startswith("files") for l in log) and "Installed" in pg.inner_text("body"), str([l for l in log if l.startswith("files")]))
    pg.close()

    b.close()
srv.shutdown()
print("FAILURES:", fails); sys.exit(1 if fails else 0)
