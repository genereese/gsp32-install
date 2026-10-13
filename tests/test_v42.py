# Version 42: 15 px body text (headings and the Install button in proportion, console unchanged), smaller Wi-Fi rows
#  and password box, and the status bar pulsing blue while the board erases
import sys, http.server, threading, functools, os
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); here = os.path.dirname(os.path.abspath(__file__))
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8771), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
shots = os.environ.get("SHOTS") or __import__("tempfile").mkdtemp(prefix="gsp32-v42-")
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra); sys.stdout.flush()
def px(pg, sel, prop="fontSize"):
    return pg.evaluate("parseFloat(getComputedStyle(document.querySelector(%r))[%r])" % (sel, prop))
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 900}); pg.add_init_script(path=here + "/mock.js"); pg.add_init_script("window.__eraseDelay = 2500")
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:8771/index.html"); pg.wait_for_timeout(300)
    body, h1 = px(pg, "body"), px(pg, "h1")
    check("body text 15 px", abs(body - 15) < 0.05, body)
    check("h1 scaled 30.4 * 15/17 = 26.8 px", abs(h1 - 26.82) < 0.1, h1)
    pg.click("#connect"); pg.wait_for_timeout(500)
    check("console font unchanged (13.6 px)", abs(px(pg, "#console-out") - 13.6) < 0.05, px(pg, "#console-out"))
    pg.click("#install-btn"); pg.wait_for_timeout(500)
    big = pg.evaluate("(() => { const e = document.getElementById('start-install'); const s = getComputedStyle(e); return [parseFloat(s.fontSize), e.offsetHeight]; })()")
    pg.check("#erase-ok"); pg.click("#start-install")
    samples = []
    for _ in range(14):
        pg.wait_for_timeout(120)
        samples.append(pg.evaluate("(() => { const s = document.getElementById('board-status'); return [s.classList.contains('erasing'), +getComputedStyle(s, '::before').opacity, s.innerText]; })()"))
    erasing = [s for s in samples if s[0]]
    check("bar pulses while erasing (opacity moves)", len(erasing) >= 5 and max(s[1] for s in erasing) - min(s[1] for s in erasing) > 0.2 and all("Erasing" in s[2] for s in erasing), [round(s[1], 2) for s in erasing])
    pg.screenshot(path=shots + "/v42-erasing.png")
    pg.wait_for_timeout(1500)
    s = pg.evaluate("(() => { const s = document.getElementById('board-status'); return [s.classList.contains('erasing'), s.innerText]; })()")
    check("pulse ends when writing starts", not s[0], s)
    pg.wait_for_function("document.getElementById('wizard').hidden", timeout=20000); pg.wait_for_timeout(1200)
    pg.click("#wifi-setup"); pg.wait_for_selector("#wifi-list li", timeout=20000); pg.wait_for_timeout(500)
    row = pg.evaluate("(() => { const l = document.querySelector('#wifi-list label'); return [parseFloat(getComputedStyle(l.querySelector('.net-name')).fontSize), l.offsetHeight]; })()")
    pg.click("#wifi-list li:first-child label"); pg.wait_for_timeout(600)
    pw = pg.evaluate("(() => { const e = document.getElementById('wifi-password'); return [parseFloat(getComputedStyle(e).fontSize), e.offsetHeight]; })()")
    check("network rows a bit under 15 px", 13 <= row[0] < 15, row)
    check("password box a bit under 15 px and shorter", 13 <= pw[0] < 15 and pw[1] <= 36, pw)
    print("install button", big)
    pg.screenshot(path=shots + "/v42-wifi.png", full_page=True)
    check("no page errors", not errors, errors)
print("fails", fails); sys.exit(1 if fails else 0)
