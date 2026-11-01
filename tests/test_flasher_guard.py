# Flasher Version 115.38 (Gene, t2970u/t2971u): the install guard. While an install (with its erase) runs: the banner
#  "Installing — keep this tab open and in front until it finishes.", a beforeunload handler (added at the start,
#  removed at the end) for the browser's own "Leave site?" prompt, a screen wake lock (asked for again when the tab shows
#  mid-install, let go at the end; silent where there is none), and the tab's hidden time counted. A failed write or
#  check after hidden time says so in plain words; with no hidden time the normal error; a good install never nags
import os, re, http.server, threading, functools
from playwright.sync_api import sync_playwright
here = os.path.dirname(os.path.abspath(__file__)); site = os.path.dirname(here)
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8932), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, "" if ok else extra)
BANNER = "Installing \u2014 keep this tab open and in front until it finishes."
VERIFY_HIDDEN = re.compile(r"^The install didn't verify\. This tab was in the background for (\d+) s during the install, which can interrupt it\. Keep this tab in front and try again\.$")
FINISH_HIDDEN = re.compile(r"^The install didn't finish\. This tab was in the background for (\d+) s during the install, which can interrupt it\. Keep this tab in front and try again\.$")
# The manifest held back (so the install sits in its guarded part long enough to hide the tab); the tab's visibility
#  under the test's control (window.__setHidden); beforeunload listeners logged; a fake screen wake lock (__wake)
INIT = r"""
const f0 = window.fetch; window.fetch = (u, o) => (window.__slowManifest && /manifest/.test(String(u))) ? new Promise(r => setTimeout(r, window.__slowManifest)).then(() => f0(u, o)) : f0(u, o);
window.__unload = [];
const add0 = window.addEventListener.bind(window), rem0 = window.removeEventListener.bind(window);
window.addEventListener = (t, f, o) => { if (t === 'beforeunload') window.__unload.push('add'); return add0(t, f, o); };
window.removeEventListener = (t, f, o) => { if (t === 'beforeunload') window.__unload.push('remove'); return rem0(t, f, o); };
let hid = false;
Object.defineProperty(Document.prototype, 'hidden', { configurable: true, get: () => hid });
Object.defineProperty(Document.prototype, 'visibilityState', { configurable: true, get: () => hid ? 'hidden' : 'visible' });
window.__wake = [];
if (!window.__noWake) {
  let held = null;
  const lock = { request: async (type) => {
    window.__wake.push('request ' + type);
    const ls = [];
    const s = { released: false, type, ls, addEventListener: (t, f) => { if (t === 'release') ls.push(f); },
      release: async () => { if (s.released) return; s.released = true; window.__wake.push('release'); ls.forEach(f => f()); } };
    held = s; return s; } };
  Object.defineProperty(Navigator.prototype, 'wakeLock', { configurable: true, get: () => lock });
  // The browser drops a held screen lock when the tab hides
  window.__dropWake = () => { if (held && !held.released) { held.released = true; window.__wake.push('dropped'); held.ls.forEach(f => f()); } };
} else {
  try { delete Navigator.prototype.wakeLock; } catch (e) {}
}
window.__setHidden = (h) => { hid = h; if (h && window.__dropWake) window.__dropWake(); document.dispatchEvent(new Event('visibilitychange')); };
"""
def page(b, init=""):
    pg = b.new_page(viewport={"width": 1100, "height": 900}); pg.add_init_script(path=here + "/mock.js")
    pg.add_init_script("window.__ver = '47';" + init); pg.add_init_script(INIT)
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.route("**/gsp32-telemetry.genereese.workers.dev/**", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true}'))
    errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:8932/index.html"); pg.wait_for_timeout(300)
    return pg, errors
def start(pg):
    pg.click("#connect"); pg.wait_for_timeout(1500)
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(150)
def finish(pg):
    pg.wait_for_function("document.getElementById('wizard').hidden || !document.querySelector('[data-step=error]').hidden", timeout=40000)
    pg.wait_for_timeout(400)
def err_text(pg): return pg.evaluate("document.getElementById('error-text').textContent")
def installed(pg): return "Installed" in pg.inner_text("#board-status")
def unload(pg): return pg.evaluate("window.__unload")
def wake(pg): return pg.evaluate("window.__wake")
with sync_playwright() as p:
    b = p.chromium.launch()
    # 1. A good install, the tab in front: the guard comes and goes, no hidden time, Installed, no nag
    pg, errors = page(b, "window.__slowManifest = 1200;")
    check("before the install: no beforeunload handler, banner hidden", unload(pg) == [] and pg.locator("#flash-warn").is_hidden(), str(unload(pg)))
    start(pg)
    check("installing: beforeunload handler added once", unload(pg) == ["add"], str(unload(pg)))
    check("installing: the banner shows, its words", pg.locator("#flash-warn").is_visible() and pg.inner_text("#flash-warn") == BANNER, pg.inner_text("#flash-warn"))
    check("installing: a screen wake lock asked for", wake(pg) == ["request screen"], str(wake(pg)))
    finish(pg)
    check("good install: Installed", installed(pg))
    check("after: beforeunload handler removed", unload(pg) == ["add", "remove"], str(unload(pg)))
    check("after: banner folded away", pg.locator("#flash-warn").is_hidden())
    check("after: wake lock released", wake(pg) == ["request screen", "release"], str(wake(pg)))
    hs = pg.evaluate("({...window.gsp32.flashHidden})")
    check("tab in front: not counted as hidden", hs["went"] is False and hs["ms"] == 0, str(hs))
    check("no page errors (1)", not errors, str(errors)); pg.close()
    # 2. The prompt itself: a beforeunload event mid-install is cancelled (the browser then asks "Leave site?"); after the
    #  install nothing cancels it. (Headless Chromium shows no beforeunload dialog, so the event is sent by hand)
    pg, errors = page(b, "window.__slowManifest = 2500;")
    BU = "(() => { const e = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(e); return e.defaultPrevented; })()"
    check("before the install: leaving is not held", pg.evaluate(BU) is False)
    start(pg)
    check("mid-install: leaving asks first (beforeunload cancelled)", pg.evaluate(BU) is True)
    finish(pg)
    check("after the install: leaving is not held", pg.evaluate(BU) is False)
    check("no page errors (2)", not errors, str(errors)); pg.close()
    # 3. Hidden mid-install, then a good install: hidden time counted, wake lock asked for again, Installed, no nag
    pg, errors = page(b, "window.__slowManifest = 2500;")
    start(pg)
    pg.evaluate("window.__setHidden(true)"); pg.wait_for_timeout(1500); pg.evaluate("window.__setHidden(false)")
    pg.wait_for_timeout(100)
    check("visible again mid-install: wake lock asked for again", wake(pg) == ["request screen", "dropped", "request screen"], str(wake(pg)))
    finish(pg)
    hs = pg.evaluate("({...window.gsp32.flashHidden})")
    check("hidden 1.5 s: counted (went, 1.3-2.5 s)", hs["went"] is True and 1300 <= hs["ms"] <= 2500, str(hs))
    check("hidden, but a good install: Installed, no background note", installed(pg) and "in the background for" not in pg.inner_text("body"), pg.inner_text("#board-status"))
    check("after: handler removed, wake lock released", unload(pg) == ["add", "remove"] and wake(pg) == ["request screen", "dropped", "request screen", "release"], str((unload(pg), wake(pg))))
    check("no page errors (3)", not errors, str(errors)); pg.close()
    # 4. Hidden mid-install, and the check (MD5) fails 3 times: the plain background message with the seconds
    pg, errors = page(b, "window.__slowManifest = 2600; window.__writePlan = ['md5', 'md5', 'md5'];")
    start(pg)
    pg.evaluate("window.__setHidden(true)"); pg.wait_for_timeout(2000); pg.evaluate("window.__setHidden(false)")
    finish(pg)
    e = err_text(pg); m = VERIFY_HIDDEN.match(e)
    check("hidden + MD5 failure: \"The install didn't verify. This tab was in the background for N s ...\"", bool(m) and 1 <= int(m.group(1)) <= 3, e)
    check("hidden + MD5 failure: also in the console", "background for" in pg.inner_text("#console-out"))
    check("hidden + MD5 failure: not Installed, handler removed", not installed(pg) and unload(pg) == ["add", "remove"], str(unload(pg)))
    check("no page errors (4)", not errors, str(errors)); pg.close()
    # 5. Hidden mid-install, noise breaks every write: the "didn't finish" form of the same message
    pg, errors = page(b, "window.__slowManifest = 2600; window.__noiseWrites = 9;")
    start(pg)
    pg.evaluate("window.__setHidden(true)"); pg.wait_for_timeout(1000); pg.evaluate("window.__setHidden(false)")
    finish(pg)
    e = err_text(pg); m = FINISH_HIDDEN.match(e)
    check("hidden + write failure: \"The install didn't finish. This tab was in the background ...\"", bool(m), e)
    check("no page errors (5)", not errors, str(errors)); pg.close()
    # 6. Tab in front, MD5 fails 3 times: the normal error, no background words
    pg, errors = page(b, "window.__writePlan = ['md5', 'md5', 'md5'];")
    start(pg); finish(pg)
    e = err_text(pg)
    check("in front + MD5 failure: the normal error", e.startswith("The install did not finish. The image on the device did not match") and "background" not in e, e)
    check("in front + MD5 failure: handler removed, wake lock released", unload(pg) == ["add", "remove"] and wake(pg) == ["request screen", "release"], str((unload(pg), wake(pg))))
    check("no page errors (6)", not errors, str(errors)); pg.close()
    # 7. No Screen Wake Lock in this browser: the install runs as before, quietly
    pg, errors = page(b, "window.__noWake = true;")
    check("no wakeLock: navigator has none", pg.evaluate("!('wakeLock' in navigator)"))
    start(pg); finish(pg)
    check("no wakeLock: Installed, no page errors", installed(pg) and not errors, str(errors)); pg.close()
    b.close()
print("FAILURES:", fails)
raise SystemExit(1 if fails else 0)
