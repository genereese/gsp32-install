# Version 49 / 53: install speed per USB chip, checked, stepped down on errors within one install only (never saved); full image always
import sys, http.server, threading, functools, os, json
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); here = os.path.dirname(os.path.abspath(__file__))
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8772), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)
KEY = "gsp32-baud:10c4:ea60:f8:b3:b7:22:05:e8"
def run(b, init="", storage=None):
    pg = b.new_page(); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script("window.__ver = '47';" + init)
    # Version 53: every status line text, and whether the status pulsed (erasing class) while it showed
    pg.add_init_script("""window.__status = []; addEventListener('DOMContentLoaded', () => { const el = document.getElementById('board-status');
      new MutationObserver(() => window.__status.push([el.textContent, document.getElementById('board-status') ? document.getElementById('board-status').classList.contains('erasing') : null]))
        .observe(el, {childList: true, characterData: true, subtree: true}); });""")
    if storage: pg.add_init_script("localStorage.setItem(%r, %r)" % storage)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.goto("http://127.0.0.1:8772/index.html"); pg.wait_for_timeout(300); pg.click("#connect"); pg.wait_for_timeout(100)
    pg.evaluate("window.__port.setSignals({requestToSend: true}).then(() => window.__port.setSignals({requestToSend: false}))")
    pg.wait_for_timeout(4500)
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(5000)
    log = pg.evaluate("window.__log"); saved = pg.evaluate("localStorage.getItem(%r)" % KEY)
    pg.status = pg.evaluate("window.__status")
    return pg, [l for l in log if isinstance(l, str)], saved
with sync_playwright() as p:
    b = p.chromium.launch()
    pg, log, saved = run(b)
    writes = [l for l in log if l.startswith("write at")]
    check("CP210x: 921600 tried, checked, written there", writes == ["write at 921600"] and "open 921600" in log, str(writes))
    check("full image, erase all", any("eraseAll true" in l for l in log) and any("size" in l for l in log))
    check("V53: nothing saved", saved is None and pg.evaluate("Object.keys(localStorage).filter(k => k.startsWith('gsp32-baud:')).length") == 0, str(saved))
    check("back to 115200 for the console after", [l for l in log if l.startswith("open")][-1] == "open 115200")
    texts = [t for t, _ in pg.status]
    check("V53: status shows the speed while writing", any(t.startswith("Installing") and "at 921,600 Baud (" in t and "%)" in t for t in texts), str(texts[-6:]))
    check("V53: no step-down notice when the fast speed works", not any("Didn't Work" in t for t in texts))
    check("installed", "Installed" in pg.inner_text("#board-state") or "Installed" in pg.inner_text("body"))
    pg.close()
    pg, log, saved = run(b, "window.__badBaud = [921600];")
    writes = [l for l in log if l.startswith("write at")]
    check("check read fails at 921600: steps down to 460800", writes == ["write at 460800"], str(writes))
    check("V53: the slower rate is not saved", saved is None, str(saved))
    notices = [(t, e) for t, e in pg.status if "Didn't Work" in t]
    check("V53: plain step-down notice naming 460,800, status pulsing", notices and notices[0][0] == "Fast Speed Didn't Work, Retrying at 460,800 Baud..." and all(e for _, e in notices), str(notices))
    check("V53: then writing shows 460,800", any("at 460,800 Baud (" in t for t, _ in pg.status))
    pg.close()
    pg, log, saved = run(b, "window.__failWriteAt = [921600];")
    writes = [l for l in log if l.startswith("write at")]
    check("write error at 921600: full install again at 460800", writes == ["write at 921600", "write at 460800"], str(writes))
    check("installed after the retry", "Installed" in pg.inner_text("body"), "")
    pcts = [int(t.rsplit("(", 1)[1].rstrip("%)")) for t, _ in pg.status if " Baud (" in t]
    restart = [i for i in range(1, len(pcts)) if pcts[i] < pcts[i - 1]]
    check("V53: after a write error the notice shows and the bar starts over", any(t == "Fast Speed Didn't Work, Retrying at 460,800 Baud..." for t, _ in pg.status)
          and restart and pcts[restart[0]] == 0, str(pcts))
    pg.close()
    pg, log, saved = run(b, "window.__badBaud = [921600, 460800, 230400];")
    writes = [l for l in log if l.startswith("write at")]
    tries = [l for l in log if l.startswith("change baud")]
    check("V53: full chain 921600 -> 460800 -> 230400, then installs at 115200", tries == ["change baud 921600", "change baud 460800", "change baud 230400"]
          and writes == ["write at 115200"] and "Installed" in pg.inner_text("body"), str((tries, writes)))
    pg.close()
    pg, log, saved = run(b, "", (KEY, "230400"))
    check("V53: an old saved entry is cleared and ignored: starts at 921600", [l for l in log if l.startswith("change baud")][:1] == ["change baud 921600"] and saved is None,
          str(([l for l in log if l.startswith("change baud")], saved)))
    pg.close()
    pg, log, saved = run(b, "window.__usb = {usbVendorId: 0x1234, usbProductId: 0x5678};")
    check("V53: an unknown chip also starts at 921600", [l for l in log if l.startswith("change baud")][:1] == ["change baud 921600"])
    pg.close()
    pg, log, saved = run(b, "window.__usb = {usbVendorId: 0x1a86, usbProductId: 0x55d4};")
    check("CH9102 tries 2000000 first", [l for l in log if l.startswith("change baud")][:1] == ["change baud 2000000"])
    pg.close()
print("fails", fails); sys.exit(1 if fails else 0)
