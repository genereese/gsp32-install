# Version 101 (Gene): a Disconnect button at the right end of the Install GSP32 row. It shows (slides in) once the
#  port is open, is gone while installing and back after, and closes the port cleanly: the board left running
#  (DTR and RTS off), the port closed once, Get Started back; Get Started connects again. The console's one stays.
import sys, http.server, threading, functools, os
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=site)
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8816), handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
here = os.path.dirname(os.path.abspath(__file__)); fails = 0
SHOTS = os.environ.get("SHOTS", "/tmp/flasher-shots"); os.makedirs(SHOTS, exist_ok=True)
def check(name, ok, info=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  " + str(info))); fails += not ok
def shown(pg, sel):
    return pg.evaluate("(s) => { const e = document.querySelector(s); return !!e && !e.hidden && !(e.sliding && !e.sliding.on) && e.getBoundingClientRect().width > 0; }", sel)
def box(pg, sel): return pg.locator(sel).bounding_box()
def page(b, w=1280):
    pg = b.new_page(viewport={"width": w, "height": 900}); pg.add_init_script(path=here + "/mock.js")
    pg.add_init_script("window.__ets = true; window.__bootGap = 0; window.__failFlash = false")
    pg.add_init_script("""(() => { window.__discAnim = []; const a = Element.prototype.animate; Element.prototype.animate = function (k, o) {
        if (this.id === 'board-disconnect' && Array.isArray(k)) window.__discAnim.push(Object.keys(k[0]).join(',')); return a.call(this, k, o); }; })()""")
    pg.route("**/vendor/esptool-js-0.5.7.js", lambda r: r.fulfill(path=here + "/fake-esptool.js", content_type="text/javascript"))
    pg.goto("http://127.0.0.1:8816/index.html"); pg.wait_for_timeout(300)
    return pg
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = page(b)
    check("before connecting: no row Disconnect", not shown(pg, "#board-disconnect"))
    pg.click("#connect"); pg.wait_for_timeout(1200)
    check("connected: Disconnect in the row, enabled", shown(pg, "#board-disconnect") and pg.evaluate("!document.getElementById('board-disconnect').disabled"))
    row, d, inst = box(pg, "#board-actions"), box(pg, "#board-disconnect"), box(pg, "#install-btn")
    check("at the right end of the Install GSP32 row", abs((d["x"] + d["width"]) - (row["x"] + row["width"])) <= 2 and d["x"] > inst["x"] + inst["width"] and abs((d["y"] + d["height"] / 2) - (inst["y"] + inst["height"] / 2)) <= 2, (row, d, inst))
    check("worded Disconnect, in the secondary style", pg.inner_text("#board-disconnect").strip() == "Disconnect" and "secondary" in pg.get_attribute("#board-disconnect", "class"))
    check("the console's Disconnect is still there", pg.locator("#disconnect").count() == 1)
    check("its push is a CSS variable", pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--board-disconnect-push').trim()") == "auto")
    pg.screenshot(path=SHOTS + "/v101-disconnect-row.png")
    # It slid in (setShown animates its width and opacity)
    anim = pg.evaluate("window.__discAnim")
    check("it slides and fades in (width, opacity)", bool(anim) and "width" in anim[0] and "opacity" in anim[0], anim)
    pg.wait_for_timeout(300)
    # Installing: gone; back after
    pg.click("#install-btn"); pg.check("#erase-ok"); pg.click("#start-install"); pg.wait_for_timeout(400)
    check("while installing: gone", not shown(pg, "#board-disconnect"))
    pg.wait_for_timeout(3500)
    check("after the install: back", shown(pg, "#board-disconnect"), pg.inner_text("#board-status")[:60])
    pg.wait_for_timeout(500)
    n = len(pg.evaluate("window.__log"))
    pg.click("#board-disconnect"); pg.wait_for_timeout(1200)
    after = pg.evaluate("window.__log")[n:]
    closes = [l for l in after if l.startswith("close")]
    check("click: the port closes once, the device left running (DTR and RTS off)", closes == ["close dtr=false rts=false"], after)
    check("no reset into the bootloader on the way out", not any("rts=true" in l for l in after), after)
    check("the device card and console fold away, Get Started back", not shown(pg, "#console") and not shown(pg, "#console-card") and shown(pg, "#connect") and pg.evaluate("!document.getElementById('connect').disabled"))
    check("no error in the console log", "Something went wrong" not in pg.inner_text("#console-out"))
    pg.click("#connect"); pg.wait_for_timeout(1200)
    check("Get Started connects again (the row's Disconnect back)", shown(pg, "#board-disconnect"))
    pg.close()
    # Phone width: still on the row's right edge
    pg = page(b, 390); pg.click("#connect"); pg.wait_for_timeout(1200)
    row, d = box(pg, "#board-actions"), box(pg, "#board-disconnect")
    check("phone: Disconnect on the right, inside the card", d and abs((d["x"] + d["width"]) - (row["x"] + row["width"])) <= 2 and d["x"] >= row["x"], (row, d))
    pg.screenshot(path=SHOTS + "/v101-disconnect-phone.png")
    pg.close(); b.close()
print("fails", fails); sys.exit(1 if fails else 0)
