# Version 50: compact landing on one laptop screen, step 3 on one line, gallery icons centered, slides one height
import sys, http.server, threading, functools, os
from playwright.sync_api import sync_playwright
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8814), functools.partial(http.server.SimpleHTTPRequestHandler, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0
def check(name, ok, extra=""):
    global fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name, extra)
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1366, "height": 768}); pg.goto("http://127.0.0.1:8814/index.html"); pg.wait_for_timeout(1000)
    last = pg.locator(".tour-thumb").last.bounding_box()
    check("whole gallery on one 1366x768 screen", last["y"] + last["height"] <= 768, str(last))
    s3 = pg.locator(".steps-row li:not(.arrow) >> nth=2").bounding_box()
    check("step 3 on one line", s3["height"] < 36, str(s3))
    hs = []
    for i in range(pg.locator(".tour-thumb").count()):
        if i == 0: pg.click(".tour-thumb >> nth=0"); pg.wait_for_timeout(300)
        else: pg.click("#tour-next"); pg.wait_for_timeout(250)
        hs.append(round(pg.locator("#tour-modal").bounding_box()["height"]))
        for sel in ("#tour-prev", "#tour-next", "#tour-close"):
            bb = pg.locator(sel).bounding_box(); ib = pg.locator(sel + " svg").bounding_box()
            if abs((bb["x"] + bb["width"] / 2) - (ib["x"] + ib["width"] / 2)) > 1 or abs((bb["y"] + bb["height"] / 2) - (ib["y"] + ib["height"] / 2)) > 1:
                check("icon centered in " + sel + " slide " + str(i), False, str((bb, ib)))
    check("every slide the same height", len(set(hs)) == 1, str(hs))
    print("icons checked on", len(hs), "slides")
print("fails", fails); sys.exit(1 if fails else 0)
