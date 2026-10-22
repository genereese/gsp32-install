# Version 80: board stats + compat notice + telemetry on connect (before Install); Install disabled when incompatible
import sys, os, json, http.server, threading, functools
from playwright.sync_api import sync_playwright
here = os.path.dirname(os.path.abspath(__file__)); site = os.path.dirname(here)
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8798), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)

js = open(os.path.join(site, "app.js")).read()
html = open(os.path.join(site, "index.html")).read()
check("cache-bust 109-fw109", html.count("?v=109-fw109") == 3)
check("probeBoardOnConnect present", "probeBoardOnConnect" in js and "Reading board info" in js)
check("Install disabled when compatIssue", "board.compatIssue" in js and "install.disabled" in js)
check("footer Flasher Version 109", "Flasher Version 109" in html)

def connect_only(b, chip=None, flash_kb=None, usb=None):
    pg = b.new_page(viewport={"width": 1100, "height": 900})
    pg.add_init_script(path=here + "/mock.js")
    init = "window.__ver='47'; window.__log=[]; window.__telemetry=[]; window.__installs=0;"
    if chip: init += "window.__chip=%s;" % json.dumps(chip)
    if flash_kb is not None: init += "window.__flashKb=%s;" % json.dumps(flash_kb)
    if usb is not None: init += "window.__usb=%s;" % json.dumps(usb)
    init += """
    (() => { const real = window.fetch.bind(window);
      window.fetch = (input, init) => {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        if (url.indexOf('/install') >= 0 && url.indexOf('gsp32-telemetry') >= 0) { window.__installs++; return Promise.resolve(new Response('{}')); }
        if (url.indexOf('gsp32-telemetry') >= 0 && url.indexOf('/log') >= 0) {
          let body = null;
          try { body = JSON.parse(init && init.body || '{}'); } catch (e) { body = init && init.body; }
          window.__telemetry.push({ url, method: (init && init.method) || 'GET', body });
          return Promise.resolve(new Response(JSON.stringify({ok:true}), {status:200, headers:{'Content-Type':'application/json'}}));
        }
        return real(input, init);
      }; })();
    """
    pg.add_init_script(init)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.route("**/gsp32-telemetry.genereese.workers.dev/**", lambda r: r.fulfill(status=200, body='{"ok":true}'))
    pg.goto("http://127.0.0.1:8798/index.html"); pg.wait_for_timeout(300)
    pg.click("#connect")
    # Wait until probe finishes (busy clears / Reading board info done)
    pg.wait_for_function("""() => {
      const log = (window.__log || []).join('\\n');
      const body = document.body.innerText;
      return body.includes('Reading board info') || (document.getElementById('board-details') && !document.getElementById('board-details').hidden);
    }""", timeout=15000)
    pg.wait_for_timeout(500)  # let finally/release finish
    # Ensure install not mid-busy
    for _ in range(40):
        if not pg.evaluate("!!window.gsp32 && false"): break
        # poll install disabled state / details
        busy = pg.evaluate("""() => {
          const btn = document.getElementById('install-btn');
          return btn && btn.disabled && !document.getElementById('board-details')?.textContent;
        }""")
        # better: wait for details or notice or console line
        done = pg.evaluate("""() => {
          const d = document.getElementById('board-details');
          const n = document.getElementById('compat-notice');
          const out = document.getElementById('console-out');
          const text = out ? out.textContent : '';
          return (d && !d.hidden && d.textContent) || (n && !n.hidden) || text.includes('could not read') || text.includes('Board:');
        }""")
        if done: break
        pg.wait_for_timeout(100)
    pg.wait_for_timeout(200)
    details = pg.evaluate("(() => { const el=document.getElementById('board-details'); return el&&!el.hidden?el.textContent:''; })()")
    mac = pg.evaluate("(() => { const el=document.getElementById('board-mac'); return el&&!el.hidden?el.textContent:''; })()")
    notice = pg.evaluate("""() => {
      const box=document.getElementById('compat-notice');
      if(!box||box.hidden) return null;
      return {title:document.getElementById('compat-notice-title').textContent,
              text:document.getElementById('compat-notice-text').textContent};
    }""")
    install_disabled = pg.evaluate("document.getElementById('install-btn').disabled")
    tel = pg.evaluate("window.__telemetry")
    log = [l for l in pg.evaluate("window.__log") if isinstance(l, str)]
    return pg, details, mac, notice, install_disabled, tel, log

with sync_playwright() as p:
    b = p.chromium.launch()

    # Classic ESP32: stats + telemetry on connect, Install enabled, no notice
    pg, details, mac, notice, disabled, tel, log = connect_only(b, None)
    check("ESP32 connect: MAC shown", "F8:B3:B7:22:05:E8" in mac.upper(), mac)
    check("ESP32 connect: stats before Install",
          "Dual Core" in details and "4 MB flash" in details and "240 MHz" in details and "CP2102" in details, details)
    check("ESP32 connect: no notice", notice is None, str(notice))
    check("ESP32 connect: Install enabled", disabled is False, str(disabled))
    check("ESP32 connect: telemetry once", len(tel) == 1 and tel[0]["body"].get("compatible") is True, str(tel))
    check("ESP32 connect: no flash write yet", not any(l.startswith("files") for l in log), str(log))
    # Install then: no second telemetry
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(500)
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(6000)
    tel2 = pg.evaluate("window.__telemetry")
    check("ESP32 install: still one telemetry", len(tel2) == 1, str(tel2))
    inst = pg.evaluate("window.__installs || 0")
    check("ESP32 install: one /install beacon", inst == 1, str(inst))
    check("ESP32 install: wrote image", any(l.startswith("files") for l in pg.evaluate("window.__log") if isinstance(l, str)))
    pg.close()

    # C3 (Version 92: Beta only for now): on Stable a short Beta-only note, before Install; Install opens the step (where
    #  Release is) but Erase and Install stays off until Beta is chosen. The board
    #  itself counts as compatible in telemetry
    pg, details, mac, notice, disabled, tel, log = connect_only(b, "ESP32-C3 (QFN32) (revision v0.4)")
    # Version 99: Stable has the C3 image now (no note on connect); the previous Stable is checked in test_v79
    check("C3 connect: no note on Stable", not notice, str(notice))
    check("C3 connect: Single Core stats", "Single Core" in details and "160 MHz" in details, details)
    check("C3 connect: Install opens the step", disabled is False, str(disabled))
    check("C3 connect: telemetry compatible (on Beta)", len(tel) == 1 and tel[0]["body"].get("compatible") is True, str(tel))
    check("C3 connect: nothing written", not any(l.startswith("files") for l in log))
    pg.click("#install-btn", force=True)
    pg.wait_for_timeout(300)
    if pg.is_visible("#erase-ok"): pg.check("#erase-ok")
    # Version 106 (Gene): Stable is the only version (Release hidden); it has the C3 image
    check("C3 on Stable (the only version): Release hidden, Erase and Install is on", pg.evaluate("document.querySelector('.release-field').hidden && !document.getElementById('start-install').disabled"))
    check("C3 on Stable: nothing written after the Install click", not any(l.startswith("files") for l in pg.evaluate("window.__log") if isinstance(l, str)))
    tel3 = pg.evaluate("window.__telemetry")
    check("C3: still one telemetry after Install click", len(tel3) == 1, str(tel3))
    pg.close()

    # S3 4 MB: notice on connect (Version 83: 8 MB S3 boards are supported)
    pg, details, mac, notice, disabled, tel, log = connect_only(b, "ESP32-S3 (QFN56) (revision v0.2)", flash_kb=4096)
    check("S3-4MB connect: notice", notice and "4 MB flash" in notice["text"], str(notice))
    check("S3-4MB connect: Install disabled", disabled is True)
    check("S3-4MB connect: telemetry", len(tel) == 1 and tel[0]["body"].get("compatible") is False)
    pg.close()

    # Good S3: PSRAM in stats on connect
    pg, details, mac, notice, disabled, tel, log = connect_only(b, "ESP32-S3 (QFN56) (revision v0.2)")
    check("S3 connect: PSRAM+16MB stats", "Embedded PSRAM" in details and "16 MB flash" in details, details)
    check("S3 connect: Install enabled", disabled is False)
    check("S3 connect: telemetry ok", len(tel) == 1 and tel[0]["body"].get("compatible") is True)
    pg.close()

    b.close()
srv.shutdown()
print("FAILURES:", fails); sys.exit(1 if fails else 0)
